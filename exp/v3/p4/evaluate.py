"""Replay budgeted decisions against P3 offline outcomes and measured component costs."""

import argparse
from collections import Counter
import csv
import hashlib
import math
from pathlib import Path
from random import Random
from statistics import mean, quantiles

from prepare import load_json, load_records, sha, write_json

HERE = Path(__file__).resolve().parent
SIGNS = ("improved", "tied", "degraded")
REFERENCE = ("fixed_fuzzy", "ridge")


def label_sign(value):
    return "improved" if value > 0 else "degraded" if value < 0 else "tied"


def describe_errors(ids, scores, targets):
    errors = {qid: scores[qid] - targets[qid]["delta_f1"] for qid in ids}
    groups = {sign: [errors[qid] for qid in ids if label_sign(targets[qid]["delta_f1"]) == sign] for sign in SIGNS}
    return {"mse": mean(e**2 for e in errors.values()), "mae": mean(abs(e) for e in errors.values()),
            "prediction_min": min(scores[qid] for qid in ids), "prediction_max": max(scores[qid] for qid in ids),
            "by_label": {sign: {"n": len(es), "mse": mean(e**2 for e in es), "mae": mean(abs(e) for e in es)}
                         for sign, es in groups.items() if es}}


def selection(ids, scores, k, tie_seed):
    def key(qid):
        return -scores[qid], hashlib.sha256(f"{tie_seed}:{qid}".encode()).hexdigest(), qid

    top = sorted(ids, key=key)[:k]
    return set(top), key(top[-1]) if top else None


def evaluate_policy(ids, method, budget, chosen, targets, costs, *, uses_nli, cutoff=None):
    selected_f1 = {qid: targets[qid]["b_f1" if qid in chosen else "a_f1"] for qid in ids}
    counts = Counter(label_sign(targets[qid]["delta_f1"]) for qid in chosen)
    n = len(ids)
    qwen_in, qwen_out, nli_tokens, estimated_seconds = 0, 0, 0, []
    for qid in ids:
        c = costs[qid]
        expand = qid in chosen
        qwen_in += c["a_input_tokens"] + (c["b_input_tokens"] if expand else 0)
        qwen_out += c["a_output_tokens"] + (c["b_output_tokens"] if expand else 0)
        nli_tokens += c["nli_input_tokens"] if uses_nli else 0
        estimated_seconds.append((c["pair_elapsed_seconds"] if expand else c["a_http_seconds"])
                                 + (c["nli_seconds"] if uses_nli else 0.))
    return {
        "method": method, "budget_percent": budget, "validation_n": n, "selected_n": len(chosen),
        **{f"selected_{sign}": counts[sign] for sign in SIGNS},
        "missed_improved": sum(targets[qid]["delta_f1"] > 0 for qid in ids) - counts["improved"],
        "val_f1": mean(selected_f1.values()),
        "val_em": mean(float(targets[qid]["b_em" if qid in chosen else "a_em"]) for qid in ids),
        "qwen_calls": n + len(chosen), "qwen_input_tokens": qwen_in, "qwen_output_tokens": qwen_out,
        "qwen_input_tokens_per_question": qwen_in / n, "qwen_output_tokens_per_question": qwen_out / n,
        "nli_calls": n if uses_nli else 0, "nli_input_tokens": nli_tokens,
        "p3_component_seconds_per_question": mean(estimated_seconds),
        "p3_component_seconds_p95": quantiles(estimated_seconds, n=100, method="inclusive")[94],
        "cutoff_score": -cutoff[0] if cutoff else None,
        "cutoff_tie_sha256": cutoff[1] if cutoff else None,
        "cutoff_qid": cutoff[2] if cutoff else None,
        "selected_qids": "|".join(sorted(chosen)),
    }, selected_f1


def paired(draws, ids, method, ref, budget, values):
    a, b = (values[m, budget] for m in (method, ref))
    delta = [100 * (a[qid] - b[qid]) for qid in ids]
    samples = [math.fsum(delta[i] for i in draw) / len(ids) for draw in draws]
    q = quantiles(samples, n=1000, method="inclusive")
    return {"model": method, "reference": ref, "budget_percent": budget, "point_f1_pp": mean(delta),
            "ci95_low_f1_pp": q[24], "ci95_high_f1_pp": q[974]}


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def check_checkpoint_predictions(cfg, raw, features, qids, scores, spec, runs):
    by_fit = {(r["variant"], r["alpha"], r["seed"]): r for r in runs}
    if len(by_fit) != len(cfg["variants"]) * len(cfg["alphas"]) * len(cfg["seeds"]):
        raise ValueError("Missing or duplicate optimization run")
    for run in runs:
        if (not run["checkpoint_replay_exact"] or not run["finite_gradients"]
                or run["max_rule_sum_error"] > 1e-6
                or sha(raw / run["weights_path"]) != run["weights_sha256"]):
            raise ValueError("Checkpoint, gradient or rule identity failed")
    for variant, settings in spec["variants"].items():
        for seed in cfg["seeds"]:
            p = by_fit[variant, settings["alpha"], seed]["effective_parameters"]
            for qid in qids:
                risk, bridge = features[qid]["x"].values()
                h_r = 1 / (1 + math.exp(-(risk - p["center_r"]) / p["width_r"]))
                h_g = 1 / (1 + math.exp(-(bridge - p["center_bridge"]) / p["width_bridge"]))
                a, b = 1-h_r, 1-h_g
                score = a*b*p["LL"] + a*h_g*p["LH"] + h_r*b*p["HL"] + h_r*h_g*p["HH"]
                if not math.isclose(score, scores[f"{variant}_seed{seed}"][qid], abs_tol=2e-7):
                    raise ValueError(f"Effective-rule replay disagrees at {qid}")


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--raw", type=Path, required=True, help="Remote evidence output directory")
    cli.add_argument("--out", type=Path, required=True)
    args = cli.parse_args()
    cfg = load_json(HERE / "protocol.json")
    inputs = HERE / "input"
    manifest = load_json(inputs / "manifest.json")
    if (any(sha(inputs / name) != expected for name, expected in manifest["inputs_sha256"].items())
            or sha(HERE / "protocol.json") != manifest["upstream_sha256"]["p4_protocol"]):
        raise ValueError("P4 replay inputs differ from the freeze")
    identity = load_json(args.raw / "train_manifest.json")
    if (identity["train_source_sha256"] != sha(HERE / "train.py")
            or identity["input_manifest_sha256"] != sha(inputs / "manifest.json")):
        raise ValueError("Training provenance does not match the frozen cache")
    targets = load_records(inputs / "targets.jsonl")
    costs = load_records(inputs / "cost.jsonl")
    features = load_records(inputs / "features.jsonl")
    predictions = load_json(args.raw / "predictions.json")
    ids = predictions["qid_order"]
    if (len(ids) != len(set(ids)) or set(ids) != set(targets) or set(ids) != set(costs) or set(ids) != set(features)
            or any(len(s) != len(ids) or not all(math.isfinite(v) for v in s) for s in predictions["scores"].values())):
        raise ValueError("Result keys/shape differ from the frozen 150 questions")
    scores = {key: dict(zip(ids, values, strict=True)) for key, values in predictions["scores"].items()}
    spec = load_json(args.raw / "model_spec.json")
    runs = load_json(args.raw / "all_run_checkpoints.json")
    check_checkpoint_predictions(cfg, args.raw, features, ids, scores, spec, runs)
    train = [qid for qid in ids if targets[qid]["split"] == "train"]
    val = [qid for qid in ids if targets[qid]["split"] == "validation"]
    regression = {method: {"train": describe_errors(train, pred, targets), "validation": describe_errors(val, pred, targets)}
                  for method, pred in scores.items() if method.endswith(tuple(f"_seed{s}" for s in cfg["seeds"]))
                  or method in {"ridge", "constant_mean"}}

    curve, policies = [], {}
    for method, pred in scores.items():
        for budget in cfg["budgets_percent"]:
            chosen, cutoff = selection(val, pred, len(val) * budget // 100, cfg["tie_seed"])
            row, policies[method, budget] = evaluate_policy(val, method, budget, chosen, targets, costs,
                                                          uses_nli=method != "constant_mean", cutoff=cutoff)
            curve.append(row)
    for method, chosen, budget in (("top2_always_a", set(), 0), ("two_stage_always_b", set(val), 100)):
        row, _ = evaluate_policy(val, method, budget, chosen, targets, costs, uses_nli=False)
        curve.append(row)

    primary = f"full_sugeno_seed{cfg['primary_seed']}"
    rng = Random(cfg["paired_bootstrap_seed"])
    draws = [[rng.randrange(len(val)) for _ in val] for _ in range(cfg["paired_bootstrap_resamples"])]
    intervals = [paired(draws, val, primary, ref, budget, policies)
                 for budget in cfg["budgets_percent"] for ref in REFERENCE]
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    write_csv(out / "validation_cost_curve.csv", curve)
    write_csv(out / "paired_validation_intervals.csv", intervals)
    write_json(out / "summary.json", {
        "n_by_split": cfg["n_by_split"], "seed42_primary_method": primary,
        "alpha_by_variant": {v: spec["variants"][v]["alpha"] for v in cfg["variants"]},
        "regression": regression, "optimization_runs": len(runs), "bootstrap_seed": cfg["paired_bootstrap_seed"],
        "bootstrap_resamples": len(draws), "budget_replays": len(curve),
        "interval_scope": "Exploratory paired validation bootstrap of already-selected actions. No refit/resorting within bootstrap.",
        "cost_scope": "Same-qid P3 cached Qwen tokens; charge original A and any selected B, and all NLI for NLI-dependent routes. Times replay measured P3 components; no live P4 timing for question answering.",
    })
    print(f"Verified {len(runs)} checkpoints; scored {len(curve)} cached policies and {len(intervals)} paired intervals.")


if __name__ == "__main__":
    main()

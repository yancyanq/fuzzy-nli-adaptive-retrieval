"""Freeze model identity and score boundaries using only the existing validation labels."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

from policy import key, score_policy

HERE = Path(__file__).resolve().parent
V3 = HERE.parent


def load(path):
    return json.loads(path.read_text())


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--calibration", type=Path, required=True)
    cli.add_argument("--out", type=Path, required=True)
    args = cli.parse_args()
    raw = V3 / "p4/remote-evidence/output"
    cfg = load(HERE / "protocol.json")
    spec = load(raw / "model_spec.json")
    checkpoints = load(raw / "all_run_checkpoints.json")
    p4_predictions = load(raw / "predictions.json")
    labels = {r["qid"]: r for r in lines(V3 / "p4/input/targets.jsonl") if r["split"] == "validation"}
    x = {r["qid"]: r["x"] for r in lines(V3 / "p4/input/features.jsonl") if r["qid"] in labels}
    panel = {r["qid"]: r for r in lines(V3 / "p3/remote-evidence/qwen/first_round.jsonl") if r["qid"] in labels}
    qwen = {r["qid"]: r for r in lines(args.calibration) if r["ok"]}
    if not (len(labels) == 50 and set(labels) == set(qwen) == set(x) == set(panel)):
        raise ValueError("Calibration must use the frozen validation qids only")
    for qid, r in qwen.items():
        if (not r["validation"]["ok"] or r["format"] != "guided_selfcheck_example_free"
                or any(r[k] != panel[qid][k] for k in ("pool_sha256", "a_prompt_sha256"))):
            raise ValueError(f"Invalid/mismatched validation selfcheck for {qid}")
    models, weight_paths = {}, {}
    for variant, seeds in (("full_sugeno", (17,42,73)), ("consequents_only", (42,))):
        alpha = spec["variants"][variant]["alpha"]
        for seed in seeds:
            name = f"{variant}_seed{seed}"
            fitted = next(row for row in checkpoints if (row["variant"], row["alpha"], row["seed"]) == (variant, alpha, seed))
            if sha(raw / fitted["weights_path"]) != fitted["weights_sha256"]:
                raise ValueError("P4 checkpoint hash mismatch")
            weight_paths[name] = str(raw.relative_to(V3) / fitted["weights_path"])
            models[name] = {"kind": "sugeno", "parameters": fitted["effective_parameters"],
                            "checkpoint_sha256": fitted["weights_sha256"]}
    p = spec["baseline_parameters"]
    fixed = p["fixed_fuzzy_parameters"]
    historic = p["locked_v2_fuzzy"]
    models.update({
        "ridge": {"kind": "linear", "parameters": p["ridge_parameters_intercept_then_features"]},
        "constant_mean": {"kind": "constant", "parameters": p["constant_train_mean"]},
        "fixed_fuzzy": {"kind": "fixed_fuzzy", "parameters": fixed},
        "locked_v2_fuzzy": {"kind": "fixed_fuzzy", "parameters": historic["parameters"]},
        "v2_native": {"kind": "fixed_fuzzy", "parameters": historic["parameters"]},
        "nli_only": {"kind": "nli_only"},
        "qwen_selfcheck": {"kind": "selfcheck"},
        "crisp": {"kind": "crisp", "parameters": fixed},
        "weighted_risk_bridge": {"kind": "weighted"},
    })
    seed = cfg["tie_seed"]
    with (V3 / "p4/analysis/validation_cost_curve.csv").open() as stream:
        p4_selected = {(r["method"], int(r["budget_percent"])): set(r["selected_qids"].split("|"))
                       for r in csv.DictReader(stream)}
    boundaries, val_metrics = {}, {}
    for method, model in models.items():
        if method == "v2_native":
            continue
        scores = {qid: score_policy(model, *x[qid].values(), qwen[qid]["validation"]["risk"]) for qid in labels}
        if any(score is None for score in scores.values()):
            raise ValueError("Calibration score unavailable")
        order = sorted((key(score,qid,seed) for qid, score in scores.items()))
        if method in p4_predictions["scores"]:
            former = dict(zip(p4_predictions["qid_order"], p4_predictions["scores"][method], strict=True))
            if any(not math.isclose(score, former[qid], abs_tol=2e-7, rel_tol=0) for qid, score in scores.items()):
                raise ValueError("P4 effective-rule replay changed numeric scores")
        bounds, metrics = {}, {}
        for budget in cfg["budgets_percent"]:
            n = len(labels)*budget//100
            bounds[budget] = order[n-1]
            chosen = {cut[-1] for cut in order[:n]}
            if (method,budget) in p4_selected and chosen != p4_selected[method,budget]:
                raise ValueError("P4 portable scoring changed validation selection")
            metrics[budget] = {"count": n, "f1": math.fsum(
                r["b_f1"] if qid in chosen else r["a_f1"] for qid,r in labels.items())/len(labels)}
        boundaries[method], val_metrics[method] = bounds, metrics
    data = {
        "scope": "Validation calibrated immutable boundaries, reused at every final scale.",
        "models": models, "weight_paths_from_exp_v3": weight_paths, "tie_seed": seed, "boundaries": boundaries,
        "historical_v2_boundary": historic["boundary_sort_key"], "validation_metrics": val_metrics,
        "calibration_qids_sha256": hashlib.sha256(json.dumps(sorted(labels)).encode()).hexdigest(),
        "qwen_selfcheck_calibration_sha256": sha(args.calibration), "p4_model_spec_sha256": sha(raw / "model_spec.json"),
        "p4_predictions_sha256": sha(raw / "predictions.json"),
        "model_logic_sha256": sha(HERE / "policy.py"), "protocol_sha256": sha(HERE / "protocol.json")
    }
    with args.out.open("x",encoding="utf-8") as handle:
        handle.write(json.dumps(data,indent=2) + "\n")
    print(f"Froze {len(models)} scores and {sum(map(len,boundaries.values()))} action boundaries.")


if __name__ == "__main__":
    main()

"""Calibrate fixed cutoffs on one cohort and evaluate on the other."""
from argparse import ArgumentParser
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from random import Random
from statistics import mean
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "constraint-aware-gate-20261122"))
from policy_values import features, ranks, read, triggered

P5 = HERE.parents[1] / "exp/v3/p5"
sys.path.insert(0, str(P5))
from evaluate import official_module


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def by_id(path):
    with path.open(encoding="utf-8") as stream:
        items = [json.loads(line) for line in stream]
    result = {r["qid"]: r for r in items}
    if len(result) != len(items):
        raise ValueError(f"Duplicate row in {path}")
    return result


def check_hashes(directory, manifest):
    files = {
        directory / "pools.jsonl": "pool_sha256",
        directory / "evaluation_gold.jsonl": "gold_sha256",
        HERE / "trained.json": "trained_sha256",
        HERE / "dates.py": "constraint_code_sha256",
        HERE / "policy_values.py": "policy_code_sha256",
        HERE / "protocol.json": "protocol_sha256",
    }
    for path, field in files.items():
        if digest(path) != manifest[field]:
            raise ValueError(f"Sealed input changed: {path}")


def measure(official, pred, gold):
    scores = Counter()
    official.update_answer(scores, pred, gold)
    return scores["f1"], scores["em"]


def open_block(phase, official):
    directory = HERE / phase
    manifest = read(directory / "manifest.json")
    check_hashes(directory, manifest)
    qids = manifest["qids"]
    expected = set(qids)
    a, b, pool, gold, nli = (by_id(directory / n) for n in (
        "a.jsonl", "b.jsonl", "pools.jsonl", "evaluation_gold.jsonl", "nli.jsonl"
    ))
    plan = read(directory / "plan.json")
    if plan["phase"] != phase or set(a) != expected or set(pool) != expected or set(gold) != expected or set(nli) != expected:
        raise ValueError("Unexpected online records")
    if set(b) != {q for group in plan["routes"].values() for q in group}:
        raise ValueError("Follow-up outputs differ from planned union")
    trained = read(HERE / "trained.json")
    block = {}
    for q in qids:
        first = a[q]
        expanded = b.get(q)
        if any(rec["pool_sha256"] != pool[q]["pool_sha256"] for rec in [first, nli[q]] + ([expanded] if expanded else [])):
            raise ValueError(f"Pool identity differs for {q}")
        measured_ranks = {name: tuple(vec) if vec is not None else None for name, vec in nli[q]["ranks"].items()}
        recomputed = ranks(pool[q], first, nli[q], trained)
        for name in measured_ranks:
            observed, expected_rank = measured_ranks[name], recomputed[name]
            if bool(observed) != bool(expected_rank) or (observed and
               (abs(observed[0] - expected_rank[0]) > 1e-12 or observed[1:] != expected_rank[1:])):
                raise ValueError(f"Policy replay differs for {q}/{name}")
        is_valid_b = expanded is not None and expanded["ok"]
        base_f1, base_em = measure(official, first["answer"], gold[q]["answer"])
        next_f1, next_em = (measure(official, expanded["answer"], gold[q]["answer"])
                            if is_valid_b else (base_f1, base_em))
        if expanded and expanded["calls"][0]["input_tokens"] != nli[q]["planned_b_tokens"]:
            raise ValueError(f"Follow-up token audit differs for {q}")
        signal = features(pool[q], first)
        block[q] = {"qid": q, "ranks": measured_ranks, "a_f1": base_f1, "a_em": base_em,
                    "b_f1": next_f1, "b_em": next_em, "signal_gap": signal.gap, "missing": signal.missing,
                    "answer_type": signal.answer_type, "type_mismatch": signal.type_mismatch,
                    "a_input": first["calls"][0]["input_tokens"], "a_output": first["calls"][0]["output_tokens"],
                    "b_input": expanded["calls"][0]["input_tokens"] if expanded else None,
                    "b_output": expanded["calls"][0]["output_tokens"] if expanded else None,
                    "a_answer": first["answer"], "b_answer": expanded["answer"] if expanded else None,
                    "gold_answer": gold[q]["answer"]}
    return block, plan["routes"], manifest


def best_prefix(block, ordered, input_cap=None):
    candidates = [{"n": 0, "extra_input": 0, "f1_gain_sum": 0., "included": []}]
    for q in ordered:
        prev = candidates[-1]
        row = block[q]
        request = {"n": prev["n"] + 1, "extra_input": prev["extra_input"] + row["b_input"],
                   "f1_gain_sum": prev["f1_gain_sum"] + row["b_f1"] - row["a_f1"],
                   "included": prev["included"] + [q]}
        if input_cap is not None and request["extra_input"] > input_cap:
            break
        candidates.append(request)
    best = max(candidates, key=lambda r: (round(r["f1_gain_sum"], 12), -r["extra_input"], -r["n"]))
    return best, candidates


def per_question(row, names, selection):
    output = dict(row)
    output["methods"] = {}
    for name in names:
        chosen = row["qid"] in selection[name]
        if chosen and row["b_input"] is None:
            raise ValueError(f"A selected B result is missing for {row['qid']}")
        output["methods"][name] = {
            "triggered": chosen, "f1": row["b_f1"] if chosen else row["a_f1"],
            "em": row["b_em"] if chosen else row["a_em"],
            "qwen_input": row["a_input"] + (row["b_input"] if chosen else 0),
            "qwen_output": row["a_output"] + (row["b_output"] if chosen else 0),
        }
    return output


def summarize(block, chosen):
    values = [per_question(row, chosen.keys(), chosen) for row in block.values()]
    result = {}
    for name in chosen:
        cases = [v["methods"][name] for v in values]
        summary = {metric: mean(c[metric] for c in cases) for metric in ("f1", "em", "qwen_input", "qwen_output")}
        result[name] = {**summary, "qwen_total": summary["qwen_input"] + summary["qwen_output"],
                        "triggered": sum(c["triggered"] for c in cases),
                        "improved_on_trigger": sum(v["methods"][name]["triggered"] and v["b_f1"] > v["a_f1"] for v in values),
                        "worsened_on_trigger": sum(v["methods"][name]["triggered"] and v["b_f1"] < v["a_f1"] for v in values)}
    return result, values


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def calibrate(block, plan, manifest):
    limit = int(len(block) * read(HERE / "protocol.json")["threshold_calibration"]["cap_rate"])
    prefixes = {method: sorted([q for q, row in block.items() if row["ranks"][method] is not None],
                               key=lambda q: block[q]["ranks"][method])[:limit] for method in ("old", "repaired")}
    if prefixes != plan:
        raise ValueError("Calibration candidate replay differs from plan")

    old, old_options = best_prefix(block, prefixes["old"])
    repaired, repaired_options = best_prefix(block, prefixes["repaired"], old["extra_input"])
    choices = {"old": old, "repaired": repaired}
    boundaries, selections = {}, {}
    for method, row in choices.items():
        prefix = row["included"]
        boundary = block[prefix[-1]]["ranks"][method] if prefix else None
        boundaries[method] = boundary
        selections[method] = {q for q, item in block.items() if triggered(item["ranks"][method], boundary)}
        if selections[method] != set(prefix):
            raise ValueError("Calibration boundary does not reproduce its prefix")
    scores, details = summarize(block, selections)
    lock = {"trained_sha256": manifest["trained_sha256"], "protocol_sha256": manifest["protocol_sha256"],
            "calibration_manifest_sha256": digest(HERE / "calibration/manifest.json"),
            "calibration_qids": manifest["qids"], "cap_extra_qwen_input_tokens": old["extra_input"],
            "boundaries": boundaries}
    save(HERE / "thresholds.json", lock)
    return {"n": len(block), "max_triggers": limit, "extra_input_cap": old["extra_input"], "methods": scores,
            "thresholds": boundaries, "prefix_search": {"old": old_options, "repaired": repaired_options}}, details


def test(block, plan, manifest):
    locked = read(HERE / "thresholds.json")
    if (locked["trained_sha256"] != manifest["trained_sha256"] or
       locked["protocol_sha256"] != manifest["protocol_sha256"] or
       locked["calibration_manifest_sha256"] != digest(HERE / "calibration/manifest.json") or
       set(block) & set(locked["calibration_qids"])):
        raise ValueError("Threshold identity or test disjointness check failed")
    selected = {name: {q for q, row in block.items() if triggered(row["ranks"][name], boundary)}
                for name, boundary in locked["boundaries"].items()}
    if selected != {k: set(v) for k, v in plan.items()}:
        raise ValueError("Fixed test decisions do not match server plan")
    scores, details = summarize(block, selected)
    differences = [(d["methods"]["repaired"]["f1"] - d["methods"]["old"]["f1"],
                    d["methods"]["repaired"]["qwen_input"] - d["methods"]["old"]["qwen_input"]) for d in details]
    rng = Random(42)
    paired = [rng.choices(differences, k=len(differences)) for _ in range(10000)]
    bands = []
    for i in (0, 1):
        metric = sorted(mean(j[i] for j in draw) for draw in paired)
        bands.append([metric[250], metric[9750]])
    delta_f1 = mean(d[0] for d in differences)
    delta_input = mean(d[1] for d in differences)
    return {"n": len(block), "different_actions": len(selected["old"] ^ selected["repaired"]),
            "first_only_f1": mean(r["a_f1"] for r in block.values()),
            "constraint_gap_count": sum(r["signal_gap"] > 0 for r in block.values()),
            "methods": scores, "delta_f1": delta_f1, "delta_input": delta_input,
            "paired_f1_95": bands[0], "paired_input_95": bands[1],
            "meets_predeclared_point_target": delta_f1 > 0 and delta_input <= 0}, details


def main():
    cli = ArgumentParser()
    cli.add_argument("phase", choices=("calibration", "test"))
    args = cli.parse_args()
    block, plan, manifest = open_block(args.phase, official_module())
    summary, details = (calibrate if args.phase == "calibration" else test)(block, plan, manifest)
    save(HERE / args.phase / "summary.json", summary)
    with (HERE / args.phase / "cases.jsonl").open("w", encoding="utf-8") as handle:
        for row in details:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

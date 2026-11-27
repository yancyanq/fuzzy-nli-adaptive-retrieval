"""Score sealed inference locally and report both equal-count and fixed thresholds."""
from collections import Counter
from hashlib import sha256
import json
from random import Random
from statistics import mean

import numpy as np

from run import HERE, P3, P5, by_hash, design, development, evaluate, index, load, make_case, rows, score_policy
from evaluate import official_module


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def score_ranks(cases, models, cfg, p4):
    result = {name: design(cases, m["fuzzy"], m["enriched"], cfg) @ np.asarray(m["weights"])
              for name, m in models.items()}
    result["nli_only"] = [c.risk for c in cases]
    result["p4_sugeno_archived"] = [score_policy(p4, c.risk, c.bridge, None) for c in cases]
    return result


def deployment(train_cases, test_cases, models, cfg, p4):
    test_values = score_ranks(test_cases, models, cfg, p4)
    train_values = score_ranks(train_cases, models, cfg, p4)
    budget = len(train_cases) * cfg["budget_percent"] // 100
    output = {}
    for name in train_values:
        def rank(case, score):
            return -float(score), by_hash(case.qid, cfg["tie_seed"]), case.qid

        candidates = sorted(rank(c, s) for c, s in zip(train_cases, train_values[name]) if c.risk is not None)
        cutoff = candidates[budget - 1]
        take = [c.risk is not None and rank(c, s) <= cutoff for c, s in zip(test_cases, test_values[name])]
        output[name] = {
            "boundary": [float(cutoff[0]), *cutoff[1:]], "trigger_count": sum(take),
            "f1": mean(c.b_f1 if chosen else c.a_f1 for c, chosen in zip(test_cases, take)),
            "selected_improve": sum(c.gain > 0 for c, chosen in zip(test_cases, take) if chosen),
            "avg_qwen_input_tokens": mean(c.b_tokens if chosen else c.a_tokens for c, chosen in zip(test_cases, take)),
        }
    return output


def bootstrap(details, left, right):
    delta = [(r["b_f1"] - r["a_f1"]) * (int(r["selected"][left]) - int(r["selected"][right]))
             for r in details]
    rng = Random(42)
    draws = sorted(mean(rng.choices(delta, k=len(delta))) for _ in range(10000))
    return {"delta_f1": mean(delta), "paired_percentile_95": [draws[250], draws[9750]],
            "different_actions": sum(r["selected"][left] != r["selected"][right] for r in details)}


def main():
    fresh = HERE / "fresh"
    manifest = load(fresh / "manifest.json")
    artifacts = {"pools.jsonl": "pool_sha256", "evaluation_gold.jsonl": "gold_sha256",
                 "../summary.json": "policy_training_summary_sha256", "../fresh_protocol.json": "protocol_sha256",
                 "../constraints.py": "constraint_code_sha256"}
    for name, field in artifacts.items():
        if digest(fresh / name) != manifest[field]:
            raise ValueError(f"Frozen evidence identity mismatch for {name}")
    trained = load(HERE / "summary.json")
    models = trained["models"]
    cfg = load(HERE / "protocol.json")
    p4 = load(P5 / "policy_lock.json")["models"]["full_sugeno_seed42"]
    official = official_module()
    pools = index(rows(fresh / "pools.jsonl"), "qid")
    gold = index(rows(fresh / "evaluation_gold.jsonl"), "qid")
    answers = index(rows(fresh / "answers.jsonl"), "qid", "route")
    features = index(rows(fresh / "features.jsonl"), "qid")
    expected = set(manifest["qids"])
    routes = load(HERE / "fresh_protocol.json")["routes"]
    if set(pools) != expected or set(gold) != expected or set(features) != expected or set(answers) != {
        (qid, route) for qid in expected for route in routes
    }:
        raise ValueError("Fresh evaluation is incomplete")

    def score(answer, qid):
        result = Counter()
        official.update_answer(result, answer, gold[qid]["answer"])
        return result["f1"]

    cases, direct = [], []
    for qid in manifest["qids"]:
        a, b, direct_row = [answers[qid, route] for route in routes]
        pool = pools[qid]
        feature = features[qid]
        if any(row["pool_sha256"] != pool["pool_sha256"] for row in (a, b, direct_row, feature)):
            raise ValueError("Fresh pool digest mismatch among rows")
        contexts = [pool["input"]["contexts"][i] for i in a["paragraph_indices"]]
        pa, pb, pd = [r["calls"][0]["input_tokens"] for r in (a, b, direct_row)]
        sa, sb = score(a["answer"], qid), score(b["answer"], qid)
        cases.append(make_case(qid, pool["input"]["question"], a["answer"], contexts, feature["risk"],
                               feature["bridge"], (sa, sb if a["ok"] and b["ok"] else sa), (pa, pa + pb)))
        direct.append((score(direct_row["answer"], qid), pd))

    equal_count, details = evaluate(cases, models, cfg, p4)
    train_ids = trained["fit_qids"]
    training = development(train_ids)
    threshold = deployment([training[q] for q in train_ids], cases, models, cfg, p4)
    report = {"equal_count": equal_count, "fixed_training_boundary": threshold,
              "fixed_direct_2plus1": {"f1": mean(v[0] for v in direct), "avg_qwen_input_tokens": mean(v[1] for v in direct)},
              "matched_sugeno_delta": bootstrap(details, "sugeno_constraints", "sugeno_old"),
              "matched_sugeno_vs_linear_delta": bootstrap(details, "sugeno_constraints", "linear_constraints"),
              "wall_scope": "Qwen answering inputs only; NLI scored independently"}
    (fresh / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    (fresh / "cases.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in details))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

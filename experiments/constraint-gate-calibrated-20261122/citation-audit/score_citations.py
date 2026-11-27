"""Evaluate measured citation outputs with local HotpotQA evidence labels."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from random import Random
from statistics import mean
import sys


HERE = Path(__file__).resolve().parent
TEST = HERE.parent / "test"
P5 = HERE.parents[2] / "exp/v3/p5"
sys.path.insert(0, str(P5))
from evaluate import official_module, visible_references


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def index(path, keys=("qid",)):
    with path.open(encoding="utf-8") as stream:
        records = [json.loads(line) for line in stream]
    found = {(tuple(r[k] for k in keys) if len(keys) > 1 else r[keys[0]]): r for r in records}
    if len(found) != len(records):
        raise ValueError(f"Duplicate record in {path}")
    return found


def call_totals(calls):
    if any(not call["ok"] or len(call["attempts"]) != 1 for call in calls):
        raise ValueError("Token ledger requires successful single-attempt calls")
    return {"input": sum(call["input_tokens"] for call in calls),
            "output": sum(call["output_tokens"] for call in calls),
            "count": len(calls)}


def score_branch(official, qid, picked, first, followup, pool, gold, selector):
    final = followup if picked else first
    evidence = selector[qid, "B" if picked else "A"]
    if evidence["pool_sha256"] != pool["pool_sha256"] or evidence["answer_prompt_sha256"] != final["calls"][0]["prompt_sha256"]:
        raise ValueError(f"Evidence attached to different answer or candidate pool: {qid}")
    references = evidence["sp"]
    visible_references(pool, final | {"sp": references})
    contexts = pool["input"]["contexts"]
    indices = final["paragraph_indices"]
    cited = {contexts[indices[i - 1]]["title"] for i in final["citations"]}
    if not {r[0] for r in references} <= cited:
        raise ValueError(f"Selected sentences outside answer citations: {qid}")
    want = [[fact["title"], fact["source_sentence_index"]] for fact in gold["supporting_facts"]]
    metrics = Counter()
    _, ap, ar = official.update_answer(metrics, final["answer"], gold["answer"])
    _, sp, sr = official.update_sp(metrics, references, want)
    jp, jr = ap * sp, ar * sr
    answer_cost = call_totals(first["calls"] + (followup["calls"] if picked else []))
    selector_cost = call_totals(evidence["calls"])
    values = {
        "answer_f1": metrics["f1"], "answer_em": metrics["em"],
        "sp_f1": metrics["sp_f1"], "sp_precision": sp, "sp_recall": sr, "sp_em": metrics["sp_em"],
        "joint_f1": 2 * jp * jr / (jp + jr) if jp + jr else 0., "joint_em": metrics["em"] * metrics["sp_em"],
        "gold_coverage_complete": float(sr == 1.), "nonempty_citation": float(bool(references)),
        "answer_input_tokens": answer_cost["input"], "answer_output_tokens": answer_cost["output"],
        "selector_input_tokens": selector_cost["input"], "selector_output_tokens": selector_cost["output"],
        "total_qwen_input_tokens": answer_cost["input"] + selector_cost["input"],
        "total_qwen_output_tokens": answer_cost["output"] + selector_cost["output"],
        "total_qwen_tokens": sum(answer_cost[k]+selector_cost[k] for k in ("input", "output")),
        "qwen_calls": answer_cost["count"] + selector_cost["count"],
    }
    return {"route": "B" if picked else "A", "metrics": values, "answer": final["answer"], "predicted_sp": references,
            "gold_sp": want, "evidence_reason": evidence["reason"]}


def paired_intervals(rows, metrics):
    deltas = [tuple(r["repaired"]["metrics"][m] - r["old"]["metrics"][m] for m in metrics) for r in rows]
    rng = Random(42)
    samples = [rng.choices(deltas, k=len(deltas)) for _ in range(10000)]
    output = {}
    for i, m in enumerate(metrics):
        values = sorted(mean(x[i] for x in sample) for sample in samples)
        output[m] = {"delta": mean(x[i] for x in deltas), "paired_95": [values[250], values[9750]]}
    return output


def main():
    study = read(HERE / "protocol.json")
    for file, expected in study["online_sha256"].items():
        if digest(TEST / file) != expected:
            raise ValueError(f"Online record differs: {file}")
    if digest(TEST / "summary.json") != study["original_answer_summary_sha256"] or digest(
        TEST / "evaluation_gold.jsonl"
    ) != study["gold_sha256"]:
        raise ValueError("Frozen answer metrics or gold changed")
    a, b, pools, gold = [index(TEST / n) for n in ("a.jsonl", "b.jsonl", "pools.jsonl", "evaluation_gold.jsonl")]
    official = official_module()
    plan = {name: set(ids) for name, ids in read(TEST / "plan.json")["routes"].items()}
    selector = index(HERE / "selector.jsonl", ("qid", "route"))
    expected = {(q, "B" if q in ids else "A") for q in pools for ids in plan.values()}
    if expected != set(selector) or not (set(pools) == set(a) == set(gold)) or len(pools) != 60:
        raise ValueError("Test panel or union of final branches is incomplete")
    answers = [
        {"qid": q, **{name: score_branch(official, q, q in ids, a[q], b.get(q), pool, gold[q], selector)
                      for name, ids in plan.items()}}
        for q, pool in pools.items()
    ]
    methods = {name: {metric: mean(row[name]["metrics"][metric] for row in answers)
                      for metric in answers[0][name]["metrics"]} for name in plan}
    baseline = read(TEST / "summary.json")["methods"]
    for name, row in methods.items():
        if abs(baseline[name]["f1"] - row["answer_f1"]) > 1e-12 or abs(
                baseline[name]["qwen_input"] - row["answer_input_tokens"]) > 1e-12:
            raise ValueError("Previous answer-only summary no longer reproduces")
    report = {"n": len(answers), "selected_final_branches": len(selector),
              "selector_calls": sum(len(r["calls"]) for r in selector.values()),
              "parse_failures": sum(not c["parse_ok"] for r in selector.values() for c in r["calls"]),
              "invalid_selector_sentence_ids": sum(c["invalid_ids"] for r in selector.values() for c in r["calls"]),
              "different_actions": len(plan["old"] ^ plan["repaired"]),
              "methods": methods,
              "paired": paired_intervals(answers, ("sp_f1", "joint_f1", "gold_coverage_complete", "total_qwen_input_tokens")),
              "interpretation": "Automated comparison against annotated HotpotQA supporting sentences; no new manual citation labels."}
    text = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    (HERE / "summary.json").write_text(text, encoding="utf-8")
    (HERE / "cases.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in answers), encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()

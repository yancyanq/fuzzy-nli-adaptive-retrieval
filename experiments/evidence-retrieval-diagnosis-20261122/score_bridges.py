"""Measure a same-gate follow-up swap with audited HotpotQA answer and citation metrics."""
import json
from pathlib import Path
from statistics import mean
import sys


HERE = Path(__file__).resolve().parent
BASELINE = HERE.parent / "constraint-gate-calibrated-20261122"
sys.path.insert(0, str(BASELINE / "citation-audit"))
from score_citations import index, official_module, read, score_branch


def main():
    trial = index(HERE / "bridge_live.jsonl")
    planned = read(HERE / "bridge_ids.json")["routes"]
    if set(trial) != set(planned) or len(trial) != 8:
        raise ValueError("The prespecified follow-up set is incomplete")
    test = BASELINE / "test"
    a, pools, gold = [index(test / filename) for filename in ("a.jsonl", "pools.jsonl", "evaluation_gold.jsonl")]
    baseline = index(BASELINE / "citation-audit/cases.jsonl")
    official = official_module()
    values = []
    for q, ref in baseline.items():
        original = ref["repaired"]
        if q not in trial:
            values.append({"qid": q, "original": original, "bridge_titles": original})
            continue
        answer = trial[q]
        if not answer["ok"] or answer["chunk_ids"] != planned[q]:
            raise ValueError(f"Unexpected follow-up answer or context: {q}")
        evidence = {(q, "B"): {"pool_sha256": answer["pool_sha256"],
                                "answer_prompt_sha256": answer["calls"][0]["prompt_sha256"],
                                "sp": answer["sp"], "calls": answer["calls"][1:],
                                "reason": answer["evidence_reason"]}}
        measured = score_branch(official, q, True, a[q], answer | {"calls": answer["calls"][:1]}, pools[q], gold[q], evidence)
        values.append({"qid": q, "original": original, "bridge_titles": measured})
    metrics = ("answer_f1", "answer_em", "sp_f1", "gold_coverage_complete", "joint_f1",
               "answer_input_tokens", "selector_input_tokens", "total_qwen_input_tokens", "total_qwen_tokens")
    names = ("original", "bridge_titles")
    methods = {name: {m: mean(row[name]["metrics"][m] for row in values) for m in metrics} for name in names}
    report = {"scope": "Retrospective 60-question comparison. Same eight gate triggers and cached first rounds.",
              "n": len(values), "new_followups": len(trial), "methods": methods,
              "answer_f1_cases_improved": sum(r["bridge_titles"]["metrics"]["answer_f1"] > r["original"]["metrics"]["answer_f1"] for r in values),
              "answer_f1_cases_worsened": sum(r["bridge_titles"]["metrics"]["answer_f1"] < r["original"]["metrics"]["answer_f1"] for r in values),
              "answer_text_change_count": sum(r["bridge_titles"]["answer"] != r["original"]["answer"] for r in values)}
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    (HERE / "answer_summary.json").write_text(text)
    (HERE / "answer_cases.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in values))
    print(text, end="")


if __name__ == "__main__":
    main()

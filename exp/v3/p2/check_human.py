"""Summarize reviewer-supplied labels, preserving unknown/missing judgments."""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path

from prepare import HERE, jsonl


SUPPORT = {"entailment", "neutral", "contradiction", "unknown"}
VALID = {
    "whole": ("support", SUPPORT),
    "question": ("coverage", {"complete", "incomplete", "unknown"}),
    "relation": ("faithful", {"yes", "no", "unknown"}),
}


def load_sheet(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--template", required=True, type=Path)
    cli.add_argument("--ratings", required=True, type=Path)
    cli.add_argument("--nli", required=True, type=Path)
    args = cli.parse_args()
    cfg = json.loads((HERE / "protocol.json").read_text())
    labels = load_sheet(args.ratings)
    def row_key(row):
        return row["case_id"], row["qid"], row["unit"], row["item"]

    if Counter(map(row_key, labels)) != Counter(map(row_key, load_sheet(args.template))):
        raise ValueError("Rating rows differ from the locked reviewer packet")
    evidence = {r["qid"]: r for r in jsonl(args.nli)}
    by_case = {}
    for row in labels:
        by_case.setdefault(row["case_id"], []).append(row)
    completed = {}
    for case_id, rows in by_case.items():
        for row in rows:
            column, enum = VALID[row["unit"]]
            if row[column] and row[column] not in enum:
                raise ValueError(f"Invalid {column} label for {case_id}")
            if row["unit"] == "relation" and row["support"] and row["support"] not in SUPPORT:
                raise ValueError(f"Invalid relation support label for {case_id}")
        if all(row["reviewer"].strip() and row[VALID[row["unit"]][0]]
               and (row["unit"] != "relation" or row["support"]) for row in rows):
            completed[case_id] = rows
    fidelity, coverage = Counter(), Counter()
    agree = {"whole": Counter(), "local": Counter()}
    for rows in completed.values():
        for row in rows:
            result = evidence[row["qid"]]
            unit = row["unit"]
            if unit == "whole":
                if row["support"] != "unknown" and not result["old_whole"]["truncated"]:
                    agree["whole"]["eligible"] += 1
                    agree["whole"]["matched"] += int(row["support"] == result["old_whole"]["argmax"])
            elif unit == "question":
                coverage[row["coverage"]] += 1
            else:
                fidelity[row["faithful"]] += 1
                plan = next(p for p in result["local_claims"] if p["requirement_id"] == row["item"])
                if plan["kind"] == "joint" and row["support"] != "unknown":
                    pred = plan["bundles"][0].get("prediction")
                    if pred:
                        agree["local"]["eligible"] += 1
                        agree["local"]["matched"] += int(row["support"] == pred["argmax"])
    evaluated = fidelity["yes"] + fidelity["no"]
    rate = fidelity["yes"] / evaluated if evaluated else None
    print(json.dumps({"completed_cases": len(completed), "sample_cases": len(by_case),
                      "fidelity_counts": fidelity, "coverage_counts": coverage,
                      "fidelity_on_determinate_relationships": rate,
                      "human_fidelity_gate": "pending" if len(completed) < 20 or rate is None else
                          "pass" if rate >= cfg["human_gate"]["human_relationship_fidelity_min"] else "fail",
                      "agreement_on_observed_units": agree}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

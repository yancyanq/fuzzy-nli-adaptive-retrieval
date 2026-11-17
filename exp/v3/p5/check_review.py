"""Summarize two independent P5 citation sheets against the locked private key."""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

FIELDS = ("answer_supported", "chain_complete")
ALLOWED = {"yes", "no", "unknown"}


def sheet(path, expected):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    by_id = {row["item_id"]:row for row in rows}
    if len(by_id) != len(rows) or by_id.keys() != expected:
        raise ValueError(f"Missing, duplicate or unknown item IDs in {path.name}")
    for row in rows:
        if any(row[field] and row[field] not in ALLOWED for field in FIELDS):
            raise ValueError(f"Invalid evidence label for {row['item_id']}")
    return {item: row for item,row in by_id.items() if row["reviewer"].strip() and all(row[field] for field in FIELDS)}


def complete_cases(mapping, complete):
    by_case = {}
    for item, row in mapping.items():
        by_case.setdefault(row["qid"], set()).add(item)
    return {qid for qid, items in by_case.items() if items <= complete.keys()}


def summary(rows, mapping, qids):
    results = {}
    for item, row in rows.items():
        spec = mapping[item]
        if spec["qid"] in qids:
            group = results.setdefault(spec["method"], {name:Counter() for name in FIELDS})
            for name in FIELDS:
                group[name][row[name]] += 1
    return results


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--mapping", required=True, type=Path)
    cli.add_argument("--reviewer1", required=True, type=Path)
    cli.add_argument("--reviewer2", required=True, type=Path)
    args = cli.parse_args()
    methods = [json.loads(line) for line in args.mapping.read_text().splitlines() if line]
    key = {row["item_id"]:row for row in methods}
    if len(key) != len(methods):
        raise ValueError("Duplicate items in private key")
    dual_key = {item:row for item,row in key.items() if row["double_review"]}
    primary = sheet(args.reviewer1, key.keys())
    second = sheet(args.reviewer2, dual_key.keys())
    qids = complete_cases(key,primary)
    doubly_reviewed = qids & complete_cases(dual_key,second)
    paired = [item for item in dual_key if key[item]["qid"] in doubly_reviewed]
    if any(primary[item]["reviewer"].strip() == second[item]["reviewer"].strip() for item in paired):
        raise ValueError("The same reviewer identifier was used twice for a double-review item")
    agreement = {field: {"n":len(paired),"same":sum(primary[i][field]==second[i][field] for i in paired),
                         "both_determinate":sum("unknown" not in (primary[i][field],second[i][field]) for i in paired)}
                 for field in FIELDS}
    print(json.dumps({"primary_completed_cases": len(qids),
        "primary_sample_cases": len({row["qid"] for row in methods}),
        "double_completed_cases": len(doubly_reviewed),
        "double_sample_cases": len({row["qid"] for row in dual_key.values()}),
        "primary_rater_labels": summary(primary,key,qids),
        "second_rater_labels_on_complete_pairs": summary(second,key,doubly_reviewed),
        "double_review_exact_agreement":agreement}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

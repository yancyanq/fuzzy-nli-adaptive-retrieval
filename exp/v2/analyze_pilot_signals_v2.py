#!/usr/bin/env python3
"""Offline comparison of the two approved Protocol V2 pilot rankings."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter
from fractions import Fraction
from itertools import groupby
from pathlib import Path

import analyze_signals as signals
import compare_models as cm


PILOT_SIZE = 100
SELECTION_SIZE = 20
TIE_SEED = 42
WORD = re.compile(r"[^\W_]+")


def records_by_id(records, name):
    indexed = {}
    for record in records:
        qid = record.get("_id")
        if not isinstance(qid, str) or not qid or qid in indexed:
            raise ValueError(f"{name} contains a missing or duplicate _id: {qid!r}")
        indexed[qid] = record
    return indexed


def unit_interval(value, field, qid):
    value = signals.to_float(value)
    if value is None or not 0 <= value <= 1:
        raise ValueError(f"{qid}: invalid {field}")
    return value


def words(text):
    return " ".join(WORD.findall(unicodedata.normalize("NFKC", text).casefold()))


def bridge_matches(context, indices):
    """Return matching (source, target, sentence) indices, or None if unavailable."""
    if len(indices) != 2 or indices[0] == indices[1]:
        return None
    if any(type(index) is not int or not 0 <= index < len(context) for index in indices):
        return None
    left, right = indices
    titles = {index: words(context[index][0]) for index in indices}
    bodies = {index: [words(sentence) for sentence in context[index][1]] for index in indices}
    if any(not titles[index] or not any(bodies[index]) for index in indices):
        return None
    matches = []
    for source, target in ((left, right), (right, left)):
        title = f" {titles[target]} "
        for sentence_index, sentence in enumerate(bodies[source]):
            if title in f" {sentence} ":
                matches.append((source, target, sentence_index))
                break
    return matches


def midpercentiles(scores):
    """Map larger scores to larger exact percentiles, with average ranks on ties."""
    if len(scores) < 2:
        return {}
    ordered = sorted(scores.items(), key=lambda item: item[1])
    result = {}
    start = 0
    for _, entries in groupby(ordered, key=lambda item: item[1]):
        group = list(entries)
        percentile = Fraction(2 * start + len(group) - 1, 2 * (len(scores) - 1))
        result.update((qid, percentile) for qid, _ in group)
        start += len(group)
    return result


def select(scores):
    def key(qid):
        tie_key = hashlib.sha256(f"{TIE_SEED}:{qid}".encode("utf-8")).digest()
        return -scores[qid], tie_key, qid

    return sorted(scores, key=key)[:SELECTION_SIZE]


def class_counts(labels):
    counts = Counter(labels)
    return {label: counts[label] for label in signals.CLASSES}


def analyze(pilot, branches, table):
    if len(pilot) != PILOT_SIZE or pilot.keys() != branches.keys() or pilot.keys() != table.keys():
        raise ValueError("The three files must have the same 100 distinct pilot IDs")
    if any(question.get("type") != "bridge" for question in pilot.values()):
        raise ValueError("All 100 pilot questions must have type bridge")

    matches = {}
    entailment = {}
    for qid, question in pilot.items():
        branch = branches[qid]
        observed = unit_interval(table[qid]["nli_entailment_A"], "A entailment (CSV)", qid)
        stored = unit_interval(branch["nli"]["A"]["probs"]["entailment"], "A entailment (JSONL)", qid)
        if observed != stored or branch["A"]["paragraph_indices"] != branch["r1_indices"]:
            raise ValueError(f"{qid}: inconsistent first-round data between exports")
        entailment[qid] = observed
        matches[qid] = bridge_matches(question["context"], branch["r1_indices"])

    nli_rank = midpercentiles({qid: -value for qid, value in entailment.items()})
    bridge_rank = midpercentiles({
        qid: int(not hits) for qid, hits in matches.items() if hits is not None
    })
    combined = {
        qid: (nli_score + bridge_rank.get(qid, nli_score)) / 2
        for qid, nli_score in nli_rank.items()
    }
    selected = {"nli_only": select(nli_rank), "nli_plus_bridge": select(combined)}

    labels = {}
    for qid, row in table.items():
        branch = branches[qid]
        f1_a = unit_interval(row["F1_A"], "F1_A", qid)
        f1_b = unit_interval(row["F1_B"], "F1_B", qid)
        label = cm.classify_delta(f1_b - f1_a, eps=0)
        if (f1_a, f1_b, label) != (branch["A"]["F1"], branch["B"]["F1"], branch["delta_class"]):
            raise ValueError(f"{qid}: inconsistent A/B F1 or delta class between exports")
        if label != row["delta_class"]:
            raise ValueError(f"{qid}: CSV delta class disagrees with F1 at epsilon=0")
        labels[qid] = label

    totals = class_counts(labels.values())
    results = {}
    for name, ids in selected.items():
        results[name] = {
            "n_selected": len(ids),
            "re_retrieval_rate": len(ids) / PILOT_SIZE,
            "counts": class_counts(labels[qid] for qid in ids),
            "selected_ids": ids,
        }
    counts_a = results["nli_only"]["counts"]
    counts_b = results["nli_plus_bridge"]["counts"]
    nli_set = set(selected["nli_only"])
    combined_set = set(selected["nli_plus_bridge"])
    summary = {
        "protocol": "V2 §7.3 supplemental pilot comparison",
        "n_pilot": PILOT_SIZE,
        "budget_questions": SELECTION_SIZE,
        "tie_seed": TIE_SEED,
        "weights": {"nli": 0.5, "bridge_absence": 0.5},
        "pilot_class_counts": totals,
        "bridge_matches": {
            "linked": sum(bool(hits) for hits in matches.values()),
            "unlinked": sum(hits == [] for hits in matches.values()),
            "unavailable": sum(hits is None for hits in matches.values()),
        },
        "strategies": results,
        "combined_minus_nli": {label: counts_b[label] - counts_a[label] for label in signals.CLASSES},
        "selected_by_both": len(nli_set & combined_set),
        "uniform_random_expected_counts": {
            label: SELECTION_SIZE * count / PILOT_SIZE for label, count in totals.items()
        },
    }
    details = []
    for qid in pilot:
        hits = matches[qid]
        details.append({
            "_id": qid,
            "nli_entailment_A": entailment[qid],
            "nli_risk_percentile": float(nli_rank[qid]),
            "bridge_link": None if hits is None else int(bool(hits)),
            "bridge_matches": json.dumps(hits),
            "bridge_risk_percentile": float(bridge_rank[qid]) if qid in bridge_rank else None,
            "combined_score": float(combined[qid]),
            "delta_class": labels[qid],
            "selected_nli_only": qid in nli_set,
            "selected_nli_plus_bridge": qid in combined_set,
        })
    return summary, details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--branches", type=Path, required=True)
    parser.add_argument("--per-question", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("pilot_signals_v2"))
    args = parser.parse_args()

    try:
        if args.out.name == "cache.jsonl":
            raise ValueError("Refusing cache.jsonl as an output path")
        if args.out.exists():
            raise ValueError(f"Output already exists: {args.out}")
        pilot = json.loads(args.pilot.read_text(encoding="utf-8-sig"))
        with args.branches.open(encoding="utf-8-sig") as file:
            branches = [json.loads(line) for line in file if line.strip()]
        table = signals.load_rows(args.per_question)
        summary, details = analyze(
            records_by_id(pilot, "pilot"),
            records_by_id(branches, "branches"),
            records_by_id(table, "per-question table"),
        )
        summary["input_sha256"] = {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in (
                ("pilot", args.pilot), ("branches", args.branches), ("per_question", args.per_question)
            )
        }
        args.out.mkdir(parents=True)
        (args.out / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        with (args.out / "per_question_selection.csv").open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(details[0]))
            writer.writeheader()
            writer.writerows(details)
    except (OSError, KeyError, TypeError, ValueError) as error:
        parser.exit(2, f"Error: {error}\n")
    print(json.dumps({name: item["counts"] for name, item in summary["strategies"].items()}, indent=2))


if __name__ == "__main__":
    main()

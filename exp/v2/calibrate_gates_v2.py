#!/usr/bin/env python3
"""Fit and lock the two equal-budget V2 gates using the paired tune cache."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path

import analyze_pilot_signals_v2 as pilot
import compare_models as cm

TUNE_SIZE = 500
TARGET_COUNT = 100
TIE_SEED = 42
TUNE_SHA256 = "478f6b2f4d7506a0b8d804de5aa077eacdd3ef20d90f127ac8d22999453ea53b"
LOW_QUANTILES = (0.10, 0.25, 0.40)
HIGH_QUANTILES = (0.55, 0.70, 0.85)
BRIDGE_WEIGHTS = (0.125, 0.25, 0.375)


@dataclass(frozen=True)
class Pair:
    qid: str
    risk: float
    bridge_absent: bool | None
    f1_a: float
    f1_b: float
    em_a: float
    em_b: float

    @property
    def delta(self):
        return self.f1_b - self.f1_a


def probability(value):
    value = float(value)
    if not 0 <= value <= 1:
        raise ValueError(f"Expected a probability in [0, 1], got {value}")
    return value


def load_pairs(questions, branches):
    questions = pilot.records_by_id(questions, "tune questions")
    branches = pilot.records_by_id(branches, "tune branches")
    if len(questions) != TUNE_SIZE or questions.keys() != branches.keys():
        raise ValueError("Need 500 unique tune IDs and exactly one paired record for each")
    if any(row.get("type") != "bridge" for row in questions.values()):
        raise ValueError("The tune split must contain only bridge questions")
    pairs = []
    for qid, row in questions.items():
        record = branches[qid]
        a, b = record["A"], record["B"]
        if a.get("error") or b.get("error"):
            raise ValueError(f"{qid}: generation error in the paired cache")
        first, extra = cm.retrieve_indices(row, 2, 1)
        if record["r1_indices"] != first or a["paragraph_indices"] != first or b["paragraph_indices"] != first + extra:
            raise ValueError(f"{qid}: cached paragraph indices differ from the fixed retrieval")
        entailment = probability(record["nli"]["A"]["probs"]["entailment"])
        probability(record["nli"]["B"]["probs"]["entailment"])
        matches = pilot.bridge_matches(row["context"], first)
        pair = Pair(
            qid, 1 - entailment, None if matches is None else not bool(matches),
            probability(a["F1"]), probability(b["F1"]),
            probability(a["EM"]), probability(b["EM"]),
        )
        if record["delta_class"] != cm.classify_delta(pair.delta, 0):
            raise ValueError(f"{qid}: stored class differs from paired F1 at epsilon=0")
        pairs.append(pair)
    return pairs


def quantile(values, fraction):
    position = fraction * (len(values) - 1)
    index = int(position)
    return values[index] + (position - index) * (values[math.ceil(position)] - values[index])


def candidate_grid(pairs):
    risks = sorted(pair.risk for pair in pairs)
    anchors = [
        (lo, hi)
        for low, high in product(LOW_QUANTILES, HIGH_QUANTILES)
        if (lo := quantile(risks, low)) < (hi := quantile(risks, high))
    ]
    return [
        {"lo": lo, "hi": hi, "bridge_weight": weight}
        for (lo, hi), weight in product(anchors or [(0.0, 1.0)], BRIDGE_WEIGHTS)
    ]


def gate_score(kind, parameters, risk, bridge_absent):
    if kind == "nli_only":
        return risk
    lo, hi = parameters["lo"], parameters["hi"]
    if kind == "fuzzy":
        high = min(1.0, max(0.0, (risk - lo) / (hi - lo)))
    elif kind == "crisp":
        high = float(risk >= (lo + hi) / 2)
    else:
        raise ValueError(f"Unknown gate type: {kind}")
    if bridge_absent is None:
        return high
    weight = parameters["bridge_weight"]
    return (1 - weight) * high + weight * int(bridge_absent)


def sort_key(kind, parameters, qid, risk, bridge_absent):
    score = gate_score(kind, parameters, risk, bridge_absent)
    tie = hashlib.sha256(f"{TIE_SEED}:{qid}".encode()).hexdigest()
    return -score, -risk, tie, qid


def should_retrieve(locked_gate, qid, entailment, bridge_absent):
    key = sort_key(
        locked_gate["kind"], locked_gate["parameters"], qid,
        1 - probability(entailment), bridge_absent,
    )
    return key <= tuple(locked_gate["boundary_sort_key"])


def lock_at_budget(pairs, kind, parameters, k):
    ordering = sorted(
        sort_key(kind, parameters, pair.qid, pair.risk, pair.bridge_absent) for pair in pairs
    )
    return {
        "kind": kind,
        "parameters": parameters,
        "boundary_sort_key": list(ordering[k - 1]),
    }, {key[-1] for key in ordering[:k]}


def prefer(pairs, chosen):
    deltas = [p.delta for p in pairs if p.qid in chosen]
    return math.fsum(deltas), -sum(d < 0 for d in deltas), sum(d > 0 for d in deltas)


def metrics(pairs, chosen):
    labels = Counter(cm.classify_delta(p.delta, 0) for p in pairs if p.qid in chosen)
    size = len(pairs)
    return {
        "f1": math.fsum(p.f1_b if p.qid in chosen else p.f1_a for p in pairs) / size,
        "em": math.fsum(p.em_b if p.qid in chosen else p.em_a for p in pairs) / size,
        "n_retrieved": len(chosen),
        "retrieval_rate": len(chosen) / size,
        "selected_labels": dict.fromkeys(("improved", "tie", "degraded"), 0) | dict(labels),
    }


def calibrate(pairs, k):
    if not 0 < k < len(pairs) or len({p.qid for p in pairs}) != len(pairs):
        raise ValueError("Budget must be internal to the sample and question IDs must be unique")
    grid = candidate_grid(pairs)
    gates = {}
    selections = {}
    for kind in ("fuzzy", "crisp"):
        candidates = (lock_at_budget(pairs, kind, parameters, k) for parameters in grid)
        gates[kind], selections[kind] = max(candidates, key=lambda item: prefer(pairs, item[1]))
    gates["nli_only"], selections["nli_only"] = lock_at_budget(pairs, "nli_only", {}, k)
    selections["never"] = set()
    selections["always"] = {p.qid for p in pairs}
    selections["oracle"] = {p.qid for p in pairs if p.delta > 0}
    summary = {
        "n": len(pairs), "target_count": k, "target_rate": k / len(pairs), "grid_size": len(grid),
        "bridge_counts": {
            "present": sum(p.bridge_absent is False for p in pairs),
            "absent": sum(p.bridge_absent is True for p in pairs),
            "unavailable": sum(p.bridge_absent is None for p in pairs),
        },
        "policies": {name: metrics(pairs, chosen) for name, chosen in selections.items()},
        "fuzzy_crisp_overlap": len(selections["fuzzy"] & selections["crisp"]),
    }
    return gates, summary, selections


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tune", type=Path, required=True)
    parser.add_argument("--branches", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--serve-script", type=Path)
    args = parser.parse_args()
    if sha256(args.tune) != TUNE_SHA256:
        parser.error("The input does not match the locked V2 tune manifest")
    questions = json.loads(args.tune.read_text(encoding="utf-8-sig"))
    branches = [json.loads(line) for line in args.branches.read_text(encoding="utf-8").splitlines() if line.strip()]
    pairs = load_pairs(questions, branches)
    gates, summary, selections = calibrate(pairs, TARGET_COUNT)
    sources = [__file__, pilot.__file__, cm.__file__, cm._BM25_SRC, Path(__file__).with_name("run_pilot.py")]
    lock = {
        "schema": "v2_dev_gate_1",
        "inputs": ["nli_entailment_A", "first_round_full_title_bridge"],
        "tie_seed": TIE_SEED,
        "dev_n": TUNE_SIZE,
        "dev_target_count": TARGET_COUNT,
        "retrieval": {"k": 2, "m": 1},
        "decoding": {"temperature": 0, "max_tokens": 128},
        "answer_model": "Qwen/Qwen2.5-7B-Instruct",
        "answer_model_revision": "a09a35458c702b33eeacc393d103063234e8bc28",
        "nli_model": "MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli",
        "nli_revision": "b3546ea6b0346eb6f8d5d68b13c7dc6d0376b3d7",
        "nli_model_sha256": "c03cd208bf920b4fbbb182a0535859a566e8acc3477d2b536bf87b769978524b",
        "nli_max_tokens": 512,
        "source_sha256": {Path(path).name: sha256(path) for path in sources},
        "tune_sha256": TUNE_SHA256,
        "scored_branches_sha256": sha256(args.branches),
        "gates": gates,
    }
    if args.serve_script:
        lock["serve_script"] = {"name": args.serve_script.name, "sha256": sha256(args.serve_script)}
    args.out.mkdir(parents=True, exist_ok=False)
    write_json(args.out / "locked_gates.json", lock)
    write_json(args.out / "dev_summary.json", summary)
    with (args.out / "dev_selection.csv").open("w", encoding="utf-8", newline="") as stream:
        fields = list(asdict(pairs[0])) + list(selections)
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for pair in pairs:
            writer.writerow(asdict(pair) | {name: pair.qid in chosen for name, chosen in selections.items()})
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

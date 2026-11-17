"""Project the reproducible P3 smoke set into separate P4 inputs and evaluation files."""

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
P3 = HERE.parent / "p3"
V2 = HERE.parents[2] / "exp/v2"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_records(path):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    by_id = {row["qid"]: row for row in rows}
    if len(rows) != len(by_id):
        raise ValueError(f"Duplicate question IDs in {path.name}")
    return by_id


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def write_records(path, rows):
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")


def project(cfg, labels, features, costs, cohorts):
    qids = {qid for group in cohorts.values() for qid in group}
    if (set(labels) != qids or set(features) != qids or set(costs) != qids
            or {name: len(group) for name, group in cohorts.items()} != cfg["n_by_split"]
            or len(qids) != sum(cfg["n_by_split"].values())):
        raise ValueError("P4 inputs differ from the frozen non-overlapping P3 cohorts")
    out_x, out_y, out_cost = [], [], []
    for split, group in cohorts.items():
        for qid in sorted(group):
            label, feature, cost = labels[qid], features[qid], costs[qid]
            if label["split"] != split or cost["split"] != split:
                raise ValueError(f"Split mismatch for {qid}")
            if any(label[field] != feature[field] for field in ("pool_sha256", "a_prompt_sha256")):
                raise ValueError(f"First-round identity mismatch for {qid}")
            if (list(feature["x"]) != cfg["features"] or type(feature["x"]["bridge_absent"]) is not bool
                    or not 0 <= feature["x"]["old_nli_risk"] <= 1):
                raise ValueError(f"Invalid two-feature row for {qid}")
            if not math.isclose(label["b_f1"]-label["a_f1"], label["delta_f1"], abs_tol=1e-12):
                raise ValueError(f"Stored target differs from A/B F1 for {qid}")
            if (cost["nli_input_tokens"] != feature["nli_input_tokens"]
                    or cost["nli_seconds"] != feature["seconds"]):
                raise ValueError(f"Cost refers to a different NLI call for {qid}")
            out_x.append({"qid": qid, "x": feature["x"]})
            out_y.append({key: label[key] for key in ("qid", "split", "a_f1", "b_f1", "a_em", "b_em", "delta_f1")})
            out_cost.append(cost)
    return out_x, out_y, out_cost


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--out", required=True, type=Path)
    args = cli.parse_args()
    cfg = load_json(HERE / "protocol.json")
    raw = P3 / "remote-evidence"
    hashes = {name: value for value, name in map(str.split, (raw / "evidence.sha256").read_text().splitlines())}
    for name in ("features/features.jsonl", "qwen/identity.json", "qwen/pairs.jsonl"):
        if sha(raw / name) != hashes[name]:
            raise ValueError(f"P3 evidence hash mismatch: {name}")
    paths = {"labels": P3 / "analysis/offline_labels.jsonl", "features": raw / "features/features.jsonl",
             "cost": P3 / "analysis/cost.jsonl", "cohorts": P3 / "input/cohorts.json",
             "p3_protocol": P3 / "protocol.json", "p3_run_identity": raw / "qwen/identity.json",
             "p3_evidence": raw / "evidence.sha256", "v2_calibrator": V2 / "calibrate_gates_v2.py",
             "v2_gate": V2 / "step4_dev/gates/locked_gates.json",
             "p4_protocol": HERE / "protocol.json", "p4_preparer": Path(__file__)}
    rows = project(cfg, load_records(paths["labels"]), load_records(paths["features"]),
                   load_records(paths["cost"]), load_json(paths["cohorts"])["qids"])
    args.out.mkdir(parents=True, exist_ok=False)
    files = ("features.jsonl", "targets.jsonl", "cost.jsonl")
    for name, values in zip(files, rows, strict=True):
        write_records(args.out / name, values)
    write_json(args.out / "manifest.json", {
        "n_by_split": dict(Counter(row["split"] for row in rows[1])),
        "features": cfg["features"], "branch": cfg["branch"],
        "upstream_sha256": {name: sha(path) for name, path in paths.items()},
        "inputs_sha256": {name: sha(args.out / name) for name in files},
    })
    print("Frozen P4 features, targets and costs for 150 P3 questions.")


if __name__ == "__main__":
    main()

"""Recompute labels with the official scorer and verify the A-only boundary."""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from statistics import mean, median, quantiles
import sys

from first_round import project_a, validate_a

HERE = Path(__file__).resolve().parent
P1 = HERE.parent / "p1"
P15 = HERE.parent / "p1_5"
P2 = HERE.parent / "p2"
V2 = HERE.parents[2] / "exp/v2"
sys.path[:0] = [str(P1), str(V2)]

from build_pools import digest, file_hash, read_json, write_json, write_rows
from calibrate_gates_v2 import gate_score, should_retrieve
from compare_models import parse_response
from generate_test_v2 import load_official


def jsonl(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def index(rows, qids=None):
    result = {row["qid"]: row for row in rows}
    if len(result) != len(rows) or qids is not None and result.keys() != qids:
        raise ValueError("Missing, extraneous or duplicate question IDs")
    return result


def audit(path, size):
    with path.open(encoding="utf-8") as stream:
        rows = [row for row in csv.DictReader(stream) if int(row["pool_size"]) == size]
    by_key = {(row["qid"], row["path"]): row for row in rows}
    if len(by_key) != len(rows):
        raise ValueError("Duplicate length audit record")
    return by_key


def verify_call(pool, call, locked, cfg):
    chunks = {c["chunk_id"] for c in pool["input"]["contexts"]}
    parsed = parse_response(call["raw"])
    ordered = call["chunk_ids"]
    cited = sorted({ordered[i - 1] for i in parsed["citations"] if 1 <= i <= len(ordered)})
    if (not call["ok"] or locked["pool_sha256"] != pool["pool_sha256"]
            or call["prompt_sha256"] != locked["prompt_sha256"]
            or call["input_tokens"] != int(locked["input_tokens"])
            or ordered != json.loads(locked["ordered_chunk_ids"])
            or not set(ordered) <= chunks or cited != call["cited_chunk_ids"]
            or not 0 <= call["output_tokens"] <= cfg["max_output_tokens"]
            or call["answer"] != parsed["answer"] or call["parse_ok"] != parsed["parse_ok"]):
        raise ValueError(f"Model call does not match the locked input/output for {pool['qid']}")


def branch_labels(official, gold, pool, a, b):
    a_f1, b_f1 = [official.f1_score(x["answer"], gold["answer"])[0] for x in (a, b)]
    return {
        "qid": pool["qid"], "pool_sha256": pool["pool_sha256"], "a_prompt_sha256": a["prompt_sha256"],
        "b_prompt_sha256": b["prompt_sha256"], "a_response_id": a["response_id"],
        "b_response_id": b["response_id"], "a_f1": a_f1, "b_f1": b_f1, "delta_f1": b_f1 - a_f1,
        "a_em": official.exact_match_score(a["answer"], gold["answer"]),
        "b_em": official.exact_match_score(b["answer"], gold["answer"]),
    }


def cohort_summary(rows):
    trigger = [r for r in rows if r["locked_v2_fuzzy_trigger"]]
    counts = Counter("improved" if r["delta_f1"] > 0 else "degraded" if r["delta_f1"] < 0 else "tied" for r in rows)
    return {"n": len(rows), "a_f1": mean(r["a_f1"] for r in rows), "b_f1": mean(r["b_f1"] for r in rows),
            "oracle_f1": mean(max(r["a_f1"], r["b_f1"]) for r in rows),
            "a_em": mean(r["a_em"] for r in rows), "b_em": mean(r["b_em"] for r in rows),
            "mean_delta": mean(r["delta_f1"] for r in rows), "counts": counts,
            "fixed_v2": {"triggered": len(trigger), "triggered_improved": sum(r["delta_f1"] > 0 for r in trigger),
                         "f1": mean(r["b_f1"] if r["locked_v2_fuzzy_trigger"] else r["a_f1"] for r in rows)}}


def development(cfg, official, gate, out):
    size = cfg["pool_size"]
    archive = P15 / "remote-evidence"
    records_path = archive / "results/8192/records.jsonl"
    if [file_hash(records_path), "results/8192/records.jsonl"] not in [
            line.split() for line in (archive / "evidence.sha256").read_text().splitlines()]:
        raise ValueError("P1.5 raw record hash mismatch")
    p1 = P1 / "artifacts"
    pools = index([row for row in jsonl(p1 / "pools.jsonl") if row["pool_size"] == size])
    qids = set(pools)
    rows = [r for r in jsonl(records_path) if r["ok"] and r["phase"] == "experiment" and r["pool_size"] == size]
    previous = {method: index([r for r in rows if r["route"] == method], qids)
                for method in ("top2", "2plus4")}
    with (P15 / "analysis/per_question.csv").open(encoding="utf-8") as stream:
        f1 = {(r["qid"], r["route"]): float(r["f1"]) for r in csv.DictReader(stream) if int(r["pool_size"]) == size}
    gold = index(jsonl(p1 / "evaluation_only/gold.jsonl"), qids)
    lengths = audit(p1 / "length_audit.csv", size)
    panel = index(jsonl(P2 / "input/panel.jsonl"), qids)
    nli = index(jsonl(P2 / "guided-evidence/live-nli/nli.jsonl"), qids)
    features, labels = [], []
    for qid, pool in sorted(pools.items()):
        (a,) = previous["top2"][qid]["calls"]
        b = previous["2plus4"][qid]["calls"][-1]
        for call in (a, b):
            verify_call(pool, call, lengths[qid, call["prompt_path"]], cfg)
        projected = project_a(pool, a, parse_response)
        validate_a(projected)
        old = nli[qid]
        if projected != panel[qid] or any(projected[k] != old[k] for k in ("pool_sha256", "a_prompt_sha256")):
            raise ValueError("P2 and P1.5 used different first-round inputs")
        e = old["old_whole"]["probs"]["entailment"]
        bridge = old["bridge_matches"]
        absent = None if bridge is None else not bridge
        x = {"old_nli_risk": 1-e, "bridge_absent": absent}
        fixed = gate_score(gate["kind"], gate["parameters"], 1-e, absent)
        if fixed != old["signals"]["old_nli_bridge"] or x["old_nli_risk"] != old["signals"]["old_nli_risk"]:
            raise ValueError("P2 original signal replay mismatch")
        features.append({"qid": qid, "pool_sha256": pool["pool_sha256"], "a_prompt_sha256": a["prompt_sha256"],
                         "first_round_sha256": digest(projected), "x": x, "locked_v2_fuzzy_score": fixed,
                         "locked_v2_fuzzy_trigger": should_retrieve(gate, qid, e, absent)})
        label = branch_labels(official, gold[qid], pool, a, b)
        if (label["a_f1"], label["b_f1"]) != (f1[qid, "top2"], f1[qid, "2plus4"]):
            raise ValueError("P1.5 official scores cannot be replicated")
        labels.append(label)
    out.mkdir(parents=True, exist_ok=True)
    write_rows(out / "first_round_features.jsonl", features)
    write_rows(out / "offline_labels.jsonl", labels)
    write_json(out / "summary.json", {"status": "development_replay", "features_from_p2": True,
                     "timing": "no inference or timing remeasurement", **cohort_summary([label | feature for label, feature in zip(labels, features, strict=True)])})
    print(f"Recomputed {len(labels)} development A/B labels and matched all original scores and A-only signals.")


def times(values):
    return {"mean": mean(values), "p50": median(values), "p95": quantiles(values, n=100, method="inclusive")[94]}


def smoke(cfg, official, gate, raw, out):
    size = cfg["pool_size"]
    inputs = HERE / "input"
    manifest = read_json(inputs / "manifest.json")
    names = ("pools.jsonl", "lengths.csv", "cohorts.json", "evaluation_only/gold.jsonl")
    for name in names:
        if file_hash(inputs / name) != manifest["files_sha256"][name]:
            raise ValueError(f"P3 frozen input differs: {name}")
    cohorts = read_json(inputs / "cohorts.json")["qids"]
    split_by_id = {qid: split for split, qids in cohorts.items() for qid in qids}
    qids = set(split_by_id)
    pools = index(jsonl(inputs / "pools.jsonl"), qids)
    gold = index(jsonl(inputs / "evaluation_only/gold.jsonl"), qids)
    lengths = audit(inputs / "lengths.csv", size)
    journal = jsonl(raw / "qwen/pairs.jsonl")
    pairs = index([r for r in journal if r["ok"]], qids)
    projections = index(jsonl(raw / "qwen/first_round.jsonl"), qids)
    features = index(jsonl(raw / "features/features.jsonl"), qids)
    if read_json(raw / "features/complete.json")["first_round_sha256"] != file_hash(raw / "qwen/first_round.jsonl"):
        raise ValueError("Feature job used a different first-round file")
    offline, cost = [], []
    for qid, pool in sorted(pools.items()):
        row = pairs[qid]
        a, b = row["calls"]
        if (row["phase"] != "p3_smoke" or row["pool_size"] != size or row["pool_sha256"] != pool["pool_sha256"]
                or (a["prompt_path"], b["prompt_path"]) != ("top2", "2plus4")
                or b["chunk_ids"][:2] != a["chunk_ids"] or len(b["chunk_ids"]) != 6 or len(set(b["chunk_ids"])) != 6):
            raise ValueError(f"P3 route identity mismatch for {qid}")
        for call in (a, b):
            verify_call(pool, call, lengths[qid, call["prompt_path"]], cfg)
        projected = project_a(pool, a, parse_response)
        validate_a(projected)
        feature = features[qid]
        if (projected != projections[qid] or feature["first_round_sha256"] != digest(projected)
                or any(feature[k] != projected[k] for k in ("pool_sha256", "a_prompt_sha256"))
                or list(feature["x"]) != cfg["features"]):
            raise ValueError(f"Feature evidence outside first-round whitelist for {qid}")
        e = feature["nli"]["probs"]["entailment"]
        absent = feature["x"]["bridge_absent"]
        if (feature["x"]["old_nli_risk"] != 1-e or feature["locked_v2_fuzzy_trigger"] != should_retrieve(gate, qid, e, absent)
                or feature["locked_v2_fuzzy_score"] != gate_score(gate["kind"], gate["parameters"], 1-e, absent)):
            raise ValueError("Frozen V2 gate cannot be replayed")
        offline.append({"split": split_by_id[qid], **branch_labels(official, gold[qid], pool, a, b)})
        cost.append({"qid": qid, "split": split_by_id[qid], "a_input_tokens": a["input_tokens"],
                     "b_input_tokens": b["input_tokens"], "a_output_tokens": a["output_tokens"],
                     "b_output_tokens": b["output_tokens"], "a_http_seconds": sum(t["seconds"] for t in a["attempts"]),
                     "b_http_seconds": sum(t["seconds"] for t in b["attempts"]), "pair_elapsed_seconds": row["elapsed_seconds"],
                     "nli_input_tokens": feature["nli_input_tokens"], "nli_seconds": feature["seconds"]})
    calls = [call for row in journal for call in row["calls"]]
    observed = {split: cohort_summary([label | features[label["qid"]] for label in offline if label["split"] == split])
                for split in cohorts}
    summary = {
        "n": len(qids), "cohorts": observed, "successful_pairs": len(pairs),
        "failure_records": len(journal)-len(pairs), "qwen_requests": sum(len(c["attempts"]) for c in calls),
        "qwen_parsing_failures": sum(c["ok"] and not c["parse_ok"] for c in calls),
        "qwen_invalid_citations": sum(c.get("invalid_citations", 0) for c in calls),
        "qwen_output_limits": sum(c.get("finish_reason") == "length" for c in calls),
        "qwen_input_tokens": sum(c.get("input_tokens", 0) for c in calls),
        "qwen_output_tokens": sum(c.get("output_tokens", 0) for c in calls),
        "qwen_batches_wall_seconds": sum(r["seconds"] for r in jsonl(raw / "qwen/batches.jsonl")),
        "pair_wall_seconds": times([r["pair_elapsed_seconds"] for r in cost]),
        "a_http_wall_seconds": times([r["a_http_seconds"] for r in cost]),
        "b_http_wall_seconds": times([r["b_http_seconds"] for r in cost]),
        "nli_wall_seconds": times([r["nli_seconds"] for r in cost]),
        "nli_input_tokens": sum(r["nli_input_tokens"] for r in cost),
        "nli_truncated_n": sum(f["nli"]["truncated"] for f in features.values()),
        "nli_premise_fallbacks": sum(f["retrieved_premise_fallback"] for f in features.values()),
        "bridge_unavailable_n": sum(f["x"]["bridge_absent"] is None for f in features.values()),
        "warmup_calls": sum(len(r["calls"]) for r in jsonl(raw / "qwen/warmups.jsonl")),
    }
    out.mkdir(parents=True, exist_ok=True)
    write_rows(out / "offline_labels.jsonl", offline)
    write_rows(out / "cost.jsonl", cost)
    write_json(out / "summary.json", summary)
    print(f"Recomputed all {len(qids)} train/validation labels, matched A-only feature hashes, and measured real pair costs.")


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--raw", type=Path, help="If absent, replay the existing development cache")
    cli.add_argument("--out", type=Path, required=True)
    args = cli.parse_args()
    cfg = read_json(HERE / "protocol.json")
    scorer = V2 / "step5_v2/hotpot_evaluate_v1.py"
    if file_hash(scorer) != cfg["qa_scorer_sha256"]:
        raise ValueError("HotpotQA scorer hash mismatch")
    official = load_official(scorer)
    gate = read_json(V2 / "step4_dev/gates/locked_gates.json")["gates"]["fuzzy"]
    if args.raw:
        smoke(cfg, official, gate, args.raw, args.out)
    else:
        development(cfg, official, gate, args.out)


if __name__ == "__main__":
    main()

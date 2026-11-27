"""Seal a fresh bridge sample with the unchanged P1 distractor construction."""
from itertools import combinations
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
V3 = ROOT / "exp/v3"
P1 = V3 / "p1"
P5 = V3 / "p5"
sys.path[:0] = [str(P1), str(ROOT / "exp/v2")]

from build_pools import (BM25Okapi, Chunk, ParquetFile, audit_labels, digest, duplicate,
                         expand_pool, file_hash, read_json, train_donors, write_json, write_rows)
from bm25_topk import para_text, tok


def historical_ids():
    p0 = read_json(V3 / "p0/manifest.json")
    p3 = read_json(V3 / "p3/input/cohorts.json")["qids"]
    p5 = read_json(P5 / "input/split.json")
    history = {q for ids in p0["historical_ids_by_split"].values() for q in ids}
    history.update(p0["additional_upstream_ids_in_scanned_artifacts"])
    history.update(read_json(P1 / "artifacts/split_plan.json")["development"]["qids"])
    history.update(q for ids in p3.values() for q in ids)
    history.update(p5["primary_qids"])
    return history


def main():
    cfg = read_json(P1 / "config.json")
    cfg["sizes"] = [30]
    protocol = read_json(HERE / "fresh_protocol.json")
    data = HERE / "data"
    validation = data / "validation.parquet"
    shards = [data / n for n in cfg["train_sha256"]]
    hashes = {validation: cfg["validation_sha256"], **{p: cfg["train_sha256"][p.name] for p in shards}}
    for path, expected in hashes.items():
        if file_hash(path) != expected:
            raise ValueError(f"Dataset identity mismatch for {path}")
    bank = ParquetFile(validation)
    val_ids = set(bank.read(columns=["id"])["id"].to_pylist())
    donors, index = train_donors(shards, val_ids, cfg)
    if index != read_json(P1 / "artifacts/pool_manifest.json")["dataset"]:
        raise ValueError("Donor index differs from P1")
    print(f"Exact P1 donor index recovered: {len(donors)}", flush=True)
    bm25 = BM25Okapi([tok(para_text(c.title, c.sentences)) for c, _, _ in donors])
    excluded = historical_ids()
    candidates = [r for r in bank.read().to_pylist() if r["type"] == "bridge" and r["id"] not in excluded]
    namespace = protocol["draw_namespace"]
    candidates.sort(key=lambda item: digest([namespace, item["id"]]))
    pools, gold, prov = [], [], []
    for r in candidates:
        qid = r["id"]
        contents = list(zip(r["context"]["title"], r["context"]["sentences"], strict=True))
        if len(contents) != 10:
            continue
        base = [Chunk.from_text(*p) for p in contents]
        if any(duplicate(a, b, cfg["near_duplicate"]) for a, b in combinations(base, 2)):
            continue
        title_text = dict(contents)
        supports = list(zip(r["supporting_facts"]["title"], r["supporting_facts"]["sent_id"], strict=True))
        if not supports or any(t not in title_text or not 0 <= i < len(title_text[t]) for t, i in supports):
            continue
        item = {"_id": qid, "question": r["question"], "answer": r["answer"], "supporting_facts": supports}
        chunks, origins = expand_pool(qid, r["question"], base, donors, bm25, tok, cfg)
        ordered = sorted(chunks, key=lambda chunk: digest(["presentation", cfg["presentation_seed"], qid, chunk.chunk_id]))
        payload = {"question": r["question"], "contexts": [c.as_online() for c in ordered]}
        pools.append({"qid": qid, "pool_size": 30, "pool_sha256": digest(payload), "input": payload})
        label, _ = audit_labels(item, base, [], [])
        gold.append(label)
        prov.append({"qid": qid, "selection_order": origins})
        print(f"frozen {len(pools)}/{protocol['n']}", flush=True)
        if len(pools) == protocol["n"]:
            break
    if len(pools) != protocol["n"]:
        raise ValueError("Incomplete fresh cohort")
    assert not excluded.intersection(r["qid"] for r in pools)
    out = HERE / "fresh"
    out.mkdir(exist_ok=False)
    write_rows(out / "pools.jsonl", pools)
    write_rows(out / "evaluation_gold.jsonl", gold)
    write_rows(out / "provenance.jsonl", prov)
    write_json(out / "manifest.json", {
        "qids": [r["qid"] for r in pools], "archived_exclusions": len(excluded),
        "policy_training_summary_sha256": file_hash(HERE / "summary.json"),
        "constraint_code_sha256": file_hash(HERE / "constraints.py"),
        "donor_index_sha256": index["donor_index_sha256"],
        "protocol_sha256": file_hash(HERE / "fresh_protocol.json"),
        "pool_sha256": file_hash(out / "pools.jsonl"),
        "gold_sha256": file_hash(out / "evaluation_gold.jsonl"),
    })


if __name__ == "__main__":
    main()

"""Seal the P5 data set before inference using adjacency, identity and length checks."""

import argparse
from collections import Counter
import csv
from itertools import combinations
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
V3 = HERE.parent
REPO = HERE.parents[2]
V2 = REPO / "exp/v2"
P1 = V3 / "p1"
sys.path[:0] = [str(P1), str(V2)]

from build_pools import (BM25Okapi, Chunk, ParquetFile, audit_labels, digest, duplicate, expand_pool,
                         file_hash, read_json, train_donors, write_json, write_rows)
from bm25_topk import para_text, tok
import compare_models as v2
from routes import answer_messages, example_from_pool, route_indices


def lengths_for(row, tokenizer, config):
    ex = example_from_pool(row)
    audit = []
    for route in config["shared_routes"]:
        ids = route_indices(v2, ex, route)
        messages = answer_messages(v2, ex, ids, route)
        count = len(tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True))
        audit.append({"qid": row["qid"], "pool_size": row["pool_size"], "pool_sha256": row["pool_sha256"], "route": route,
                      "input_tokens": count, "total_tokens": count + config["max_output_tokens"],
                      "prompt_sha256": digest(messages), "chunk_ids": [row["input"]["contexts"][i]["chunk_id"] for i in ids]})
    return audit


def shape(item):
    context = item["context"]
    sp = item["supporting_facts"]
    return {"_id": item["id"], "question": item["question"], "answer": item["answer"], "type": item["type"],
            "context": list(zip(context["title"], context["sentences"], strict=True)),
            "supporting_facts": list(zip(sp["title"], sp["sent_id"], strict=True))}


def render(qid, question, chunks, size, policy):
    ordered = sorted(chunks[:size], key=lambda chunk: digest(["presentation", policy["presentation_seed"], qid, chunk.chunk_id]))
    payload = {"question": question, "contexts": [chunk.as_online() for chunk in ordered]}
    return {"qid": qid, "pool_size": size, "pool_sha256": digest(payload), "input": payload}


def draw(config, prior, candidates, donors, tokenizer):
    size = config["primary_size"]
    services = config["services"]
    other_sizes = config["secondary_sizes"]
    ranker = BM25Okapi([tok(para_text(chunk.title, chunk.sentences)) for chunk, _, _ in donors])
    ordered_ids = sorted(candidates, key=lambda qid: digest(["p5-final", config["draw_seed"], qid]))
    eligible, exclusions, pool_rows, lengths, secondary_ready, gold, provenance = [], [], [], [], [], [], []

    for qid in ordered_ids:
        item = shape(candidates[qid])
        base = [Chunk.from_text(*p) for p in item["context"]]
        title_text = dict(item["context"])
        if len(base) != 10:
            reason = "original_paragraph_count"
        elif any(duplicate(a, b, prior["near_duplicate"]) for a, b in combinations(base, 2)):
            reason = "original_near_duplicate"
        elif (not item["supporting_facts"] or any(title not in title_text or not 0 <= i < len(title_text[title])
                                                    for title, i in item["supporting_facts"])):
            reason = "unresolvable_reference_label"
        else:
            reason = None
        if reason:
            exclusions.append({"qid": qid, "reason": reason})
            continue
        chunks, origins = expand_pool(qid, item["question"], base, donors, ranker, tok, prior)
        main = render(qid, item["question"], chunks, size, prior)
        main_lengths = lengths_for(main, tokenizer, config)
        if max(x["total_tokens"] for x in main_lengths) > services[str(size)]["context"]:
            exclusions.append({"qid": qid, "reason": "primary_context_limit"})
            continue
        primary_label, _ = audit_labels(item, base, (), ())
        gold.append(primary_label)
        eligible.append(qid)
        pool_rows.append(main)
        lengths.extend(main_lengths)
        provenance.append({"qid": qid, "selection_order": origins})

        sides = [render(qid, item["question"], chunks, small, prior) for small in other_sizes]
        ans = [lengths_for(side, tokenizer, config) for side in sides]
        if all(max(x["total_tokens"] for x in leg) <= services[str(leg[0]["pool_size"])]["context"] for leg in ans):
            secondary_ready.append((qid, sides, ans))
        if len(eligible) == config["primary_n"]:
            break

    if len(eligible) != config["primary_n"] or len(secondary_ready) < config["secondary_n"]:
        raise ValueError("Frozen sample sizes are infeasible under the length and data criteria")
    secondary = sorted(secondary_ready, key=lambda row: digest(["p5-secondary", config["draw_seed"], row[0]]))[:config["secondary_n"]]
    for qid, sides, ans in secondary:
        main_order = next(r["input"]["contexts"] for r in pool_rows if r["qid"] == qid and r["pool_size"] == size)
        ordered = sorted([main_order, *(r["input"]["contexts"] for r in sides)], key=len)
        for a, b in zip(ordered, ordered[1:]):
            subset = {c["chunk_id"] for c in a}
            if [c["chunk_id"] for c in b if c["chunk_id"] in subset] != [c["chunk_id"] for c in a]:
                raise ValueError(f"Nested candidate sequence corrupted for {qid}")
        pool_rows.extend(sides)
        lengths.extend(item for estimates in ans for item in estimates)
    human = sorted(eligible, key=lambda qid: digest(["p5-human", config["draw_seed"], qid]))[:config["human_n"]]
    split = {"primary_size": size, "primary_qids": eligible, "secondary_qids": [r[0] for r in secondary],
             "secondary_sizes": other_sizes, "n_primary_also_fits_secondary": len(secondary_ready),
             "timing_qids": sorted(eligible, key=lambda qid: digest(["p5-timing", config["draw_seed"], qid]))[:config["timing_n"]],
             "human_qids": human,
             "human_dual_qids": sorted(human, key=lambda qid: digest(["p5-human-dual", config["draw_seed"], qid]))[:config["human_dual_n"]],
             "excluded_before_primary_quota": exclusions}
    return split, pool_rows, lengths, gold, provenance


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--train-dir", required=True, type=Path)
    cli.add_argument("--validation", required=True, type=Path)
    cli.add_argument("--tokenizer", required=True, type=Path)
    cli.add_argument("--out", required=True, type=Path)
    args = cli.parse_args()
    from transformers import AutoTokenizer

    config = read_json(HERE / "protocol.json")
    prior = read_json(P1 / "config.json")
    p0file = V3 / "p0/manifest.json"
    p0 = read_json(p0file)
    shards = [args.train_dir / name for name in prior["train_sha256"]]
    source = {path: prior["train_sha256"][path.name] for path in shards}
    source[args.validation] = prior["validation_sha256"]
    source.update({args.tokenizer / name: sha for name, sha in p0["tokenizer_files"].items()})
    if any(file_hash(path) != digest for path, digest in source.items()):
        raise ValueError("Frozen dataset/tokenizer artifact mismatch")
    historical = {qid for group in p0["historical_ids_by_split"].values() for qid in group}
    historical.update(p0["additional_upstream_ids_in_scanned_artifacts"])
    p3_cohorts = read_json(V3 / "p3/input/cohorts.json")["qids"]
    if not all(set(ids) <= historical for ids in p3_cohorts.values()):
        raise ValueError("New P3 development IDs must be added to the audited historical list")
    val_data = ParquetFile(args.validation)
    validation = val_data.read(columns=["id", "type"]).to_pylist()
    val_ids = {row["id"] for row in validation}
    bridges = {row["id"] for row in validation if row["type"] == "bridge"} - historical
    expected = read_json(P1 / "artifacts/split_plan.json")["final"]["bridge_qid_count_outside_audited_history"]
    if len(bridges) != expected:
        raise ValueError("History conflicts with the previously audited candidate count")
    candidates = {row["id"]: row for row in val_data.read(columns=["id", "type", "answer", "question", "context", "supporting_facts"]).to_pylist()
                  if row["id"] in bridges}
    donors, index = train_donors(shards, val_ids, prior)
    if index != read_json(P1 / "artifacts/pool_manifest.json")["dataset"]:
        raise ValueError("Donor index differs from the audited P1 corpus")
    tokenizer = AutoTokenizer.from_pretrained(str(args.tokenizer), local_files_only=True)
    split, pools, lengths, gold, prov = draw(config, prior, candidates, donors, tokenizer)
    assert historical.isdisjoint(split["primary_qids"])
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "evaluation_only").mkdir()
    write_json(args.out / "split.json", split)
    for name, values in {"pools.jsonl": pools, "lengths.jsonl": lengths,
                          "evaluation_only/gold.jsonl": gold, "provenance.jsonl": prov}.items():
        write_rows(args.out / name, values)
    write_json(args.out / "manifest.json", {
        "seal": "pre-score, IDs and length filter frozen",
        "config_sha256": file_hash(HERE / "protocol.json"), "history_sha256": file_hash(p0file),
        "source_sha256": {path.name: digest for path, digest in source.items()},
        "donor_index": index, "eligible_bridge_before_content_filter": len(candidates),
        "historical_excluded_ids": len(historical), "history_attestation": config["history_attestation"],
        "counts_by_size": dict(Counter(row["pool_size"] for row in pools)),
        "max_total_by_size": {s: max(r["total_tokens"] for r in lengths if str(r["pool_size"]) == s) for s in config["services"]},
        "excluded_before_quota": dict(Counter(row["reason"] for row in split["excluded_before_primary_quota"])),
        "frozen_code_sha256": {str(path.relative_to(REPO)): file_hash(path) for path in (
            Path(__file__), HERE / "routes.py", P1 / "build_pools.py", V2 / "compare_models.py", V2 / "bm25_topk.py")},
        "files_sha256": {str(path.relative_to(args.out)): file_hash(path)
                         for path in sorted(args.out.rglob("*")) if path.is_file()},
    })
    print(f"P5 sealed {len(split['primary_qids'])} primary and {len(split['secondary_qids'])} paired secondary questions.")


if __name__ == "__main__":
    main()

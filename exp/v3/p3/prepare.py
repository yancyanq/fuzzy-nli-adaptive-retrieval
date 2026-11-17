"""Freeze P3 fallback cohorts, candidate pools and prompt lengths from locked sources."""

import argparse
from collections import Counter
import csv
from itertools import combinations
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
P1 = HERE.parent / "p1"
REPO = HERE.parents[2]
V2 = REPO / "exp/v2"
sys.path[:0] = [str(P1), str(V2)]

from audit_lengths import prompt_lengths, read_pools
from build_pools import (BM25Okapi, Chunk, ParquetFile, audit_labels, digest, duplicate,
                         expand_pool, file_hash, read_json, train_donors, write_json, write_rows)
import compare_models as v2
from bm25_topk import para_text, tok


def freeze_cohorts(plan, archived, config, counts):
    cohorts, skips, additions = {}, {}, {}
    dev = set(plan["development"]["qids"])
    for split, key in (("train", "conditional_gate_train"), ("validation", "conditional_gate_validation")):
        selection, skipped = [], []
        for qid in plan[key]["qids"]:
            row = archived[qid]
            base = [Chunk.from_text(*p) for p in row["context"]]
            if row["type"] != "bridge" or len(base) != 10:
                reason = "not_bridge_with_ten_original_paragraphs"
            elif any(duplicate(a, b, config["near_duplicate"]) for a, b in combinations(base, 2)):
                reason = "base_duplicate"
            else:
                reason = None
            if reason:
                skipped.append({"qid": qid, "reason": reason})
                continue
            selection.append((qid, base))
            if len(selection) == counts[split]:
                break
        if len(selection) != counts[split] or dev & {qid for qid, _ in selection}:
            raise ValueError("Insufficient or overlapping eligible P3 questions")
        baseline = set(plan[key]["smoke_qids"])
        cohorts[split] = selection
        skips[split] = skipped
        additions[split] = [qid for qid, _ in selection if qid not in baseline]
    if {qid for qid, _ in cohorts["train"]} & {qid for qid, _ in cohorts["validation"]}:
        raise ValueError("P3 split overlap")
    return cohorts, skips, additions


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--train-dir", type=Path, required=True)
    cli.add_argument("--validation", type=Path, required=True, help="Only the upstream ID column is read")
    cli.add_argument("--tokenizer", type=Path, required=True)
    cli.add_argument("--out", type=Path, required=True)
    args = cli.parse_args()
    from transformers import AutoTokenizer

    cfg = read_json(HERE / "protocol.json")
    policy = read_json(P1 / "config.json")
    p1_art = P1 / "artifacts"
    p1_manifest = read_json(p1_art / "pool_manifest.json")
    plan_path = p1_art / "split_plan.json"
    plan = read_json(plan_path)
    p0 = read_json(HERE.parent / "p0/manifest.json")
    tune = REPO / p0["input_splits"]["tune"]["path"]
    shards = [args.train_dir / name for name in policy["train_sha256"]]
    sources = {tune: p0["input_splits"]["tune"]["sha256"],
               plan_path: p1_manifest["files_sha256"]["split_plan.json"],
               args.validation: policy["validation_sha256"],
               **{path: policy["train_sha256"][path.name] for path in shards},
               **{args.tokenizer / name: expected for name, expected in p0["tokenizer_files"].items()}}
    for file, expected in sources.items():
        if file_hash(file) != expected:
            raise ValueError(f"Input hash mismatch: {file}")
    archived = {row["_id"]: row for row in read_json(tune)}
    cohorts, skipped, additions = freeze_cohorts(plan, archived, policy, cfg["n_by_split"])
    validation_ids = set(ParquetFile(args.validation).read(columns=["id"])["id"].to_pylist())
    donors, donor_manifest = train_donors(shards, validation_ids, policy)
    if donor_manifest != p1_manifest["dataset"]:
        raise ValueError("P3 donor index must match P1 exactly")
    ranker = BM25Okapi([tok(para_text(chunk.title, chunk.sentences)) for chunk, _, _ in donors])
    pool_size = cfg["pool_size"]
    pool_policy = {**policy, "sizes": [pool_size]}
    pools, provenance, gold, phrase_review = [], [], [], []
    for split, selection in cohorts.items():
        for qid, base in selection:
            item = archived[qid]
            chunks, origins = expand_pool(qid, item["question"], base, donors, ranker, tok, pool_policy)
            expected_modes = Counter(original=10, bm25=10, random=10)
            if len({chunk.chunk_id for chunk in chunks}) != pool_size or Counter(r["mode"] for r in origins) != expected_modes:
                raise ValueError(f"Unexpected P3 pool for {qid}")
            ordered = sorted(chunks, key=lambda chunk: digest(["presentation", policy["presentation_seed"], qid, chunk.chunk_id]))
            payload = {"question": item["question"], "contexts": [chunk.as_online() for chunk in ordered]}
            pools.append({"qid": qid, "pool_size": pool_size, "pool_sha256": digest(payload), "input": payload})
            provenance.append({"qid": qid, "split": split, "selection_order": origins})
            # Audit labels after material selection. They never influence its ordering or membership.
            label, phrase_matches = audit_labels(item, base, chunks[len(base):], origins[len(base):])
            gold.append(label)
            phrase_review.extend(phrase_matches)
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "evaluation_only").mkdir()
    for name, records in {"pools.jsonl": pools, "provenance.jsonl": provenance,
                          "evaluation_only/gold.jsonl": gold,
                          "evaluation_only/phrase_review.jsonl": phrase_review}.items():
        write_rows(args.out / name, records)
    split_qids = {split: [qid for qid, _ in selection] for split, selection in cohorts.items()}
    write_json(args.out / "cohorts.json", {"qids": split_qids, "skipped_before_quota": skipped, "substitutes": additions})
    tokenizer = AutoTokenizer.from_pretrained(str(args.tokenizer), local_files_only=True)
    lengths = prompt_lengths(read_pools(args.out / "pools.jsonl"), tokenizer, v2, cfg["max_output_tokens"])
    paths = {"top2", cfg["routes"]["2plus4"]["prompt_path"]}
    lengths = [row for row in lengths if row["path"] in paths]
    if len(lengths) != 2 * len(pools) or any(row["total_tokens"] > cfg["context"] for row in lengths):
        raise ValueError("P3 prompt does not fit the locked context")
    with (args.out / "lengths.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(lengths[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(lengths)
    write_json(args.out / "manifest.json", {
        "inputs_sha256": {file.name: expected for file, expected in sources.items()},
        "locked_code_sha256": {str(f.relative_to(REPO)): file_hash(f) for f in (
            Path(__file__), HERE / "protocol.json", P1 / "config.json", P1 / "build_pools.py",
            P1 / "audit_lengths.py", V2 / "compare_models.py", V2 / "bm25_topk.py")},
        "donor_index": donor_manifest,
        "n_by_split": {key: len(qids) for key, qids in split_qids.items()},
        "max_total_by_path": {path: max(row["total_tokens"] for row in lengths if row["path"] == path)
                              for path in sorted(paths)},
        "total_prompt_tokens": sum(row["input_tokens"] for row in lengths),
        "phrase_audit_records": len(phrase_review),
        "files_sha256": {str(path.relative_to(args.out)): file_hash(path)
                         for path in sorted(args.out.rglob("*")) if path.is_file()},
    })
    substitute_counts = {split: len(qids) for split, qids in additions.items()}
    print(f"Frozen {len(pools)} pools and {len(lengths)} Qwen prompts; substitutes: {substitute_counts}")


if __name__ == "__main__":
    main()

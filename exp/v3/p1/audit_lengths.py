"""Measure untruncated P1 prompts and precompute common samples by token cap."""

import argparse
import csv
import json
from pathlib import Path
import sys

import tokenizers
import transformers

from build_pools import HERE, REPO, digest, file_hash, read_json, write_json


def read_pools(path):
    pools = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if set(row) != {"qid", "pool_size", "pool_sha256", "input"}:
                raise ValueError("Unexpected online pool metadata field")
            payload = row["input"]
            if set(payload) != {"question", "contexts"} or len(payload["contexts"]) != row["pool_size"]:
                raise ValueError("Unexpected input fields or incorrect context count")
            for chunk in payload["contexts"]:
                if set(chunk) != {"chunk_id", "title", "sentences"}:
                    raise ValueError("Unexpected online paragraph fields")
                for i, sentence in enumerate(chunk["sentences"]):
                    if set(sentence) != {"sentence_id", "text"} or sentence["sentence_id"] != f"{chunk['chunk_id']}:{i}":
                        raise ValueError("Unexpected online sentence fields or ID")
            if digest(payload) != row["pool_sha256"]:
                raise ValueError(f"Pool hash mismatch for {row['qid']} / {row['pool_size']}")
            pools.append(row)
    return pools


def prompt_lengths(pools, tokenizer, v2, reserve):
    rows = []
    for row in pools:
        payload = row["input"]
        contexts = payload["contexts"]
        example = {"question": payload["question"],
                   "context": [[chunk["title"], [sentence["text"] for sentence in chunk["sentences"]]]
                               for chunk in contexts]}
        rank, _ = v2.retrieve_indices(example, 6, 0)
        a, b = v2.retrieve_indices(example, 2, 4)
        if rank[:2] != a or len(b) != 4:
            raise ValueError("Unexpected V2 retrieval output")
        routes = {
            "top2": a, "top4": rank[:4], "top6": rank,
            "2plus1": a + b[:1], "2plus2": a + b[:2], "2plus4": a + b,
            "full": list(range(len(contexts))),
        }
        for route, indices in routes.items():
            messages = v2.build_messages(example, indices)
            input_tokens = len(tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True))
            rows.append({
                "qid": row["qid"], "pool_size": row["pool_size"], "pool_sha256": row["pool_sha256"],
                "path": route, "input_tokens": input_tokens, "output_reserved": reserve,
                "total_tokens": input_tokens + reserve, "paragraphs_read": len(indices),
                "ordered_chunk_ids": json.dumps([contexts[i]["chunk_id"] for i in indices], separators=(",", ":")),
                "prompt_sha256": digest(messages),
            })
    return rows


def by_capacity(rows, config):
    routes = config["primary_preflight_paths"]
    paths = routes + config["optional_preflight_paths"]
    results = {}
    for size in config["sizes"]:
        by_qid = {}
        for row in rows:
            if row["pool_size"] == size:
                by_qid.setdefault(row["qid"], {})[row["path"]] = row
        if len(by_qid) != config["dev_n"] or any(set(per_qid) != set(paths) for per_qid in by_qid.values()):
            raise ValueError("Length audit has missing questions or paths")
        maximum = {path: max(results[path]["total_tokens"] for results in by_qid.values()) for path in paths}
        sizes = {}
        for cap in config["audited_context_limits"]:
            eligible = []
            excluded = []
            fit = dict.fromkeys(paths, 0)
            for qid, measurements in by_qid.items():
                too_long = [path for path in routes if measurements[path]["total_tokens"] > cap]
                if too_long:
                    excluded.append({"qid": qid, "paths": too_long})
                else:
                    eligible.append(qid)
                for path in paths:
                    fit[path] += int(measurements[path]["total_tokens"] <= cap)
            sizes[str(cap)] = {
                "fit_count_by_path": fit, "common_eligible_qids": eligible, "exclusions": excluded,
                "primary_shared_answer_calls": len(eligible) * len(routes),
                "primary_shared_prompt_tokens": sum(
                    by_qid[qid][path]["input_tokens"] for qid in eligible for path in routes
                ),
            }
        results[str(size)] = {"maximum_total_by_path": maximum, "candidates_by_context_limit": sizes}
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    config = read_json(HERE / "config.json")
    history = read_json(HERE.parent / "p0/manifest.json")
    manifest = read_json(args.artifacts / "pool_manifest.json")
    path = args.artifacts / "pools.jsonl"
    if manifest["files_sha256"][path.name] != file_hash(path):
        raise ValueError("Pool file SHA-256 differs from the P1 build manifest")
    tokenizer_hashes = {name: file_hash(args.tokenizer / name) for name in history["tokenizer_files"]}
    if config["qwen_revision"] != history["qwen_revision"] or tokenizer_hashes != history["tokenizer_files"]:
        raise ValueError("Qwen tokenizer identity does not match P0")
    tokenizer = transformers.AutoTokenizer.from_pretrained(str(args.tokenizer), local_files_only=True)
    sys.path.insert(0, str(REPO / "exp/v2"))
    import compare_models as v2

    pools = read_pools(path)
    rows = prompt_lengths(pools, tokenizer, v2, config["answer_reservation_tokens"])
    by_limit = by_capacity(rows, config)
    length_path = args.artifacts / "length_audit.csv"
    with length_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    write_json(args.artifacts / "length_manifest.json", {
        "status": "offline_lengths_measured_live_gpu_unverified",
        "pools_sha256": file_hash(path), "csv_sha256": file_hash(length_path),
        "auditor_sha256": file_hash(Path(__file__)),
        "config_sha256": file_hash(HERE / "config.json"),
        "v2_prompt_and_retrieval_source_sha256": file_hash(REPO / "exp/v2/compare_models.py"),
        "tokenizer_files": tokenizer_hashes, "qwen_revision": config["qwen_revision"],
        "transformers": transformers.__version__, "tokenizers": tokenizers.__version__,
        "reserved_output_tokens": config["answer_reservation_tokens"],
        "primary_paths": config["primary_preflight_paths"],
        "optional_paths": config["optional_preflight_paths"],
        "measured_prompt_records": len(rows), "scales": by_limit,
    })
    print(f"Measured {len(rows)} complete Qwen prompts without truncation.")


if __name__ == "__main__":
    main()

"""Export only the frozen online P2 inputs; keep all evaluation material local."""

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
P1 = ROOT / "exp/v3/p1/artifacts"
P15 = ROOT / "exp/v3/p1_5"
V2 = ROOT / "exp/v2"


def jsonl(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def stable_hash(value):
    blob = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cfg = json.loads((HERE / "protocol.json").read_text())
    pool_path = P1 / "pools.jsonl"
    lengths_path = P1 / "length_audit.csv"
    a_path = P15 / "remote-evidence/results/8192/records.jsonl"
    identity = json.loads((a_path.parent / "identity.json").read_text())["sha256"]
    if (sha(pool_path) != identity["pools"] or sha(lengths_path) != identity["lengths"]):
        raise ValueError("P1.5 pool or length artifact does not match the original")
    files = (P15 / "remote-evidence/evidence.sha256").read_text().splitlines()
    if not any(line.split() == [sha(a_path), "results/8192/records.jsonl"] for line in files):
        raise ValueError("Original P1.5 answer record hash mismatch")

    size = cfg["pool_size"]
    pools = {row["qid"]: row for row in jsonl(pool_path) if row["pool_size"] == size}
    answers = [row for row in jsonl(a_path) if row["pool_size"] == size and row["route"] == "top2"
               and row["phase"] == "experiment" and row["ok"]]
    assert len(answers) == len(pools) == cfg["count"]
    assert Counter(row["qid"] for row in answers) == Counter({qid: 1 for qid in pools})
    with lengths_path.open(encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        length_fields = reader.fieldnames
        lengths = [row for row in reader if int(row["pool_size"]) == size]
    first = {row["qid"]: row for row in lengths if row["path"] == "top2"}
    sys.path.insert(0, str(V2))
    from compare_models import parse_response

    panel = []
    for row in sorted(answers, key=lambda item: item["qid"]):
        qid = row["qid"]
        (answer,) = row["calls"]
        pool = pools[qid]
        order = answer["chunk_ids"]
        assert len(order) == 2 and len(set(order)) == 2
        assert row["pool_sha256"] == pool["pool_sha256"] == stable_hash(pool["input"])
        assert answer["prompt_sha256"] == first[qid]["prompt_sha256"] and order == json.loads(first[qid]["ordered_chunk_ids"])
        chunks = {item["chunk_id"]: item for item in pool["input"]["contexts"]}
        parsed = parse_response(answer["raw"])
        citations = [x for x in parsed["citations"] if 1 <= x <= len(order)]
        assert parsed["answer"] == answer["answer"]
        assert {order[i - 1] for i in citations} == set(answer["cited_chunk_ids"])
        panel.append({"qid": qid, "pool_sha256": pool["pool_sha256"], "a_prompt_sha256": answer["prompt_sha256"],
                      "question": pool["input"]["question"], "draft_answer": answer["answer"],
                      "draft_citations": citations, "contexts": [chunks[key] for key in order]})

    args.out.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.out / "panel.jsonl", panel)
    write_jsonl(args.out / "pools.jsonl", [pools[qid] for qid in sorted(pools)])
    with (args.out / "lengths.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=length_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(lengths)
    review_ids = sorted(pools, key=lambda qid: stable_hash(["p2-human", cfg["sample_and_rank_seed"], qid]))[:cfg["human_sample_n"]]
    manifest = {
        "inputs_sha256": {"P1_pools": sha(pool_path), "P1_lengths": sha(lengths_path), "P15_8192_records": sha(a_path)},
        "human_sample_qids": review_ids,
        "files_sha256": {name: sha(args.out / name) for name in ("panel.jsonl", "pools.jsonl", "lengths.csv")},
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Exported {len(panel)} frozen first-round records, locked {len(review_ids)} human review IDs.")


if __name__ == "__main__":
    main()

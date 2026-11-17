"""Export the eight longest P1 Full inputs per intended GPU context."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
P1 = ROOT / "exp/v3/p1/artifacts"
SCALES = {4096: 10, 8192: 30, 16384: 60}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "exp/v2"))
    from compare_models import build_messages

    with (P1 / "length_audit.csv").open() as stream:
        full = [row for row in csv.DictReader(stream) if row["path"] == "full"]
    with (P1 / "pools.jsonl").open() as stream:
        pools = {(row["qid"], str(row["pool_size"])): row for line in stream if (row := json.loads(line))}
    packed = {}
    for cap, size in SCALES.items():
        group = [row for row in full if int(row["pool_size"]) == size and int(row["total_tokens"]) <= cap]
        group.sort(key=lambda row: (-int(row["total_tokens"]), row["qid"]))
        cases = []
        for row in group[:8]:
            pool = pools[row["qid"], row["pool_size"]]
            payload = pool["input"]
            example = {"question": payload["question"],
                       "context": [[chunk["title"], [sentence["text"] for sentence in chunk["sentences"]]]
                                   for chunk in payload["contexts"]]}
            messages = build_messages(example, list(range(size)))
            blob = json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode()
            if row["pool_sha256"] != pool["pool_sha256"] or row["prompt_sha256"] != hashlib.sha256(blob).hexdigest():
                raise ValueError(f"P1 case has changed: {row['qid']}")
            cases.append({"qid": row["qid"], "pool_size": size, "pool_sha256": row["pool_sha256"],
                          "prompt_sha256": row["prompt_sha256"], "input_tokens": int(row["input_tokens"]),
                          "messages": messages})
        if len(cases) != 8:
            raise ValueError(f"Insufficient eligible P1 cases for {cap}")
        packed[str(cap)] = cases
    args.out.write_text(json.dumps(packed, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

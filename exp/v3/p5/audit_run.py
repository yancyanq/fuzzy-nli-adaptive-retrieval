"""Check the frozen answer prompts, retained journal prefixes, and measured usage."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from evaluate import keyed, records

HERE = Path(__file__).resolve().parent


def ensure(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def json_file(path):
    return json.loads(path.read_text(encoding="utf-8"))


def charge(calls, cfg, cap):
    result = Counter()
    for call in calls:
        kind = call["kind"]
        tokens = call["expected_input_tokens"]
        reserve = cfg[{"answer": "max_output_tokens", "selector": "selector_max_output_tokens",
                       "selfcheck": "selfcheck_max_output_tokens"}[kind]]
        limit = min(cap, cfg["selector_total_tokens_max"]) if kind == "selector" else cap
        attempts = call["attempts"]
        where = call["prompt_sha256"]
        ensure(len(attempts) <= 3, f"Too many attempts: {where}")
        ensure(not attempts or tokens + reserve <= limit, f"Over-limit request: {where}")
        ensure(call["input_tokens"] == (tokens if call["ok"] else 0), f"Usage mismatch: {where}")
        ensure(0 <= call["output_tokens"] <= (reserve if call["ok"] else 0), f"Output length mismatch: {where}")
        ensure(sum(a.get("http_status") == 200 for a in attempts) == int(call["ok"]),
               f"HTTP success mismatch: {where}")
        result["logical_calls"] += 1
        result["http_attempts"] += len(attempts)
        result["extra_attempts"] += max(0, len(attempts) - 1)
        result["failed_calls"] += int(not call["ok"])
        result["charged_prompt_tokens"] += tokens * len(attempts)
        result["reported_input_tokens"] += call["input_tokens"]
        result["reported_output_tokens"] += call["output_tokens"]
        result["length_stop_calls"] += int(call.get("finish_reason") == "length")
        result["invalid_selector_ids"] += call.get("invalid_ids", 0)
    return result


def verify_prompt(call, signed):
    ensure(call["prompt_sha256"] == signed["prompt_sha256"]
           and call["expected_input_tokens"] == signed["input_tokens"], "Frozen answer prompt mismatch")


def verify_prefixes(evidence):
    sizes = {"quality.jsonl": 2520, "selfcheck.jsonl": 360, "timing.jsonl": 250}
    receipts = sorted(evidence.glob("driver-prior-*.raw.sha256"))
    for receipt in receipts:
        for line in receipt.read_text().splitlines():
            expected, label = line.split(maxsplit=1)
            path = Path(label)
            n = sizes[path.name]
            with (evidence / path).open("rb") as stream:
                actual = sha256(b"".join(stream.readline() for _ in range(n))).hexdigest()
            ensure(actual == expected, f"Pre-resumption rows changed: {path}")
    return {"manifests": len(receipts), "verified_prefix_rows_each": sizes if receipts else {}}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--evidence", type=Path, required=True)
    args = cli.parse_args()
    ensure((args.evidence / "status").read_text().strip() == "0", "P5 is not finished")
    cfg = json_file(HERE / "protocol.json")
    source = HERE / "input"
    manifest = json_file(source / "manifest.json")
    ensure(digest(HERE / "protocol.json") == manifest["config_sha256"], "Protocol hash mismatch")
    for name, expected in manifest["files_sha256"].items():
        ensure(digest(source / name) == expected, f"Frozen input changed: {name}")
    audited = keyed(records(source / "lengths.jsonl"), ("qid", "pool_size", "route"))
    raw = args.evidence / "live"
    result = {"pre_resumption": verify_prefixes(args.evidence), "base_answer_planned_prompt_tokens": 0, "phases": {}}

    for path in sorted(raw.glob("*.jsonl")):
        name = path.stem
        if name in {"features", "decisions"}:
            continue
        by_size = {}
        for row in records(path):
            size = row["pool_size"]
            cap = int(name.split("_")[1]) if name.startswith("warmup_") else cfg["services"][str(size)]["context"]
            counts = by_size.setdefault(size, Counter())
            calls = row["calls"]
            observed = charge(calls, cfg, cap)
            counts.update(observed)
            counts["records"] += 1
            counts["unavailable_answers"] += int(row.get("ok") is False)
            answer_calls = [call for call in calls if call["kind"] == "answer"]
            if name == "quality":
                signed = audited[row["qid"], size, row["route"]]
                verify_prompt(answer_calls[0], signed)
                ensure(row["pool_sha256"] == signed["pool_sha256"] and row["chunk_ids"] == signed["chunk_ids"],
                       "Base answer has a different pool or paragraph order")
                result["base_answer_planned_prompt_tokens"] += signed["input_tokens"]
                counts["answer_parse_failures"] += int(not row["parse_ok"])
                counts["invalid_answer_citation_ids"] += row["invalid_citation_count"]
            if name == "timing":
                verify_prompt(answer_calls[0], audited[row["qid"], size, "top2"])
                if row["triggered"]:
                    route = "v2_direct_2plus1" if row["policy"] == "v2_native" else "direct_2plus4"
                    verify_prompt(answer_calls[1], audited[row["qid"], size, route])
            if name != "selfcheck":
                budget = cfg["cumulative_qwen_input_limit"]
                ensure(observed["charged_prompt_tokens"] + row["budget_remaining"] == budget,
                       f"Wrong ledger total for {name}: {row['qid']}")
            ensure(sum(call["kind"] == "selector" for call in calls) <= cfg["selector_max_calls_per_answer"],
                   f"Selector call limit exceeded for {name}: {row['qid']}")
            if name == "selfcheck":
                counts["unavailable_scores"] += int(row["risk"] is None)
        result["phases"][name] = by_size
    ensure(result["base_answer_planned_prompt_tokens"] == sum(row["input_tokens"] for row in audited.values()),
           "Base prompt coverage does not match plan")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

"""Replay only the P5 evidence selector for the fixed policies' final answers."""
import argparse
from pathlib import Path
from urllib.request import urlopen
import json

import p15_runner
import runtime
from transformers import AutoTokenizer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--p5", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    args = parser.parse_args()
    study = json.loads(Path("protocol.json").read_text())
    for filename, expected in study["online_sha256"].items():
        if p15_runner.file_hash(args.test / filename) != expected:
            raise ValueError(f"Fixed-threshold input diverges: {filename}")
    cfg = json.loads((args.p5 / "protocol.json").read_text())
    cap = cfg["services"]["30"]["context"]
    runtime.URL = "http://127.0.0.1:18083/v1"
    with urlopen(runtime.URL + "/models", timeout=10) as response:
        cards = json.load(response)["data"]
    if not any(card["id"] == cfg["model"] and card.get("max_model_len") == cap for card in cards):
        raise ValueError("Unexpected Qwen service")
    tokenizer = AutoTokenizer.from_pretrained(str(args.tokenizer), local_files_only=True)
    rt = runtime.Runtime(cfg, tokenizer, cap)
    pools = {qid: row for (_, qid), row in p15_runner.load_pools(args.test / "pools.jsonl", [30]).items()}
    a = {q: row for (q,), row in runtime.read_index(args.test / "a.jsonl", ("qid",)).items()}
    b = {q: row for (q,), row in runtime.read_index(args.test / "b.jsonl", ("qid",)).items()}
    plan = json.loads((args.test / "plan.json").read_text())
    cutoff = json.loads((args.test / "thresholds.json").read_text())["boundaries"]
    features = {q: row for (q,), row in runtime.read_index(args.test / "nli.jsonl", ("qid",)).items()}
    if plan["phase"] != "test" or set(pools) != set(a) or set(pools) != set(features):
        raise ValueError("Unexpected source cohort")
    selections = {k: set(v) for k, v in plan["routes"].items()}
    replay = {
        k: {q for q, row in features.items()
            if threshold is not None and row["ranks"][k] is not None and row["ranks"][k] <= threshold}
        for k, threshold in cutoff.items()
    }
    if replay != selections or set(b) != set.union(*selections.values()) or not all(r["ok"] for r in b.values()):
        raise ValueError("Original fixed-threshold routing or final answers differ")
    jobs = [(q, route) for q in pools for route in sorted({("B" if q in ids else "A") for ids in selections.values()})]
    if len(jobs) != len(pools) + len(selections["old"] ^ selections["repaired"]):
        raise ValueError("Wrong union size for final branches")

    def select(q, route):
        pool = pools[q]
        final = b[q] if route == "B" else a[q]
        answer_calls = a[q]["calls"] + (b[q]["calls"] if route == "B" else [])
        spent = sum(call["expected_input_tokens"] * len(call["attempts"]) for call in answer_calls)
        ledger = runtime.Ledger(cfg["cumulative_qwen_input_limit"] - spent)
        sp, calls, reason = rt.evidence(runtime.example_from_pool(pool), final, ledger)
        return {"qid": q, "route": route, "pool_sha256": pool["pool_sha256"],
                "answer_prompt_sha256": final["calls"][0]["prompt_sha256"], "sp": sp,
                "calls": calls, "reason": reason}

    print(f"Selecting citations for {len(jobs)} frozen final branches.", flush=True)
    output = Path("selector.jsonl")
    runtime.run_jobs(output, ("qid", "route"), jobs, select, 8, "fresh_citations")
    actual = runtime.read_index(output, ("qid", "route"))
    if set(actual) != set(jobs) or any(not call["ok"] for r in actual.values() for call in r["calls"]):
        raise ValueError("Selector journal incomplete or has failed model requests")
    print(f"Completed {len(actual)} branch citation records.", flush=True)


if __name__ == "__main__":
    main()

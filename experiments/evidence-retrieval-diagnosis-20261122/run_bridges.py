"""Run changed follow-up paragraphs for the unchanged repaired gate."""
import argparse
import json
from pathlib import Path
from urllib.request import urlopen

import p15_runner
import runtime
from transformers import AutoTokenizer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--p5", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(Path("bridge_ids.json").read_text())
    for name, expected in plan["inputs"].items():
        if p15_runner.file_hash(args.test / name) != expected:
            raise ValueError("The frozen input changed")
    selected = plan["routes"]
    if set(selected) != set(json.loads((args.test / "plan.json").read_text())["routes"]["repaired"]):
        raise ValueError("Trigger set changed")
    first = runtime.read_index(args.test / "a.jsonl", ("qid",))
    pools = p15_runner.load_pools(args.test / "pools.jsonl", [30])
    cfg = json.loads((args.p5 / "protocol.json").read_text())
    cap = cfg["services"]["30"]["context"]
    runtime.URL = "http://127.0.0.1:18083/v1"
    with urlopen(runtime.URL + "/models", timeout=10) as response:
        cards = json.load(response)["data"]
    if not any(card["id"] == cfg["model"] and card.get("max_model_len") == cap for card in cards):
        raise ValueError("Unexpected inference engine")
    rt = runtime.Runtime(cfg, AutoTokenizer.from_pretrained(str(args.tokenizer), local_files_only=True), cap)

    def run(qid):
        pool, a = pools[30, qid], first[qid,]
        chosen = selected[qid]
        if chosen[:2] != a["chunk_ids"] or len(set(chosen)) != 6:
            raise ValueError("Unexpected follow-up context")
        lookup = {c["chunk_id"]: i for i, c in enumerate(pool["input"]["contexts"])}
        indices = [lookup[c] for c in chosen]
        ex = runtime.example_from_pool(pool)
        messages = runtime.answer_messages(runtime.v2, ex, indices, "direct_2plus4")
        initial = a["calls"][0]
        ledger = runtime.Ledger(cfg["cumulative_qwen_input_limit"] - initial["input_tokens"])
        call = rt.request(ledger, "answer", messages, cfg["max_output_tokens"])
        if not call["ok"]:
            raise RuntimeError(f"Missing required model result: {qid}")
        parsed = runtime.v2.parse_response(call["raw"])
        citations = [i for i in parsed["citations"] if type(i) is int and 1 <= i <= len(indices)]
        result = {"answer": parsed["answer"], "citations": citations, "paragraph_indices": indices,
                  "chunk_ids": chosen, "ok": bool(parsed["answer"])}
        sp, citation_calls, reason = rt.evidence(ex, result if result["ok"] else a, ledger)
        if any(not c["ok"] for c in citation_calls):
            raise RuntimeError(f"Citation request failed: {qid}")
        return {"qid": qid, "pool_sha256": pool["pool_sha256"], **result, "sp": sp,
                "calls": [call] + citation_calls, "evidence_reason": reason}

    runtime.run_jobs(Path("bridge_live.jsonl"), ("qid",), [(q,) for q in selected], run, 8, "bridge_followup")


if __name__ == "__main__":
    main()

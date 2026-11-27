"""Generate three frozen branches on new questions, then score A with real NLI."""
import argparse
from pathlib import Path
from urllib.request import urlopen
import json

import p15_runner
import runtime
from transformers import AutoTokenizer


ROUTES = ("top2", "direct_2plus4", "v2_direct_2plus1")


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--p5", type=Path, required=True)
    cli.add_argument("--qwen", type=Path, required=True)
    cli.add_argument("--deberta", type=Path, required=True)
    cli.add_argument("--workers", type=int, default=8)
    args = cli.parse_args()
    cfg = json.loads((args.p5 / "protocol.json").read_text())
    manifest = json.loads(Path("manifest.json").read_text())
    if p15_runner.file_hash(Path("pools.jsonl")) != manifest["pool_sha256"]:
        raise ValueError("Fresh pools changed after sealing")
    pools = {qid: p for (_, qid), p in p15_runner.load_pools(Path("pools.jsonl"), [30]).items()}
    if list(pools) != manifest["qids"]:
        raise ValueError("Fresh cohort order changed")
    runtime.URL = "http://127.0.0.1:18083/v1"
    with urlopen(runtime.URL + "/models", timeout=10) as response:
        models = json.load(response)["data"]
    cap = cfg["services"]["30"]["context"]
    assert any(r["id"] == cfg["model"] and r["max_model_len"] == cap for r in models)
    tokenizer = AutoTokenizer.from_pretrained(str(args.qwen), local_files_only=True)
    rt = runtime.Runtime(cfg, tokenizer, cap)
    audit, examples = {}, {}
    for qid, p in pools.items():
        ex = runtime.example_from_pool(p)
        examples[qid] = ex
        for route in ROUTES:
            indices = runtime.route_indices(runtime.v2, ex, route)
            prompt = runtime.answer_messages(runtime.v2, ex, indices, route)
            tokens = rt.count(prompt)
            if tokens + cfg["max_output_tokens"] > cap:
                raise ValueError(f"Fresh question exceeds context capacity: {qid}")
            audit[30, qid, route] = {"pool_sha256": p["pool_sha256"], "input_tokens": tokens,
                                      "chunk_ids": [p["input"]["contexts"][i]["chunk_id"] for i in indices],
                                      "prompt_sha256": p15_runner.digest(prompt)}

    def answer(qid, route):
        ledger = runtime.Ledger(cfg["cumulative_qwen_input_limit"])
        result = rt.answer(pools[qid], examples[qid], route, audit, ledger)
        if not result["calls"][0]["ok"]:
            raise RuntimeError(f"Required Qwen call failed: {qid}/{route}")
        return {"qid": qid, "route": route, "pool_sha256": pools[qid]["pool_sha256"], **result}

    jobs = [(qid, r) for qid in pools for r in ROUTES]
    runtime.run_jobs(Path("answers.jsonl"), ("qid", "route"), jobs, answer, args.workers, "fresh_qwen")
    answers = runtime.read_index(Path("answers.jsonl"), ("qid", "route"))
    if set(answers) != set(jobs):
        raise ValueError("Fresh generation is incomplete")

    cfg["nli"]["threads"] = 2
    nli = runtime.NLI(cfg, args.deberta)

    def verify(qid):
        a = answers[qid, "top2"]
        if a["ok"]:
            feature = nli.get(rt.project_a(pools[qid], a))
        else:
            feature = {"risk": None, "bridge": None, "nli_seconds": 0., "nli_input_tokens": 0}
        return {"qid": qid, "pool_sha256": pools[qid]["pool_sha256"], **feature}

    runtime.run_jobs(Path("features.jsonl"), ("qid",), [(qid,) for qid in pools], verify, 1, "fresh_nli")


if __name__ == "__main__":
    main()

"""Collect A and only necessary B branches without accessing any answer labels."""
import argparse
from pathlib import Path
from urllib.request import urlopen

import p15_runner
import runtime
from transformers import AutoTokenizer

from policy_values import ranks, read, triggered


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--phase", choices=("calibration", "test"), required=True)
    cli.add_argument("--p5", type=Path, required=True)
    cli.add_argument("--qwen", type=Path, required=True)
    cli.add_argument("--deberta", type=Path, required=True)
    args = cli.parse_args()
    model_dir = Path(__file__).resolve().parent
    base = read(args.p5 / "protocol.json")
    manifest = read("manifest.json")
    for path, field in [("pools.jsonl", "pool_sha256"), (model_dir / "trained.json", "trained_sha256"),
                        (model_dir / "protocol.json", "protocol_sha256"),
                        (model_dir / "dates.py", "constraint_code_sha256"), (model_dir / "policy_values.py", "policy_code_sha256")]:
        if p15_runner.file_hash(Path(path)) != manifest[field]:
            raise ValueError(f"Sealed input has changed: {path}")
    protocol, trained = read(model_dir / "protocol.json"), read(model_dir / "trained.json")
    pools = {qid: p for (_, qid), p in p15_runner.load_pools(Path("pools.jsonl"), [30]).items()}
    if list(pools) != manifest["qids"] or len(pools) != protocol["sample"][args.phase]:
        raise ValueError("Cohort identity differs")
    runtime.URL = "http://127.0.0.1:18083/v1"
    cap = base["services"]["30"]["context"]
    with urlopen(runtime.URL + "/models", timeout=10) as stream:
        assert any(card["id"] == base["model"] and card["max_model_len"] == cap for card in read_response(stream))
    rt = runtime.Runtime(base, AutoTokenizer.from_pretrained(str(args.qwen), local_files_only=True), cap)
    audit, examples = {}, {}
    for qid, pool in pools.items():
        ex = runtime.example_from_pool(pool)
        examples[qid] = ex
        for route in ("top2", "direct_2plus4"):
            indices = runtime.route_indices(runtime.v2, ex, route)
            messages = runtime.answer_messages(runtime.v2, ex, indices, route)
            count = rt.count(messages)
            if count + base["max_output_tokens"] > cap:
                raise ValueError(f"Question exceeds context capacity: {qid}")
            audit[30, qid, route] = {"pool_sha256": pool["pool_sha256"], "input_tokens": count,
                                     "prompt_sha256": p15_runner.digest(messages),
                                     "chunk_ids": [pool["input"]["contexts"][i]["chunk_id"] for i in indices]}

    def answer(qid, route):
        pool = pools[qid]
        record = rt.answer(pool, examples[qid], route, audit, runtime.Ledger(base["cumulative_qwen_input_limit"]))
        if not record["calls"][0]["ok"]:
            raise RuntimeError(f"Qwen request failed: {qid}/{route}")
        return {"qid": qid, "route": route, "pool_sha256": pool["pool_sha256"], **record}

    print(f"Starting {args.phase} first-round inference for {len(pools)} cases.", flush=True)
    runtime.run_jobs(Path("a.jsonl"), ("qid",), [(qid,) for qid in pools],
                     lambda qid: answer(qid, "top2"), 8, f"{args.phase}_a")
    first = runtime.read_index(Path("a.jsonl"), ("qid",))
    if set(first) != {(q,) for q in pools}:
        raise ValueError("Incomplete first round")
    base["nli"]["threads"] = 2
    nli = runtime.NLI(base, args.deberta)

    def verify(qid):
        a = first[qid,]
        p = pools[qid]
        feature = nli.get(rt.project_a(p, a)) if a["ok"] else {"risk": None, "bridge": None}
        return {"qid": qid, "pool_sha256": p["pool_sha256"], **feature,
                "ranks": ranks(p, a, feature, trained),
                "planned_b_tokens": audit[30, qid, "direct_2plus4"]["input_tokens"]}

    runtime.run_jobs(Path("nli.jsonl"), ("qid",), [(qid,) for qid in pools], verify, 1, f"{args.phase}_nli")
    signals = runtime.read_index(Path("nli.jsonl"), ("qid",))
    if set(signals) != set(first):
        raise ValueError("Incomplete NLI batch")
    if args.phase == "calibration":
        cap_count = int(protocol["threshold_calibration"]["cap_rate"] * len(pools))
        routing = {
            name: sorted([q for q in pools if signals[q,]["ranks"][name] is not None],
                         key=lambda q: signals[q,]["ranks"][name])[:cap_count]
            for name in protocol["models"]
        }
    else:
        cutoffs = read("thresholds.json")
        if cutoffs["trained_sha256"] != manifest["trained_sha256"] or cutoffs["protocol_sha256"] != manifest["protocol_sha256"]:
            raise ValueError("Cutoffs do not match the sealed judge")
        if set(pools) & set(cutoffs["calibration_qids"]):
            raise ValueError("Test overlaps calibration")
        routing = {
            name: [q for q in pools if triggered(tuple_or_none(signals[q,]["ranks"][name]), cutoffs["boundaries"][name])]
            for name in protocol["models"]
        }

    plan = {"phase": args.phase, "routes": routing}
    with Path("plan.json").open("w") as stream:
        import json
        json.dump(plan, stream, indent=2)
    selected = set(q for group in routing.values() for q in group)
    print(f"Running {len(selected)} unique follow-up answers.", flush=True)
    runtime.run_jobs(Path("b.jsonl"), ("qid",), [(q,) for q in pools if q in selected],
                     lambda qid: answer(qid, "direct_2plus4"), 8, f"{args.phase}_b")
    final = runtime.read_index(Path("b.jsonl"), ("qid",))
    if set(final) != {(q,) for q in selected}:
        raise ValueError("Follow-up coverage differs from plan")
    print(f"Completed {args.phase}: {len(first)} A, {len(signals)} NLI, {len(final)} B.", flush=True)


def tuple_or_none(value):
    return tuple(value) if value is not None else None


def read_response(stream):
    import json
    return json.load(stream)["data"]


if __name__ == "__main__":
    main()

"""Resume-aware runner for the frozen P5 quality and true live timing experiments."""

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/"v2"))

import p15_runner
from runtime import Ledger, NLI, Runtime, read_index, run_jobs, timed
import compare_models as v2
from routes import answer_messages, example_from_pool, route_indices
from policy import decide


def read_json(path):
    return json.loads(path.read_text())


def verify_input(cfg, lock, artifact_dir):
    if (lock["protocol_sha256"] != p15_runner.file_hash(HERE/"protocol.json")
            or lock["model_logic_sha256"] != p15_runner.file_hash(HERE/"policy.py")):
        raise ValueError("Policy and protocol have changed post-calibration")
    spec = read_json(HERE/"input_manifest.json")
    if any(p15_runner.file_hash(artifact_dir/name) != expected for name,expected in spec["files_sha256"].items()):
        raise ValueError("P5 input identity mismatch")
    sizes = [int(x) for x in cfg["services"]]
    pools = p15_runner.load_pools(artifact_dir/"pools.jsonl",sizes)
    audit_rows = p15_runner.read_jsonl(artifact_dir/"lengths.jsonl")
    audit = {(r["pool_size"],r["qid"],r["route"]):r for r in audit_rows}
    split = read_json(artifact_dir/"split.json")
    primary = {(cfg["primary_size"],qid) for qid in split["primary_qids"]}
    secondary = {(size,qid) for size in cfg["secondary_sizes"] for qid in split["secondary_qids"]}
    if (len(primary) != cfg["primary_n"] or len(secondary) != cfg["secondary_n"]*len(cfg["secondary_sizes"])
            or len(split["timing_qids"]) != cfg["timing_n"] or set(pools) != primary|secondary):
        raise ValueError("P5 cohorts do not match the frozen design")
    expected = {(*key,route) for key in pools for route in cfg["shared_routes"]}
    if len(audit) != len(audit_rows) or set(audit) != expected or any(
            r["total_tokens"] > cfg["services"][str(r["pool_size"])]["context"] for r in audit.values()):
        raise ValueError("Invalid frozen prompt lengths or coverage")
    return pools,audit,split


def warmup(rt, warm_pool_file, out):
    candidates = p15_runner.read_jsonl(warm_pool_file)
    sample = sorted(candidates,key=lambda row:row["qid"])[:2]
    audit = {}
    for row in sample:
        ex = example_from_pool(row)
        for route in ("top2","full"):
            indices = route_indices(v2,ex,route)
            messages = answer_messages(v2,ex,indices,route)
            audit[row["pool_size"],row["qid"],route] = {"pool_sha256":row["pool_sha256"],
               "chunk_ids":[row["input"]["contexts"][i]["chunk_id"] for i in indices],
               "input_tokens":rt.count(messages),"prompt_sha256":p15_runner.digest(messages)}
    with out.open("x") as stream:
        for row in sample:
            for route in ("top2","full"):
                result = rt.direct(row,route,audit)
                p15_runner.append(stream,result)
                if not result["ok"] or any(not c["ok"] for c in result["calls"]):
                    raise RuntimeError("Development end-to-end warmup did not complete")


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--stage", choices=("quality","timing","features"), required=True)
    cli.add_argument("--sizes", type=int, nargs="+", required=True)
    cli.add_argument("--tokenizer", type=Path, required=True)
    cli.add_argument("--snapshot", type=Path, required=True)
    cli.add_argument("--warm-pools", type=Path)
    cli.add_argument("--out", type=Path, required=True)
    args = cli.parse_args()
    from transformers import AutoTokenizer

    cfg = read_json(HERE/"protocol.json")
    lock = read_json(HERE/"policy_lock.json")
    pools,audit,split = verify_input(cfg,lock,HERE/"input")
    args.out.mkdir(parents=True,exist_ok=True)
    q_key = ("pool_size","qid")
    route_key = q_key+("route",)
    first_routes = cfg["shared_routes"]
    caps = {cfg["services"][str(s)]["context"] for s in args.sizes}
    if len(caps) != 1 and args.stage != "features":
        raise ValueError("GPU stages must use one service context limit")
    cap = max(caps)
    rt = Runtime(cfg,AutoTokenizer.from_pretrained(str(args.tokenizer),local_files_only=True), cap)
    workers = cfg["client_workers"]
    qids = [(size,qid) for size in args.sizes for qid in sorted(
        (qid for s,qid in pools if s == size),key=lambda q:p15_runner.digest(["p5-run",cfg["draw_seed"],q]))]
    p15_runner.URL = "http://127.0.0.1:18082/v1"
    if args.stage in {"quality","timing"}:
        p15_runner.service_ready(cfg,cap)
    if args.stage == "quality":
        warm_file = args.out/f"warmup_{cap}.jsonl"
        if args.warm_pools and not warm_file.exists():
            print("Running known validation warmup",flush=True)
            warmup(rt,args.warm_pools,warm_file)
        # Rotate order between question blocks, keeping eight equal-size requests in flight.
        phase = []
        for start in range(0,len(qids),workers):
            block = qids[start:start+workers]
            if len({s for s,_ in block}) != 1:
                # Take one scale at a time to avoid changing the service profile mid-batch.
                raise ValueError("Arrange each scale as a separate quality-stage call")
            offset = (start//workers)%len(first_routes)
            phase.extend((*key,route) for route in first_routes[offset:]+first_routes[:offset] for key in block)
        quality_path = args.out/"quality.jsonl"
        run_jobs(quality_path,route_key,phase,lambda s,q,r: rt.direct(pools[s,q],r,audit),workers,"quality")
        quality = read_index(quality_path,route_key)
        def qwen_check(s,q):
            a = quality[s,q,"top2"]
            ledger = Ledger(cfg["cumulative_qwen_input_limit"]-a["calls"][0]["input_tokens"])
            return {k:a[k] for k in ("qid","pool_size","pool_sha256")} | rt.selfcheck(pools[s,q],a,ledger)
        run_jobs(args.out/"selfcheck.jsonl",q_key,qids,qwen_check,workers,"qwen_selfcheck")
    elif args.stage == "timing":
        nli = NLI(cfg,args.snapshot)
        size = cfg["primary_size"]
        order = split["timing_qids"]
        methods = cfg["timing_policies"]
        jobs = []
        for i in range(0,len(order),workers):
            rotated = methods[(i//workers)%len(methods):]+methods[:(i//workers)%len(methods)]
            jobs.extend((size,qid,method,-1 if method=="v2_native" else cfg["primary_budget_percent"])
                        for method in rotated for qid in order[i:i+workers])
        run_jobs(args.out/"timing.jsonl",q_key+("policy","budget_percent"),jobs,
                 lambda s,q,m,b: timed(rt,nli,pools[s,q],audit,lock,m,b),workers,"true_live_timing")
    else:
        nli = NLI(cfg,args.snapshot)
        quality = read_index(args.out/"quality.jsonl",route_key)
        selfcheck = read_index(args.out/"selfcheck.jsonl",q_key)
        def features(s,q):
            a = quality[s,q,"top2"]
            return {k:a[k] for k in ("qid","pool_size","pool_sha256")} | nli.get(rt.project_a(pools[s,q],a))
        run_jobs(args.out/"features.jsonl",q_key,qids,features,1,"nli")
        feats = read_index(args.out/"features.jsonl",q_key)
        decision_path = args.out/"decisions.jsonl"
        tmp = decision_path.with_suffix(".tmp")
        with tmp.open("w") as stream:
            for s,q in qids:
                a = quality[s,q,"top2"]
                f = feats[s,q]
                sc = selfcheck[s,q]
                for method in lock["models"]:
                    budgets = [-1] if method=="v2_native" else cfg["budgets_percent"]
                    for budget in budgets:
                        yes, score, reason = decide(lock,method,budget,q,f["risk"],f["bridge"],sc["risk"])
                        b_route = "v2_direct_2plus1" if method=="v2_native" else "direct_2plus4"
                        b = quality[s,q,b_route]
                        calls_so_far = a["calls"][:1]+(sc["calls"] if method=="qwen_selfcheck" else [])
                        spent = sum(c["expected_input_tokens"]*len(c["attempts"]) for c in calls_so_far)
                        b_input = b["calls"][0]["expected_input_tokens"]
                        affordable = spent+b_input <= cfg["cumulative_qwen_input_limit"]
                        triggered = a["ok"] and yes and affordable
                        if not a["ok"]:
                            reason = "first_answer_unavailable"
                        elif yes and not affordable:
                            reason = "budget_exhausted"
                        elif triggered and not b["ok"]:
                            reason = b["reason"]
                        p15_runner.append(stream, {k:a[k] for k in ("qid","pool_size","pool_sha256")} | {
                            "policy":method,"budget_percent":budget,"triggered":triggered,
                            "final_route":b_route if triggered and b["ok"] else "top2",
                            "decision_score":score,"reason":reason})
        tmp.replace(decision_path)
    print(json.dumps({"stage":args.stage,"sizes":args.sizes,"completed_utc":p15_runner.utc_now()}),flush=True)


if __name__ == "__main__":
    main()

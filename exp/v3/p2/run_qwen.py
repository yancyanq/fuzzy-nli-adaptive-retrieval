"""Run P2 relation extraction, Qwen self-check and direct baselines."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import json
from pathlib import Path
import sys
from time import perf_counter, sleep
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import p15_runner as p15
from verify import indexed, messages, validate_relationships, validate_selfcheck


URL = "http://127.0.0.1:18082/v1"


def extract(row, task, tokenizer, qwen, guided=False, example_free=False):
    if guided:
        from guided import EXAMPLE_FREE, FORMAT, schema, validate_wire, wire_messages
        prompt = wire_messages(row, task, example_free=example_free)
    else:
        prompt = messages(row, task)
    prompt_tokens = len(tokenizer.apply_chat_template(prompt, tokenize=True, add_generation_prompt=True))
    reserve = qwen["relation_output_tokens"] if task == "relations" else qwen["selfcheck_output_tokens"]
    if prompt_tokens + reserve > qwen["context"]:
        raise ValueError(f"P2 prompt exceeds context for {row['qid']}")
    body = {"model": qwen["model"], "messages": prompt, "max_tokens": reserve, "temperature": qwen["temperature"]}
    if guided:
        body.update(guided_json=schema(row, task), guided_decoding_backend="xgrammar")
    req = Request(URL + "/chat/completions", data=p15.encoded(body), headers={"Content-Type": "application/json"})
    started = perf_counter()
    attempts = []
    for trial in range(1, 4):
        trial_start = perf_counter()
        retry = False
        try:
            with urlopen(req, timeout=480) as stream:
                payload = json.load(stream)
            usage, choice = payload["usage"], payload["choices"][0]
            raw = choice["message"]["content"]
            if usage["prompt_tokens"] != prompt_tokens or not 0 <= usage["completion_tokens"] <= reserve:
                raise ValueError("Qwen usage differs from the prechecked prompt or budget")
            if not isinstance(raw, str):
                raise ValueError("Unusable Qwen response content")
            if guided:
                result = validate_wire(raw, row, task)
            else:
                result = validate_relationships(raw, indexed(row)) if task == "relations" else validate_selfcheck(raw)
            attempts.append({"trial": trial, "http_status": 200, "seconds": perf_counter() - trial_start})
            return {"qid": row["qid"], "task": task, "ok": True, "pool_sha256": row["pool_sha256"],
                    "a_prompt_sha256": row["a_prompt_sha256"], "prompt_sha256": p15.digest(prompt), "raw": raw,
                    "response_id": payload["id"], "input_tokens": prompt_tokens, "output_tokens": usage["completion_tokens"],
                    "seconds": perf_counter() - started, "finish_reason": choice["finish_reason"],
                    "validation": result, "attempts": attempts, "recorded_at_utc": p15.utc_now(),
                    **({"format": EXAMPLE_FREE if example_free else FORMAT} if guided else {})}
        except HTTPError as err:
            retry = err.code in {408, 429, 500, 502, 503, 504}
            detail = {"http_status": err.code, "error": err.read(2048).decode(errors="replace")}
        except OSError as err:
            retry = True
            detail = {"error": str(err)}
        except (ValueError, KeyError, IndexError) as err:
            detail = {"error": str(err)}
        attempts.append({"trial": trial, "seconds": perf_counter() - trial_start, **detail})
        if not retry:
            break
        if trial < 3:
            sleep(2 ** (trial - 1))
    return {"qid": row["qid"], "task": task, "ok": False, "attempts": attempts,
            "seconds": perf_counter() - started, "recorded_at_utc": p15.utc_now()}


def run_task(executor, qids, task, path, run, workers):
    previously = p15.read_jsonl(path) if path.exists() else []
    existing = [row["qid"] for row in previously if row["ok"]]
    if len(existing) != len(set(existing)) or not set(existing) <= set(qids):
        raise ValueError("Resume would mix incompatible results")
    done = set(existing)
    with path.open("a", encoding="utf-8") as out:
        for i in range(0, len(qids), workers):
            pending = [executor.submit(run, qid) for qid in qids[i:i + workers] if qid not in done]
            for future in as_completed(pending):
                record = future.result()
                p15.append(out, record)
                if record["ok"]:
                    done.add(record["qid"])
            if pending:
                print(json.dumps({"task": task, "ok": len(done), "total": len(qids), "utc": p15.utc_now()}), flush=True)
    if len(done) != len(qids):
        raise RuntimeError(f"Missing API outputs for {task}, resume with the original configuration")


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--bundle", type=Path, required=True)
    cli.add_argument("--tokenizer", type=Path, required=True)
    cli.add_argument("--out", type=Path, required=True)
    variants = cli.add_mutually_exclusive_group()
    variants.add_argument("--guided-only", action="store_true")
    variants.add_argument("--example-free-selfcheck", action="store_true")
    args = cli.parse_args()
    bundle = args.bundle
    cfg = json.loads((bundle / "protocol.json").read_text())
    qwen = cfg["qwen"]
    panel = {row["qid"]: row for row in p15.read_jsonl(bundle / "panel.jsonl")}
    if len(panel) != cfg["count"] or any(set(row) != {
        "qid", "pool_sha256", "a_prompt_sha256", "question", "draft_answer", "draft_citations", "contexts"
    } for row in panel.values()):
        raise ValueError("Unexpected panel input or fields")
    sys.path.insert(0, str((bundle / "v2").resolve()))
    import compare_models as v2
    from transformers import AutoTokenizer

    p15.URL = URL
    p15.service_ready(qwen, qwen["context"])
    tokenizer = AutoTokenizer.from_pretrained(str(args.tokenizer), local_files_only=True)
    pools = p15.load_pools(bundle / "pools.jsonl", [cfg["pool_size"]])
    with (bundle / "lengths.csv").open(encoding="utf-8") as stream:
        lengths = {(int(r["pool_size"]), r["qid"], r["path"]): r for r in csv.DictReader(stream)}
    direct = {"routes": {f"direct_{path}": {"prompt_path": path, "first_answer": False}
                         for path in ("2plus2", "2plus4")}, "model": qwen["model"],
              "temperature": qwen["temperature"], "max_output_tokens": qwen["direct_answer_output_tokens"]}
    qids = sorted(panel, key=lambda qid: p15.digest(["p15", cfg["sample_and_rank_seed"], qid]))
    args.out.mkdir(parents=True, exist_ok=True)
    workers = qwen["client_workers"]
    guided = args.guided_only or args.example_free_selfcheck
    tasks = ("selfcheck",) if args.example_free_selfcheck else ("relations", "selfcheck")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for task in tasks:
            run_task(pool, qids, task, args.out / f"{task}.jsonl",
                     lambda qid: extract(panel[qid], task, tokenizer, qwen, guided, args.example_free_selfcheck), workers)
        for task in direct["routes"] if not guided else []:
            run_task(pool, qids, task, args.out / f"{task}.jsonl", lambda qid: p15.route_one(
                v2, pools[cfg["pool_size"], qid], task, lengths, direct, qids.index(qid) // workers, "p2_direct"
            ), workers)
    (args.out / "complete.json").write_text(json.dumps({"n_per_task": len(qids), "finished_at_utc": p15.utc_now()}) + "\n")


if __name__ == "__main__":
    main()

"""Run the preregistered P1.5 routes without access to gold labels."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from time import monotonic, perf_counter, sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


HERE = Path(__file__).resolve().parent
URL = "http://127.0.0.1:18081/v1"


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() if sys.version_info >= (3, 11) else hashlib.sha256(stream.read()).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def read_jsonl(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def append(stream, value):
    stream.write(encoded(value).decode("utf-8") + "\n")
    stream.flush()


def load_pools(path, sizes):
    pools = {}
    for row in read_jsonl(path):
        if set(row) != {"qid", "pool_size", "pool_sha256", "input"}:
            raise ValueError("Unknown online pool key")
        if row["pool_size"] not in sizes:
            continue
        payload = row["input"]
        if set(payload) != {"question", "contexts"} or digest(payload) != row["pool_sha256"]:
            raise ValueError("Pool payload differs from the locked input")
        contexts = payload["contexts"]
        for chunk in contexts:
            if set(chunk) != {"chunk_id", "title", "sentences"} or any(
                set(sentence) != {"sentence_id", "text"} for sentence in chunk["sentences"]
            ):
                raise ValueError("Online context contains an unexpected field")
        if len(contexts) != row["pool_size"] or len(set(c["chunk_id"] for c in contexts)) != row["pool_size"]:
            raise ValueError("Incorrect or repeated context")
        key = row["pool_size"], row["qid"]
        if key in pools:
            raise ValueError(f"Duplicate online pool: {key}")
        pools[key] = row
    return pools


def service_ready(protocol, cap):
    deadline = monotonic() + 420
    while monotonic() < deadline:
        try:
            with urlopen(URL + "/models", timeout=4) as response:
                model_list = json.load(response)["data"]
        except (OSError, ValueError):
            sleep(2)
            continue
        card = next((item for item in model_list if item["id"] == protocol["model"]), {})
        if card.get("max_model_len") != cap:
            raise ValueError(f"Service reports unexpected model/context: {card}")
        return
    raise TimeoutError(f"The {cap} service did not become ready")


def generate(v2, prompt_path, indices, example, chunks, row, audit, protocol):
    qid, size = row["qid"], row["pool_size"]
    messages = v2.build_messages(example, indices)
    locked = audit[size, qid, prompt_path]
    chunk_ids = [chunks[i]["chunk_id"] for i in indices]
    if (locked["pool_sha256"] != row["pool_sha256"] or digest(messages) != locked["prompt_sha256"]
            or chunk_ids != json.loads(locked["ordered_chunk_ids"])):
        raise ValueError(f"Live prompt diverged from P1 audit: {size} {qid} {prompt_path}")
    body = {"model": protocol["model"], "messages": messages, "temperature": protocol["temperature"],
            "max_tokens": protocol["max_output_tokens"]}
    request = Request(URL + "/chat/completions", data=encoded(body),
                      headers={"Content-Type": "application/json"})
    attempts = []
    result = {"prompt_path": prompt_path, "chunk_ids": chunk_ids, "prompt_sha256": locked["prompt_sha256"],
              "expected_prompt_tokens": int(locked["input_tokens"]), "attempts": attempts}
    for trial in range(1, 4):
        started = perf_counter()
        retry = False
        try:
            with urlopen(request, timeout=240) as response:
                reply = json.load(response)
            usage, choice = reply["usage"], reply["choices"][0]
            raw = choice["message"]["content"]
            if usage["prompt_tokens"] != result["expected_prompt_tokens"]:
                raise ValueError(f"Service usage {usage['prompt_tokens']} != {result['expected_prompt_tokens']}")
            if not isinstance(raw, str) or not isinstance(usage["completion_tokens"], int):
                raise ValueError("Unusable response type")
            parsed = v2.parse_response(raw)
            cited = sorted({chunk_ids[i - 1] for i in parsed["citations"] if 1 <= i <= len(chunk_ids)})
            result.update(ok=True, answer=parsed["answer"], raw=raw, parse_ok=parsed["parse_ok"],
                          cited_chunk_ids=cited, invalid_citations=sum(not 1 <= i <= len(chunk_ids) for i in parsed["citations"]),
                          input_tokens=usage["prompt_tokens"], output_tokens=usage["completion_tokens"],
                          finish_reason=choice["finish_reason"], response_id=reply["id"])
            attempts.append({"trial": trial, "seconds": perf_counter() - started, "http_status": 200})
            return result
        except HTTPError as exc:
            retry = exc.code in {408, 429, 500, 502, 503, 504}
            detail = {"http_status": exc.code, "error": exc.read(2048).decode(errors="replace")}
        except (URLError, TimeoutError, OSError) as exc:
            retry = True
            detail = {"error": str(exc)}
        except (KeyError, ValueError, IndexError, TypeError) as exc:
            detail = {"error": str(exc)}
        attempts.append({"trial": trial, "seconds": perf_counter() - started, **detail})
        if not retry:
            break
        if trial < 3:
            sleep(2 ** (trial - 1))
    return result | {"ok": False}


def route_one(v2, row, route, audit, protocol, block, phase):
    start = perf_counter()
    spec = protocol["routes"][route]
    path = spec["prompt_path"]
    chunks = row["input"]["contexts"]
    example = {"question": row["input"]["question"],
               "context": [[chunk["title"], [s["text"] for s in chunk["sentences"]]] for chunk in chunks]}
    calls = []
    if spec["first_answer"]:
        first, _ = v2.retrieve_indices(example, 2, 0)
        calls.append(generate(v2, "top2", first, example, chunks, row, audit, protocol))
    if not calls or calls[-1]["ok"]:
        if path == "full":
            indices = list(range(len(chunks)))
        elif path.startswith("top"):
            indices, _ = v2.retrieve_indices(example, int(path[3:]), 0)
        else:
            first, extra = v2.retrieve_indices(example, 2, int(path[-1]))
            indices = first + extra
        calls.append(generate(v2, path, indices, example, chunks, row, audit, protocol))
    return {"phase": phase, "qid": row["qid"], "pool_size": row["pool_size"], "pool_sha256": row["pool_sha256"],
            "route": route, "block": block, "elapsed_seconds": perf_counter() - start, "calls": calls,
            "ok": len(calls) == 1 + spec["first_answer"] and all(call["ok"] for call in calls),
            "recorded_at_utc": utc_now()}


def run_batches(args, v2, pools, audit, protocol, qids, sizes):
    routes = list(protocol["routes"])
    worker_count = protocol["client_workers"]
    answers_path = args.out / "records.jsonl"
    success = {}
    if answers_path.exists():
        for old in read_jsonl(answers_path):
            if old["ok"]:
                key = old["pool_size"], old["qid"], old["route"]
                if key in success:
                    raise ValueError(f"Duplicate success in journal: {key}")
                success[key] = old
    matches = len(qids) * len(sizes) * len(routes)
    with (ThreadPoolExecutor(max_workers=worker_count) as pool,
          answers_path.open("a", encoding="utf-8") as journal,
          (args.out / "batches.jsonl").open("a", encoding="utf-8") as batches,
          (args.out / "warmups.jsonl").open("a", encoding="utf-8") as warmups):
        for size in sizes if not success else []:
            for route in ("top2", "full"):
                for qid in qids[:2]:
                    row = route_one(v2, pools[size, qid], route, audit, protocol, -1, "warmup")
                    append(warmups, row)
                    if not row["ok"]:
                        raise RuntimeError(f"Warm-up failed: {row}")
        methods = [(size, route) for size in sizes for route in routes]
        for block, start in enumerate(range(0, len(qids), worker_count)):
            rotation = block % len(methods)
            for size, route in methods[rotation:] + methods[:rotation]:
                block_ids = qids[start:start + worker_count]
                pending = [qid for qid in block_ids if (size, qid, route) not in success]
                if not pending:
                    continue
                clock = perf_counter()
                futures = [pool.submit(route_one, v2, pools[size, qid], route, audit, protocol, block, "experiment")
                           for qid in pending]
                failures = 0
                for future in as_completed(futures):
                    row = future.result()
                    append(journal, row)
                    if row["ok"]:
                        success[size, row["qid"], route] = row
                    else:
                        failures += 1
                batch = {"block": block, "pool_size": size, "route": route, "submitted": len(pending),
                         "failed": failures, "seconds": perf_counter() - clock, "completed": len(success),
                         "expected": matches, "recorded_at_utc": utc_now()}
                append(batches, batch)
                print(json.dumps(batch), flush=True)
    if len(success) != matches:
        raise RuntimeError(f"Partial P1.5 coverage: {len(success)} of {matches}. Resume reuses successful rows.")
    return matches


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pools", type=Path, required=True)
    parser.add_argument("--lengths", type=Path, required=True)
    parser.add_argument("--v2", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cap", type=int, required=True, choices=(8192, 16384))
    args = parser.parse_args()
    protocol_path = HERE / "protocol.json"
    protocol = json.loads(protocol_path.read_text())
    sizes = protocol["services"][str(args.cap)]["pool_sizes"]
    pools = load_pools(args.pools, sizes)
    qids = sorted({qid for _, qid in pools}, key=lambda qid: digest(["p15", protocol["scheduler_seed"], qid]))
    if len(qids) != 50 or set(pools) != {(size, qid) for size in sizes for qid in qids}:
        raise ValueError("Expected the complete same panel of 50 across service pool sizes")
    with args.lengths.open(encoding="utf-8") as stream:
        audit = {(int(r["pool_size"]), r["qid"], r["path"]): r for r in csv.DictReader(stream)}
    for size, qid in pools:
        for spec in protocol["routes"].values():
            row = audit[size, qid, spec["prompt_path"]]
            if int(row["total_tokens"]) > args.cap or int(row["output_reserved"]) != protocol["max_output_tokens"]:
                raise ValueError(f"Incompatible length budget: {size} {qid}")
    core = {name: file_hash(path) for name, path in {
        "pools": args.pools, "lengths": args.lengths, "protocol": protocol_path, "runner": Path(__file__),
        "v2_retrieval": args.v2 / "bm25_topk.py", "v2_prompt": args.v2 / "compare_models.py",
    }.items()}
    expected = {"sha256": core, "cap": args.cap, "sizes": sizes, "qid_order": qids}
    args.out.mkdir(parents=True, exist_ok=True)
    identity = args.out / "identity.json"
    if identity.exists() and json.loads(identity.read_text()) != expected:
        raise ValueError("Refusing to mix incompatible P1.5 inputs or service settings")
    identity.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    sys.path.insert(0, str(args.v2))
    import compare_models as v2

    service_ready(protocol, args.cap)
    n = run_batches(args, v2, pools, audit, protocol, qids, sizes)
    (args.out / "complete.json").write_text(json.dumps({"route_records": n, "finished_at_utc": utc_now()}) + "\n")


if __name__ == "__main__":
    main()

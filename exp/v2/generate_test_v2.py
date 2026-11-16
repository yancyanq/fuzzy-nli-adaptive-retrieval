"""Generate shared answers and sentence references for Protocol V2 step 5."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from threading import Lock
from types import SimpleNamespace

import analyze_pilot_signals_v2 as signals
import calibrate_gates_v2 as gates
import run_pilot as pilot

cm = pilot.cm


MODEL = "Qwen/Qwen2.5-7B-Instruct"
TEST_SHA = "6d9acf8c4b759406b206f82cd01da7c575046bc584259d9fe11b8cb564f95426"
LOCK_SHA = "ad4a0390042c40d934d445e9127b109e69031c112b1c1ecf08fed265a40a58ed"
SCORER_SHA = "d35fc91a6db21d791dbdda11daf3856e9359f5701d54e3eefba20d88fecc02c0"
BRANCHES = ("A", "B", "full")
DECODE = SimpleNamespace(max_tokens=128, temperature=0, timeout=120, max_retries=3)
CANDIDATE_LIMIT = 4096 - DECODE.max_tokens


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_cache(path, fields, expected):
    records = {}
    if not path.exists():
        return records
    with path.open("rb+") as stream:
        while True:
            start = stream.tell()
            line = stream.readline()
            if not line:
                break
            if not line.endswith(b"\n"):
                stream.truncate(start)
                break
            row = json.loads(line)
            key = tuple(row[field] for field in fields)
            if key in records or key not in expected:
                raise ValueError(f"Unexpected or duplicate cache key {key}")
            records[key] = row
    return records


def append_record(stream, record):
    stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
    stream.flush()


def load_test(path):
    if sha256(path) != TEST_SHA:
        raise ValueError("Held-out manifest hash mismatch")
    rows = read_json(path)
    if len(rows) != 1000 or len({row["_id"] for row in rows}) != 1000:
        raise ValueError("Invalid held-out manifest")
    return rows


def load_lock(path, serve_script=None):
    if sha256(path) != LOCK_SHA:
        raise ValueError("Gate lock hash mismatch")
    lock = read_json(path)
    sources = {Path(module.__file__).name: module.__file__ for module in (cm, pilot, signals, gates)}
    sources["bm25_topk.py"] = cm._BM25_SRC
    for script, expected in lock["source_sha256"].items():
        if not sources.get(script) or sha256(sources[script]) != expected:
            raise ValueError(f"Locked code hash mismatch: {script}")
    if serve_script and sha256(serve_script) != lock["serve_script"]["sha256"]:
        raise ValueError("Serving script hash mismatch")
    return lock


def load_official(path):
    if sha256(path) != SCORER_SHA:
        raise ValueError("Official scorer hash mismatch")
    spec = importlib.util.spec_from_file_location("hotpot_evaluate_v1", path)
    module = importlib.util.module_from_spec(spec)
    if importlib.util.find_spec("ujson") is not None:
        spec.loader.exec_module(module)
    else:
        sys.modules["ujson"] = json
        try:
            spec.loader.exec_module(module)
        finally:
            del sys.modules["ujson"]
    return module


def stable_sample(examples, n):
    return sorted(examples, key=lambda ex: hashlib.sha256(f"42:{ex['_id']}".encode()).hexdigest())[:n]


def scoring_row(official, ex, answer, sp):
    metrics = Counter()
    official.update_answer(metrics, answer, ex["answer"])
    official.update_sp(metrics, sp, ex["supporting_facts"])
    return dict(metrics)


def answer_request(client, ex, indices):
    packed = cm.call_with_retries(client, MODEL, cm.build_messages(ex, indices), DECODE)
    if packed.get("error") or not packed.get("content", "").strip():
        raise RuntimeError(f"Answer request failed on {ex['_id']}: {packed.get('error')}")
    parsed = cm.parse_response(packed["content"])
    citations, _ = cm.map_citations(parsed["citations"], indices, ex)
    return {
        "answer": parsed["answer"],
        "citations": citations,
        "parse_ok": parsed["parse_ok"],
        "paragraph_indices": list(indices),
        "raw": packed["content"],
        "prompt_tokens": packed["prompt_tokens"],
        "completion_tokens": packed["completion_tokens"],
        "latency": packed["latency"],
    }


def sentence_candidates(ex, answer):
    retrieved = answer["paragraph_indices"]
    cited = pilot.unique_in_order(n for n in answer["citations"] if type(n) is int and 1 <= n <= len(retrieved))
    return [(title, i, sentence) for n in cited for title, sentences in [ex["context"][retrieved[n - 1]]]
            for i, sentence in enumerate(sentences)]


def selector_messages(ex, answer, candidates):
    numbered = "\n".join(f"[{candidate_id}] ({title}) {sentence}"
                         for candidate_id, (title, _, sentence) in candidates)
    return [
        {"role": "system", "content": "Identify the minimum set of supplied sentences that directly support the given answer to the question. Include intermediate evidence that links the reasoning steps. Use ONLY the numbered candidates, and keep the given answer fixed."},
        {"role": "user", "content": f"Question: {ex['question']}\nFixed answer: {answer['answer']}\n"
         f"Candidate sentences:\n{numbered}\n\nRespond only with a JSON object in the form "
         '{"sentence_ids": [<candidate IDs>]}. Use an empty list when no candidate supports the answer.'},
    ]


def parse_selector(content, allowed):
    try:
        ids = json.loads(content)["sentence_ids"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return [], False, 0
    if not isinstance(ids, list):
        return [], False, 0
    valid = [i for i in ids if type(i) is int and i in allowed]
    return pilot.unique_in_order(valid), True, len(ids) - len(valid)


def select_evidence(client, tokenizer, ex, answer):
    candidates = dict(enumerate(sentence_candidates(ex, answer), start=1))
    evidence_calls = []
    selected = []
    stack = [list(candidates.items())] if candidates else []
    while stack:
        chunk = stack.pop()
        messages = selector_messages(ex, answer, chunk)
        count = len(tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True))
        if count > CANDIDATE_LIMIT:
            mid = len(chunk) // 2
            if not mid:
                raise ValueError(f"One sentence exceeds the model context for {ex['_id']}")
            stack.extend((chunk[mid:], chunk[:mid]))
            continue
        packed = cm.call_with_retries(client, MODEL, messages, DECODE)
        if packed.get("error"):
            raise RuntimeError(f"Evidence request failed on {ex['_id']}: {packed['error']}")
        ids, valid, invalid = parse_selector(packed["content"], dict(chunk))
        selected.extend(ids)
        evidence_calls.append({key: packed[key] for key in ("content", "prompt_tokens", "completion_tokens", "latency")}
                              | {"parse_ok": valid, "invalid_ids": invalid, "ids": ids})
    return {"sp": [[candidates[i][0], candidates[i][1]] for i in pilot.unique_in_order(selected)],
            "evidence_calls": evidence_calls, "candidate_count": len(candidates)}


def parallel_results(jobs, worker, workers=8):
    jobs = iter(jobs)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(worker, job) for _, job in zip(range(workers), jobs)}
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                yield future.result()
                job = next(jobs, None)
                if job is not None:
                    pending.add(pool.submit(worker, job))


def generate(args, client, tokenizer):
    questions = load_test(args.data)
    jobs = []
    for ex in questions:
        first, second = cm.retrieve_indices(ex, 2, 1)
        jobs.extend((ex, branch, indices) for branch, indices in
                    zip(BRANCHES, (first, first + second, list(range(len(ex["context"]))))))
    fields = ("model", "_id", "branch")
    expected = {(MODEL, ex["_id"], branch) for ex, branch, _ in jobs}
    answers_path = args.out / "answers_test_v2.jsonl"
    evidence_path = args.out / "evidence_test_v2.jsonl"
    answers = read_cache(answers_path, fields, expected)
    evidence = read_cache(evidence_path, fields, expected)
    if evidence.keys() - answers.keys():
        raise ValueError("Evidence cache has references with missing source answers")

    def resolve(job):
        ex, branch, indices = job
        key = (MODEL, ex["_id"], branch)
        identity = dict(zip(fields, key))
        answer = answers.get(key)
        if answer is None:
            answer = identity | answer_request(client, ex, indices)
            with answer_write_lock:
                append_record(aw, answer)
        elif answer["paragraph_indices"] != indices:
            raise ValueError(f"Cached answer retrieval mismatch: {key}")
        return identity | select_evidence(client, tokenizer, ex, answer)

    pending = [job for job in jobs if (MODEL, job[0]["_id"], job[1]) not in evidence]
    print(f"Formal generation starting with {len(evidence)}/{len(expected)} complete", flush=True)
    answer_write_lock = Lock()
    with answers_path.open("a", encoding="utf-8") as aw, evidence_path.open("a", encoding="utf-8") as ew:
        for done, sp in enumerate(parallel_results(pending, resolve, args.workers), len(evidence) + 1):
            append_record(ew, sp)
            if done % 25 == 0 or done == len(expected):
                print(f"Completed {done}/{len(expected)} answer/evidence pairs", flush=True)


def smoke(args, client, tokenizer):
    if sha256(args.tune) != "478f6b2f4d7506a0b8d804de5aa077eacdd3ef20d90f127ac8d22999453ea53b":
        raise ValueError("Tune manifest hash mismatch")
    if sha256(args.dev_cache) != "dac04d277b02230709207fce727adcd9e2aadb71c05f84cf41a8497abe62b439":
        raise ValueError("Scored dev cache hash mismatch")
    examples = stable_sample(read_json(args.tune), 24)
    with args.dev_cache.open(encoding="utf-8") as stream:
        dev = {row["_id"]: row for row in map(json.loads, stream)}
    official = load_official(args.scorer)

    def resolve(job):
        ex, branch = job
        if branch == "full":
            answer = answer_request(client, ex, list(range(len(ex["context"]))))
        else:
            answer = dev[ex["_id"]][branch]
        evidence = select_evidence(client, tokenizer, ex, answer)
        return {"_id": ex["_id"], "branch": branch, "answer": answer["answer"], **evidence,
                "metrics": scoring_row(official, ex, answer["answer"], evidence["sp"])}

    jobs = [(ex, branch) for ex in examples for branch in ("A", "B")]
    jobs.extend((ex, "full") for ex in examples[:8])
    results = list(parallel_results(jobs, resolve, args.workers))
    write_json(args.out / "dev_selector_smoke.json", results)
    calls = [call for row in results for call in row["evidence_calls"]]
    summary = {
        "branches": len(results), "selector_calls": len(calls),
        "parsed_calls": sum(call["parse_ok"] for call in calls),
        "invalid_ids": sum(call["invalid_ids"] for call in calls),
        "nonempty_sp": sum(bool(row["sp"]) for row in results),
        "max_prompt_tokens": max((call["prompt_tokens"] for call in calls), default=0),
    }
    if not calls or not summary["parsed_calls"] or not summary["nonempty_sp"]:
        raise ValueError("Development smoke produced no usable sentence selection")
    print(json.dumps(summary), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("smoke", "generate"))
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tokenizer", required=True)
    parser.add_argument("--scorer", type=Path, required=True)
    parser.add_argument("--tune", type=Path, default=Path("tune.json"))
    parser.add_argument("--dev-cache", type=Path, default=Path("step4_dev/nli/branches.jsonl"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--lock", type=Path, default=Path("step4_dev/gates/locked_gates.json"))
    parser.add_argument("--serve-script", type=Path, default=Path(".serve-step4.sh"))
    args = parser.parse_args()
    load_lock(args.lock, args.serve_script)
    from transformers import AutoTokenizer

    args.out.mkdir(parents=True, exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, local_files_only=True)
    client = cm.make_client(args.base_url, "VLLM_API_KEY", allow_missing_key=True)
    if args.stage == "smoke":
        smoke(args, client, tokenizer)
    else:
        generate(args, client, tokenizer)


if __name__ == "__main__":
    main()

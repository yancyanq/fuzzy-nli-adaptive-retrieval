"""Exercise a running, approved vLLM service without scoring any dataset."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from threading import Barrier
from time import perf_counter
from urllib.error import HTTPError
from urllib.request import Request, urlopen


MODEL = "Qwen/Qwen2.5-7B-Instruct"
RESERVED_OUTPUT = 128


def run_request(url, tokenizer_ids, position, input_tokens, barrier, timeout=180):
    # Use distinct initial tokens so concurrent requests cannot share a cached
    # synthetic prefix. The bytes are valid Qwen tokens from tokenizer.json.
    prompt = [tokenizer_ids[position]] + [tokenizer_ids[-1]] * (input_tokens - 1)
    body = {"model": MODEL, "prompt": prompt, "temperature": 0,
            "max_tokens": RESERVED_OUTPUT, "ignore_eos": True}
    request = Request(url, data=json.dumps(body).encode(),
                      headers={"Content-Type": "application/json"})
    barrier.wait()
    started = perf_counter()
    row = {"request": position + 1, "requested_input": input_tokens}
    try:
        with urlopen(request, timeout=timeout) as response:
            usage = json.load(response)["usage"]
        row.update(prompt_tokens=usage["prompt_tokens"], completion_tokens=usage["completion_tokens"])
        row["ok"] = row["prompt_tokens"] == input_tokens and row["completion_tokens"] == RESERVED_OUTPUT
    except HTTPError as exc:
        row.update(ok=False, http_status=exc.code, error=exc.read(4096).decode(errors="replace"))
    except (OSError, ValueError, KeyError) as exc:
        row.update(ok=False, error=str(exc))
    row["seconds"] = round(perf_counter() - started, 3)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokenizer", required=True, help="Path to the verified Qwen tokenizer.json")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--context", type=int, choices=(4096, 8192, 16384), required=True)
    parser.add_argument("--parallel", type=int, choices=(1, 8), required=True)
    parser.add_argument("--input-tokens", type=int, help="Defaults to context minus 128")
    args = parser.parse_args()
    input_tokens = args.context - RESERVED_OUTPUT if args.input_tokens is None else args.input_tokens
    if not 1 < input_tokens <= args.context - RESERVED_OUTPUT:
        parser.error("input tokens plus the 128-token generation must fit the context")

    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(args.tokenizer)
    words = ("one", "two", "three", "four", "five", "six", "seven", "eight", " text")
    encoded = [tokenizer.encode(word, add_special_tokens=False).ids for word in words]
    if any(len(ids) != 1 for ids in encoded) or len({ids[0] for ids in encoded}) != len(words):
        raise ValueError("Expected distinct single-token Qwen inputs")
    token_ids = [ids[0] for ids in encoded]

    base = f"http://127.0.0.1:{args.port}/v1"
    with urlopen(base + "/models", timeout=5) as response:
        models = json.load(response)["data"]
    model = next((item for item in models if item["id"] == MODEL), {})
    if model.get("max_model_len") != args.context:
        raise SystemExit(f"Expected {MODEL} with server max_model_len={args.context}")
    barrier = Barrier(args.parallel)
    started = perf_counter()
    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        pending = [pool.submit(run_request, base + "/completions", token_ids, i, input_tokens, barrier)
                   for i in range(args.parallel)]
        rows = [request.result() for request in pending]
    result = {"model": MODEL, "server_context": args.context, "client_parallel": args.parallel,
              "wall_seconds": round(perf_counter() - started, 3), "requests": rows}
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if all(row["ok"] for row in rows) else 1)


if __name__ == "__main__":
    main()

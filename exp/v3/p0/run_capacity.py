"""Measure the pinned vLLM service on an isolated loopback port."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
from threading import Barrier, Event
from time import monotonic, perf_counter, sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from probe_vllm import MODEL, RESERVED_OUTPUT, run_request


HOST = "127.0.0.1"
MAX_CONCURRENT_REQUESTS = 8
METRIC = re.compile(r"^vllm:(num_requests_running|num_requests_waiting|gpu_cache_usage_perc)(?:\{[^}]*\})? ([0-9.eE+\-]+)", re.M)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def read_gpu():
    line = subprocess.check_output([
        "nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,driver_version",
        "--format=csv,noheader,nounits",
    ], text=True, timeout=10)
    (index, name, total, used, driver), = csv.reader(line.splitlines(), skipinitialspace=True)
    return {"index": int(index), "name": name, "total_mib": int(total), "used_mib": int(used), "driver": driver}


def read_json(url, timeout, body=None):
    if body is not None:
        url = Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urlopen(url, timeout=timeout) as response:
        return json.load(response)


def watch(base, result, stop):
    while not stop.is_set():
        row = {"utc": utc_now()}
        try:
            row["used_mib"] = read_gpu()["used_mib"]
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            row["gpu_error"] = str(exc)
        try:
            with urlopen(base + "/metrics", timeout=1) as response:
                metrics = METRIC.findall(response.read().decode())
            for name, value in metrics:
                row[name] = max(float(value), row.get(name, 0))
        except OSError:
            pass
        result.append(row)
        stop.wait(0.4)


def measured(base, action, telemetry_path):
    observations = []
    stop = Event()
    with ThreadPoolExecutor(max_workers=1) as monitor:
        reading = monitor.submit(watch, base, observations, stop)
        started = perf_counter()
        try:
            result = action()
        finally:
            stop.set()
            reading.result()
            telemetry_path.write_text("".join(json.dumps(row) + "\n" for row in observations))
    peaks = {name: max((row[name] for row in observations if name in row), default=None)
             for name in ("used_mib", "num_requests_running", "num_requests_waiting", "gpu_cache_usage_perc")}
    return {"wall_seconds": round(perf_counter() - started, 3), "peak": peaks, "sample_count": len(observations),
            "telemetry": telemetry_path.name, "result": result}


def wait_ready(base, process, cap):
    deadline = monotonic() + 420
    while monotonic() < deadline:
        if process.poll() is not None:
            return {"ok": False, "error": f"Server exited {process.returncode}, see service log"}
        try:
            response = read_json(base + "/v1/models", timeout=2)
        except (OSError, ValueError):
            sleep(1)
            continue
        card = next((model for model in response["data"] if model["id"] == MODEL), {})
        return {"ok": card.get("max_model_len") == cap, "reported_max_model_len": card.get("max_model_len")}
    return {"ok": False, "error": "Server did not become ready within 420 seconds"}


def live_chat(base, case, barrier):
    started = perf_counter()
    barrier.wait()
    row = {k: case[k] for k in ("qid", "pool_size", "pool_sha256", "prompt_sha256", "input_tokens")}
    try:
        reply = read_json(base + "/v1/chat/completions", 360, {
            "model": MODEL, "messages": case["messages"], "max_tokens": RESERVED_OUTPUT, "temperature": 0,
        })
        usage = reply["usage"]
        choice = reply["choices"][0]
        row.update(prompt_tokens=usage["prompt_tokens"], completion_tokens=usage["completion_tokens"],
                   finish_reason=choice["finish_reason"])
        row["ok"] = (row["prompt_tokens"] == row["input_tokens"] and 0 < row["completion_tokens"] <= RESERVED_OUTPUT
                     and isinstance(choice["message"]["content"], str) and bool(choice["message"]["content"].strip()))
    except HTTPError as exc:
        row.update(ok=False, http_status=exc.code, error=exc.read(4096).decode(errors="replace"))
    except (OSError, KeyError, IndexError, ValueError) as exc:
        row.update(ok=False, error=str(exc))
    row["seconds"] = round(perf_counter() - started, 3)
    return row


def batch_chat(base, cases):
    barrier = Barrier(len(cases))
    with ThreadPoolExecutor(max_workers=len(cases)) as executor:
        pending = [executor.submit(live_chat, base, case, barrier) for case in cases]
        return [future.result() for future in pending]


def shutdown(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def profile(args, cap, cases, output, repeats):
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(args.model / "tokenizer.json"))
    encoded = tokenizer.encode(" text", add_special_tokens=False).ids
    if len(encoded) != 1:
        raise ValueError("Synthetic input must be a single known Qwen token")
    with socket.socket() as port_check:
        port_check.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        port_check.bind((HOST, args.port))
    base = f"http://{HOST}:{args.port}"
    argv = [
        sys.executable, "-m", "vllm.entrypoints.openai.api_server", "--model", str(args.model),
        "--served-model-name", MODEL, "--host", HOST, "--port", str(args.port), "--max-logprobs", "5",
        "--load-format", "safetensors", "--dtype", "half", "--max-model-len", str(cap),
        "--max-num-seqs", str(MAX_CONCURRENT_REQUESTS), "--cpu-offload-gb", str(args.cpu_offload),
        "--enforce-eager",
    ]
    env = dict(os.environ, VLLM_USE_V1="0", VLLM_ATTENTION_BACKEND="XFORMERS",
               HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", VLLM_NO_USAGE_STATS="1")
    result = {"cap": cap, "gpu_before_start": read_gpu(), "args": argv[2:], "utc_start": utc_now()}
    try:
        with (output / f"{cap}-server.log").open("w") as log:
            process = subprocess.Popen(argv, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                result["startup"] = measured(base, lambda: wait_ready(base, process, cap),
                                              output / f"{cap}-startup.jsonl")
                if result["startup"]["result"]["ok"]:
                    result["gpu_ready"] = read_gpu()
                    result["real_single"] = measured(base, lambda: batch_chat(base, cases[:1]),
                                                      output / f"{cap}-real-single.jsonl")
                    result["boundary_single"] = measured(
                        base, lambda: run_request(base + "/v1/completions", encoded, 0,
                                                  cap - RESERVED_OUTPUT, Barrier(1), timeout=360),
                        output / f"{cap}-boundary.jsonl",
                    )
                    result["real_concurrent"] = [
                        measured(base, lambda: batch_chat(base, cases), output / f"{cap}-real-concurrent-{i}.jsonl")
                        for i in range(1, repeats + 1)
                    ]
            finally:
                shutdown(process)
    finally:
        result["utc_finish"] = utc_now()
        result["gpu_after_stop"] = read_gpu()
        (output / f"{cap}-summary.json").write_text(json.dumps(result, indent=2) + "\n")
        print(f"{cap}: {output / f'{cap}-summary.json'}", flush=True)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--model", required=True, type=Path)
    cli.add_argument("--cases", required=True, type=Path)
    cli.add_argument("--out", required=True, type=Path)
    cli.add_argument("--caps", nargs="+", type=int, default=[4096, 8192, 16384], choices=[4096, 8192, 16384])
    cli.add_argument("--port", type=int, default=18080)
    cli.add_argument("--cpu-offload", type=float, default=4)
    cli.add_argument("--repeats", type=int, default=1, choices=[1, 2, 3])
    args = cli.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    cases = json.loads(args.cases.read_text())
    for cap in args.caps:
        group = cases[str(cap)]
        if (len(group) != MAX_CONCURRENT_REQUESTS
                or any(case["input_tokens"] + RESERVED_OUTPUT > cap for case in group)):
            raise ValueError(f"Expected eight verified complete P1 prompts within {cap}")
    for cap in args.caps:
        profile(args, cap, cases[str(cap)], args.out, args.repeats)
        sleep(3)


if __name__ == "__main__":
    main()

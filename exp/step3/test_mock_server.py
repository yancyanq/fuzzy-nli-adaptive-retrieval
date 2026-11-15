#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tiny OpenAI-compatible Chat Completions mock for step 3 local tests.

Usage:
  python test_mock_server.py --port 8765
  python test_mock_server.py --port 8766 --reject-logprobs
  python test_mock_server.py --port 8765 --answers-from pilot.json
  python test_mock_server.py --port 8767 --top-logprobs-mode deepseek_t0
  python test_mock_server.py --port 8768 --top-logprobs-mode vllm_healthy

With --top-logprobs-mode deepseek_t0 (Step 5b tests; also used by Step 6a FAIL),
a request that sets top_logprobs=N gets N FAKE alternatives per token. At
temperature 0 the chosen token's logprob is reported as 0.0 (also inside its
own alternative entry), while the other alternatives are non-zero, mimicking
what the user's probe saw from deepseek-chat. All numbers are deterministic
fakes, not model output.

With --top-logprobs-mode vllm_healthy (Step 6a PASS; opt-in, default unchanged),
the chosen-token logprob is a FAKE but ordinary negative value, never exactly
0.0, and equals the top-1 alternative. Other alternatives are ordinary negative
logprobs (not placeholder sentinels such as -9999). This is only a pipeline
fixture, not a real model.

POST /v1/chat/completions  (also /chat/completions)

With --reject-logprobs, any request that sets logprobs=true gets HTTP 400
so compare_models.py can exercise its fallback path.

Optional --answers-from <official HotpotQA JSON> lets the mock look up the
gold answer by question text. Branch A (2 numbered paragraphs) gets a
deliberately weaker answer; branch B (3+ paragraphs) gets the gold answer.
This is only for pipeline testing, not a real model.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GOLD = {}
REJECT_LOGPROBS = False
REQUEST_LOG = []
LOG_LOCK = threading.Lock()
COUNTER_PATH = None
TOP_LP_MODE = "empty"


def load_gold(path):
    gold = {}
    if not path:
        return gold
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for ex in data:
        q = (ex.get("question") or "").strip()
        if q:
            gold[q] = ex.get("answer") or ""
    return gold


def count_paragraphs(user_text):
    return len(re.findall(r"^\[\d+\]", user_text, flags=re.MULTILINE))


def first_title(user_text):
    m = re.search(r"^\[1\] Title:\s*(.+)$", user_text, flags=re.MULTILINE)
    return m.group(1).strip() if m else "unknown"


def extract_question(user_text):
    m = re.search(r"^Question:\s*(.+)$", user_text, flags=re.MULTILINE)
    return m.group(1).strip() if m else ""


def make_answer(user_text):
    n_paras = count_paragraphs(user_text)
    question = extract_question(user_text)
    gold = GOLD.get(question)
    if gold:
        if n_paras >= 3:
            answer = gold
            cites = list(range(1, n_paras + 1))
        else:
            # weaker / wrong on purpose so A and B can differ
            answer = first_title(user_text)
            if normalize_loose(answer) == normalize_loose(gold):
                answer = "unknown"
            cites = [1]
    else:
        answer = first_title(user_text)
        cites = [1] if n_paras >= 1 else []
    return {"answer": answer, "citations": cites}


def normalize_loose(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def tokenize_for_logprobs(text):
    # Character-group tokens, good enough for a mock logprobs payload
    parts = re.findall(r"\s+|\w+|[^\s\w]", text)
    return parts or [text or " "]


def _fake_unit(seed_text):
    """Deterministic pseudo-random number in [0, 1) from a string (no RNG state)."""
    import hashlib
    h = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    return int(h[:8], 16) / float(0x100000000)


def fake_top_alternatives(text, i, tok, n_top, temperature):
    """FAKE top-N alternatives for token i. Chosen token is ranked first."""
    u = _fake_unit(f"{text}|{i}|{tok}")
    # second-best alternative between about -0.05 and -6.0 (fake spread)
    second = -(0.05 + 5.95 * u)
    chosen_true = -0.6 * u * u  # fake "true" chosen logprob (> second)
    alts = []
    chosen_reported = 0.0 if temperature == 0 else round(chosen_true, 6)
    alts.append({"token": tok, "logprob": chosen_reported, "bytes": list(tok.encode("utf-8"))})
    for j in range(1, n_top):
        lp = round(second - 1.3 * (j - 1) - 0.2 * _fake_unit(f"{text}|{i}|{j}"), 6)
        alt_tok = f"{tok}_alt{j}"
        alts.append({"token": alt_tok, "logprob": lp, "bytes": list(alt_tok.encode("utf-8"))})
    return chosen_reported, alts


def fake_vllm_healthy_alternatives(text, i, tok, n_top):
    """FAKE but non-degenerate alternatives, roughly like a local vLLM server.

    Chosen logprob is an ordinary negative value, never exactly 0.0, and equals
    the top-1 alternative. Other alternatives are ordinary negative logprobs,
    not placeholder sentinels. Deterministic; not model output.
    """
    u = _fake_unit(f"vllm|{text}|{i}|{tok}")
    chosen = -(1e-5 + 3.99999 * u)  # about (-4.0, -1e-5]
    chosen = round(chosen, 6)
    if chosen == 0.0:
        chosen = -1e-6
    alts = [{"token": tok, "logprob": chosen, "bytes": list(tok.encode("utf-8"))}]
    for j in range(1, n_top):
        gap = 0.05 + 4.0 * _fake_unit(f"vllm-gap|{text}|{i}|{tok}|{j}") + 0.4 * (j - 1)
        lp = round(chosen - gap, 6)
        alt_tok = f"{tok}_alt{j}"
        alts.append({"token": alt_tok, "logprob": lp, "bytes": list(alt_tok.encode("utf-8"))})
    return chosen, alts


def fake_logprobs(text, n_top=0, temperature=0.0):
    tokens = tokenize_for_logprobs(text)
    content = []
    for i, tok in enumerate(tokens):
        if TOP_LP_MODE == "deepseek_t0" and n_top > 0:
            lp, alts = fake_top_alternatives(text, i, tok, n_top, temperature)
        elif TOP_LP_MODE == "vllm_healthy" and n_top > 0:
            lp, alts = fake_vllm_healthy_alternatives(text, i, tok, n_top)
        else:
            # Stable, slightly decreasing fake logprob (Step 3/5 behaviour)
            lp = -0.05 * (i + 1)
            alts = []
        content.append({
            "token": tok,
            "logprob": lp,
            "bytes": list(tok.encode("utf-8")),
            "top_logprobs": alts,
        })
    return {"content": content}


def completion_body(req, request_id):
    model = req.get("model") or "mock-qa"
    messages = req.get("messages") or []
    user_text = ""
    for m in messages:
        if m.get("role") == "user":
            user_text = m.get("content") or ""
    obj = make_answer(user_text)
    content = json.dumps(obj, ensure_ascii=False)
    want_lp = bool(req.get("logprobs"))
    choice = {
        "index": 0,
        "message": {"role": "assistant", "content": content},
        "finish_reason": "stop",
    }
    if want_lp and not REJECT_LOGPROBS:
        try:
            n_top = int(req.get("top_logprobs") or 0)
        except (TypeError, ValueError):
            n_top = 0
        try:
            temp = float(req.get("temperature") if req.get("temperature") is not None else 1.0)
        except (TypeError, ValueError):
            temp = 1.0
        choice["logprobs"] = fake_logprobs(content, n_top=n_top, temperature=temp)
    else:
        choice["logprobs"] = None
    # rough token counts
    prompt_text = "\n".join((m.get("content") or "") for m in messages)
    prompt_tokens = max(1, len(prompt_text.split()))
    completion_tokens = max(1, len(content.split()))
    return {
        "id": request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [choice],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, obj=None, text=None):
        if obj is not None:
            payload = json.dumps(obj).encode("utf-8")
            ctype = "application/json"
        else:
            payload = (text or "").encode("utf-8")
            ctype = "text/plain; charset=utf-8"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        if self.path in ("/health", "/v1/health"):
            self._send(200, {"ok": True, "reject_logprobs": REJECT_LOGPROBS, "n_gold": len(GOLD), "top_logprobs_mode": TOP_LP_MODE})
            return
        self._send(404, {"error": {"message": "not found", "type": "invalid_request_error"}})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path not in ("/v1/chat/completions", "/chat/completions"):
            self._send(404, {"error": {"message": f"unknown path {path}", "type": "invalid_request_error"}})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            req = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._send(400, {"error": {"message": "invalid json", "type": "invalid_request_error"}})
            return

        with LOG_LOCK:
            n = len(REQUEST_LOG) + 1
            request_id = f"chatcmpl-mock-{n}"
            REQUEST_LOG.append({
                "id": request_id,
                "logprobs": bool(req.get("logprobs")),
                "top_logprobs": req.get("top_logprobs"),
                "temperature": req.get("temperature"),
                "model": req.get("model"),
                "path": path,
            })
            if COUNTER_PATH:
                with open(COUNTER_PATH, "w", encoding="utf-8") as f:
                    json.dump({"n_requests": len(REQUEST_LOG), "requests": REQUEST_LOG}, f)

        if REJECT_LOGPROBS and req.get("logprobs"):
            self._send(400, {
                "error": {
                    "message": "This model does not support logprobs.",
                    "type": "invalid_request_error",
                    "param": "logprobs",
                    "code": "unsupported_value",
                }
            })
            return

        body = completion_body(req, request_id)
        self._send(200, body)


def main(argv=None):
    global GOLD, REJECT_LOGPROBS, COUNTER_PATH, TOP_LP_MODE
    ap = argparse.ArgumentParser(description="OpenAI-compatible mock server for step 3")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--reject-logprobs", action="store_true")
    ap.add_argument("--answers-from", default=None, help="Official HotpotQA JSON for gold lookup")
    ap.add_argument("--counter", default=None, help="Write request counts to this JSON file")
    ap.add_argument(
        "--top-logprobs-mode",
        choices=("empty", "deepseek_t0", "vllm_healthy"),
        default="empty",
        help=(
            "empty (default, Step 3/5 behaviour); "
            "deepseek_t0 (FAKE non-zero alternatives, chosen=0.0 at T=0); "
            "vllm_healthy (FAKE ordinary negative chosen logprobs, no placeholders). "
            "Opt-in only; default is unchanged."
        ),
    )
    args = ap.parse_args(argv)
    TOP_LP_MODE = args.top_logprobs_mode

    REJECT_LOGPROBS = bool(args.reject_logprobs)
    GOLD = load_gold(args.answers_from)
    COUNTER_PATH = args.counter

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    mode = "REJECT logprobs" if REJECT_LOGPROBS else f"logprobs supported, top_logprobs mode={TOP_LP_MODE}"
    print(f"mock OpenAI-compatible server on http://{args.host}:{args.port}/v1  ({mode})")
    if args.answers_from:
        print(f"gold answers loaded: {len(GOLD)} from {args.answers_from}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

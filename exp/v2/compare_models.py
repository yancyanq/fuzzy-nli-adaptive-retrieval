#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 3: Compare answer LLMs on HotpotQA (paired A/B branches).

Round-1 (branch A): answer with BM25 top-k paragraphs (default k=2).
Round-2 (branch B): answer with the same k paragraphs plus m rewritten-query
paragraphs (default m=1). Retrieval logic matches bm25_topk.py exactly.

Works with any OpenAI-compatible Chat Completions API:
  DeepSeek, OpenAI, or a later local vLLM endpoint (--preset custom).

Windows examples (run in G:\\NLP_project, never put API keys on the command line):

  set DEEPSEEK_API_KEY=...
  python compare_models.py --data pilot.json --preset deepseek --n 30 --out step3_deepseek

  set OPENAI_API_KEY=...
  python compare_models.py --data pilot.json --preset openai --n 30 --out step3_openai

  python compare_models.py --data pilot.json --preset custom --base-url http://127.0.0.1:8000/v1 ^
      --model Qwen2.5-7B-Instruct --key-env LOCAL_API_KEY --n 30 --out step3_qwen
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import re
import string
import sys
import time
from collections import Counter

# ---------------------------------------------------------------------------
# Windows-friendly stdout
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Retrieval helpers: prefer bm25_topk.py (exact tok / para_text), else copy
# ---------------------------------------------------------------------------
_FALLBACK_STOP = set(
    "a an the of in on at to for and or is are was were be been by with "
    "from as that this which who whom what when where how did does do it "
    "its his her their they he she".split()
)


def _fallback_tok(s):
    return [w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in _FALLBACK_STOP]


def _fallback_para_text(title, sents):
    return title + " " + " ".join(sents)


def _load_bm25_helpers():
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(os.getcwd(), "bm25_topk.py"),
        os.path.join(here, "bm25_topk.py"),
        os.path.join(here, "..", "step2", "bm25_topk.py"),
        "/workspace/exp/step2/bm25_topk.py",
    ]
    for path in candidates:
        path = os.path.abspath(path)
        if os.path.isfile(path):
            spec = importlib.util.spec_from_file_location("bm25_topk", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod.tok, mod.para_text, path
    return _fallback_tok, _fallback_para_text, None


tok, para_text, _BM25_SRC = _load_bm25_helpers()

try:
    from rank_bm25 import BM25Okapi
except ImportError:
    sys.stderr.write("Missing dependency: pip install rank_bm25\n")
    raise


def retrieve_indices(ex, k, m):
    """Return (r1_indices, r2_indices) using the exact bm25_topk.py procedure."""
    titles = [c[0] for c in ex["context"]]
    texts = [para_text(c[0], c[1]) for c in ex["context"]]
    if not texts:
        return [], []
    bm = BM25Okapi([tok(t) for t in texts])
    scores = bm.get_scores(tok(ex["question"]))
    order = sorted(range(len(texts)), key=lambda i: -scores[i])
    k_eff = min(k, len(texts))
    r1 = order[:k_eff]
    top = ex["context"][order[0]]
    q2 = ex["question"] + " " + top[0] + " " + (top[1][0] if top[1] else "")
    unused = [i for i in range(len(texts)) if i not in r1]
    r2 = []
    if unused and m > 0:
        bm2 = BM25Okapi([tok(texts[i]) for i in unused])
        s2 = bm2.get_scores(tok(q2))
        r2 = [unused[j] for j in sorted(range(len(unused)), key=lambda j: -s2[j])[:m]]
    return r1, r2


# ---------------------------------------------------------------------------
# Official HotpotQA normalize / EM / F1 (hotpot_evaluate_v1.py semantics)
# ---------------------------------------------------------------------------
def normalize_answer(s):
    def remove_articles(text):
        return re.sub(r"\b(a|an|the)\b", " ", text)

    def white_space_fix(text):
        return " ".join(text.split())

    def remove_punc(text):
        exclude = set(string.punctuation)
        return "".join(ch for ch in text if ch not in exclude)

    def lower(text):
        return text.lower()

    return white_space_fix(remove_articles(remove_punc(lower(s))))


def f1_score(prediction, ground_truth):
    normalized_prediction = normalize_answer(prediction)
    normalized_ground_truth = normalize_answer(ground_truth)
    zero = (0.0, 0.0, 0.0)
    if normalized_prediction in ["yes", "no", "noanswer"] and normalized_prediction != normalized_ground_truth:
        return zero
    if normalized_ground_truth in ["yes", "no", "noanswer"] and normalized_prediction != normalized_ground_truth:
        return zero
    prediction_tokens = normalized_prediction.split()
    ground_truth_tokens = normalized_ground_truth.split()
    common = Counter(prediction_tokens) & Counter(ground_truth_tokens)
    num_same = sum(common.values())
    if num_same == 0:
        return zero
    precision = 1.0 * num_same / len(prediction_tokens)
    recall = 1.0 * num_same / len(ground_truth_tokens)
    f1 = (2 * precision * recall) / (precision + recall)
    return f1, precision, recall


def exact_match_score(prediction, ground_truth):
    return normalize_answer(prediction) == normalize_answer(ground_truth)


# ---------------------------------------------------------------------------
# Prompt + robust parse
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are a careful question-answering assistant. "
    "Read the numbered paragraphs and answer the question with a short span "
    "(a name, a number, yes/no, or a few words). "
    "Cite the paragraph numbers you used as evidence."
)


def format_paragraphs(ex, indices):
    blocks = []
    for n, i in enumerate(indices, start=1):
        title, sents = ex["context"][i]
        body = " ".join(sents)
        blocks.append(f"[{n}] Title: {title}\n{body}")
    return "\n\n".join(blocks)


def build_messages(ex, indices):
    paras = format_paragraphs(ex, indices)
    user = (
        f"Paragraphs:\n{paras}\n\n"
        f"Question: {ex['question']}\n\n"
        "Respond with a single JSON object and nothing else, in this exact format:\n"
        '{"answer": "<short answer span>", "citations": [<paragraph numbers>]}\n'
        "Use 1-based paragraph numbers. Do not add explanations outside the JSON."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _as_int_list(value):
    if value is None:
        return []
    if isinstance(value, (int, float)):
        return [int(value)]
    if isinstance(value, str):
        nums = re.findall(r"\d+", value)
        return [int(x) for x in nums]
    out = []
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, (int, float)):
                out.append(int(item))
            elif isinstance(item, str):
                nums = re.findall(r"\d+", item)
                out.extend(int(x) for x in nums)
    return out


def parse_response(text):
    """Parse {"answer": ..., "citations": [...]} with several fallbacks."""
    raw = text if isinstance(text, str) else ("" if text is None else str(text))
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
        stripped = stripped.strip()

    candidates = []
    if stripped:
        candidates.append(stripped)
    for match in re.finditer(r"\{[^{}]*\}", stripped, flags=re.DOTALL):
        candidates.append(match.group(0))
    # slightly nested
    match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if match:
        candidates.append(match.group(0))

    seen = set()
    for cand in candidates:
        if cand in seen:
            continue
        seen.add(cand)
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            relaxed = cand.replace("'", '"')
            try:
                obj = json.loads(relaxed)
            except json.JSONDecodeError:
                continue
        if isinstance(obj, dict) and ("answer" in obj or "citations" in obj):
            answer = obj.get("answer", "")
            if answer is None:
                answer = ""
            if not isinstance(answer, str):
                answer = str(answer)
            return {
                "answer": answer.strip(),
                "citations": _as_int_list(obj.get("citations")),
                "parse_ok": True,
            }

    m = re.search(r"(?:answer|答案)\s*[:：]\s*(.+)", stripped, flags=re.IGNORECASE)
    if m:
        ans = m.group(1).strip().strip('"').strip("'")
        ans = re.split(r"[\n\r]", ans, maxsplit=1)[0].strip()
        cites = _as_int_list(stripped)
        return {"answer": ans, "citations": cites, "parse_ok": False}

    # last resort: use the whole text (trim quotes / fences)
    return {"answer": stripped.strip().strip('"'), "citations": [], "parse_ok": False}


def map_citations(citations, indices, ex):
    """Map 1-based citation numbers to paragraph titles. Drop out-of-range."""
    titles = []
    valid_nums = []
    n = len(indices)
    for c in citations:
        if 1 <= c <= n:
            titles.append(ex["context"][indices[c - 1]][0])
            valid_nums.append(c)
    return valid_nums, titles


# ---------------------------------------------------------------------------
# Logprobs helpers
# ---------------------------------------------------------------------------
def _token_logprob_list(resp):
    try:
        choice = resp.choices[0]
        if choice.logprobs is None or not choice.logprobs.content:
            return []
        items = []
        for t in choice.logprobs.content:
            tok_s = getattr(t, "token", None)
            lp = getattr(t, "logprob", None)
            if lp is None:
                continue
            items.append({"token": tok_s if tok_s is not None else "", "logprob": float(lp)})
        return items
    except Exception:
        return []


def summarize_logprobs(token_items, parsed_answer):
    """Mean/min logprob over completion tokens; prefer tokens overlapping the answer."""
    if not token_items:
        return None, None, []
    all_lps = [t["logprob"] for t in token_items]
    used = all_lps
    if parsed_answer:
        needle = parsed_answer.strip()
        concat = "".join(t["token"] for t in token_items)
        # OpenAI often prefixes tokens with a special space char 'Ġ' or raw space
        concat_norm = concat.replace("Ġ", " ").replace("Ċ", "\n")
        start = concat_norm.find(needle)
        if start < 0:
            start = concat_norm.lower().find(needle.lower())
        if start >= 0:
            end = start + len(needle)
            pos = 0
            span = []
            for t in token_items:
                piece = t["token"].replace("Ġ", " ").replace("Ċ", "\n")
                nxt = pos + len(piece)
                if nxt > start and pos < end:
                    span.append(t["logprob"])
                pos = nxt
            if span:
                used = span
    return (sum(used) / len(used), min(used), token_items)


# ---------------------------------------------------------------------------
# API key hygiene
# ---------------------------------------------------------------------------
_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{4,}|Bearer\s+\S+|api[_-]?key\s*[:=]\s*\S+)",
    re.IGNORECASE,
)


def sanitize(text):
    if text is None:
        return ""
    return _SECRET_RE.sub("***", str(text))


def env_flag(name):
    if not name:
        return "none"
    return f"{name}={'set' if os.environ.get(name) else 'MISSING'}"


# ---------------------------------------------------------------------------
# OpenAI-compatible client
# ---------------------------------------------------------------------------
def die(msg, code=2):
    sys.stderr.write(msg.rstrip() + "\n")
    raise SystemExit(code)


PRESETS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "key_env": "DEEPSEEK_API_KEY",
    },
    "openai": {
        "base_url": None,  # official default
        "model": "gpt-4o-mini",
        "key_env": "OPENAI_API_KEY",
    },
}


def resolve_endpoint(args):
    if args.preset == "custom":
        if not args.base_url:
            die("--preset custom requires --base-url")
        if not args.model:
            die("--preset custom requires --model")
        key_env = args.key_env or "LOCAL_API_KEY"
        return args.base_url, args.model, key_env, True
    preset = PRESETS[args.preset]
    base_url = args.base_url if args.base_url else preset["base_url"]
    model = args.model if args.model else preset["model"]
    key_env = args.key_env if args.key_env else preset["key_env"]
    return base_url, model, key_env, False


def make_client(base_url, key_env, allow_missing_key):
    try:
        from openai import OpenAI
    except ImportError:
        sys.stderr.write("Missing dependency: pip install openai\n")
        raise
    key = os.environ.get(key_env) if key_env else None
    if not key:
        if allow_missing_key:
            key = "EMPTY"
            sys.stderr.write(
                f"[warn] {key_env or 'API key'} is unset; using a placeholder key 'EMPTY' "
                "(fine for a local vLLM server that does not check keys).\n"
            )
        else:
            die(
                f"Environment variable {key_env} is not set. "
                "Set it first (see README_step3.md). Do not paste the key into the command line."
            )
    kwargs = {"api_key": key}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def _status_code(exc):
    for attr in ("status_code", "status"):
        val = getattr(exc, attr, None)
        if isinstance(val, int):
            return val
    resp = getattr(exc, "response", None)
    if resp is not None:
        val = getattr(resp, "status_code", None)
        if isinstance(val, int):
            return val
    return None


def is_logprobs_error(exc):
    msg = (str(exc) or "").lower()
    if "logprob" in msg:
        return True
    body = ""
    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            body = (resp.text or "").lower()
        except Exception:
            body = ""
    return "logprob" in body


def is_retryable(exc):
    name = type(exc).__name__.lower()
    if "ratelimit" in name or "apiconnection" in name or "timeout" in name or "apitimeout" in name:
        return True
    code = _status_code(exc)
    if code in {408, 409, 429, 500, 502, 503, 504, 529}:
        return True
    msg = (str(exc) or "").lower()
    if "rate limit" in msg or "too many requests" in msg or "overloaded" in msg:
        return True
    return False


def call_chat(client, model, messages, max_tokens, temperature, want_logprobs, timeout):
    kwargs = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if want_logprobs:
        kwargs["logprobs"] = True
    if timeout is not None:
        kwargs["timeout"] = timeout
    t0 = time.perf_counter()
    resp = client.chat.completions.create(**kwargs)
    latency = time.perf_counter() - t0
    return resp, latency


def pack_response(resp, latency, logprobs_supported, parsed_answer):
    content = ""
    try:
        content = resp.choices[0].message.content or ""
    except Exception:
        content = ""
    prompt_tokens = 0
    completion_tokens = 0
    try:
        if resp.usage is not None:
            prompt_tokens = int(resp.usage.prompt_tokens or 0)
            completion_tokens = int(resp.usage.completion_tokens or 0)
    except Exception:
        pass
    token_items = _token_logprob_list(resp) if logprobs_supported else []
    if logprobs_supported and not token_items:
        logprobs_supported = False
    mean_lp, min_lp, _ = summarize_logprobs(token_items, parsed_answer) if token_items else (None, None, [])
    # store compact logprobs (not the full top_logprobs payload)
    compact = token_items
    return {
        "content": content,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "latency": latency,
        "logprobs_supported": logprobs_supported,
        "mean_logprob": mean_lp,
        "min_logprob": min_lp,
        "token_logprobs": compact,
        "error": None,
        "from_cache": False,
    }


def call_with_retries(client, model, messages, args, parsed_answer_hint=""):
    want_lp = True
    logprobs_supported = True
    last_exc = None
    attempted_without_lp = False
    max_retries = max(1, args.max_retries)
    attempt = 0
    while attempt < max_retries:
        try:
            resp, latency = call_chat(
                client,
                model,
                messages,
                args.max_tokens,
                args.temperature,
                want_lp,
                args.timeout,
            )
            # parsed_answer is filled after parse; we recompute logprob span later
            packed = pack_response(resp, latency, logprobs_supported and want_lp, parsed_answer_hint)
            return packed
        except Exception as exc:
            last_exc = exc
            if want_lp and is_logprobs_error(exc) and not attempted_without_lp:
                want_lp = False
                logprobs_supported = False
                attempted_without_lp = True
                # retry immediately without consuming a backoff slot
                continue
            if is_retryable(exc) and attempt < max_retries - 1:
                delay = min(30.0, (2 ** attempt) + 0.25 * attempt)
                sys.stderr.write(
                    f"[retry] {type(exc).__name__}: {sanitize(exc)}  sleep={delay:.1f}s\n"
                )
                time.sleep(delay)
                attempt += 1
                continue
            break
    msg = sanitize(last_exc) if last_exc is not None else "unknown error"
    return {
        "content": "",
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "latency": 0.0,
        "logprobs_supported": False if attempted_without_lp else None,
        "mean_logprob": None,
        "min_logprob": None,
        "token_logprobs": [],
        "error": f"{type(last_exc).__name__ if last_exc else 'Error'}: {msg}",
        "from_cache": False,
    }


# ---------------------------------------------------------------------------
# Cache (jsonl, key = model, _id, branch)
# ---------------------------------------------------------------------------
CACHE_FIELDS = (
    "model",
    "_id",
    "branch",
    "k",
    "m",
    "content",
    "prompt_tokens",
    "completion_tokens",
    "latency",
    "logprobs_supported",
    "mean_logprob",
    "min_logprob",
    "token_logprobs",
    "error",
)


def cache_key(model, qid, branch):
    return (str(model), str(qid), str(branch))


def load_cache(path, model, k, m):
    table = {}
    skipped = 0
    if not path or not os.path.isfile(path):
        return table
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("model") != model:
                continue
            # If k/m were recorded and disagree, skip (prompt would differ)
            if rec.get("k") is not None and int(rec["k"]) != int(k):
                skipped += 1
                continue
            if rec.get("m") is not None and int(rec["m"]) != int(m):
                skipped += 1
                continue
            table[cache_key(rec["model"], rec["_id"], rec["branch"])] = rec
    if skipped:
        sys.stderr.write(
            f"[cache] skipped {skipped} entries whose k/m do not match current settings\n"
        )
    return table


def append_cache(path, rec):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({k: rec.get(k) for k in CACHE_FIELDS}, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Summary / printing
# ---------------------------------------------------------------------------
def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def classify_delta(delta, eps):
    if delta > eps:
        return "improved"
    if delta < -eps:
        return "degraded"
    return "tie"


def print_table(summary, price_in, price_out):
    s = summary
    print()
    print(
        f"model={s['model']}  data={s['data']}  n={s['n']}  k={s['k']}  m={s['m']}"
    )
    print("-" * 72)
    print(f"{'':22} {'A (round1)':>14} {'B (round1+2)':>14} {'Oracle':>14}")
    print(f"{'mean EM':22} {s['mean_EM_A']:14.3f} {s['mean_EM_B']:14.3f} {'-':>14}")
    print(f"{'mean F1':22} {s['mean_F1_A']:14.3f} {s['mean_F1_B']:14.3f} {s['oracle_F1']:14.3f}")
    print(
        f"improved / tie / degraded (eps={s['tie_eps']}): "
        f"{s['n_improved']} / {s['n_tie']} / {s['n_degraded']}"
    )
    print(f"mean prompt tokens / call:     {s['mean_prompt_tokens_per_call']:.1f}")
    print(f"mean completion tokens / call: {s['mean_completion_tokens_per_call']:.1f}")
    print(f"total prompt tokens:           {s['total_prompt_tokens']}")
    print(f"total completion tokens:       {s['total_completion_tokens']}")
    print(f"total tokens:                  {s['total_tokens']}")
    print(f"mean latency / call (s):       {s['mean_latency']:.3f}")
    print(f"logprobs_supported:            {s['logprobs_supported']}")
    print(f"cache hits / new API calls:    {s['cache_hits']} / {s['api_calls']}")
    if s.get("n_errors"):
        print(f"API / parse errors:            {s['n_errors']} API, {s['n_parse_fallback']} parse-fallback")
    if price_in is not None and price_out is not None:
        cost = (s["total_prompt_tokens"] * price_in + s["total_completion_tokens"] * price_out) / 1_000_000.0
        n = max(s["n"], 1)
        cost_1600 = cost / n * 1600.0
        print(f"estimated cost ({s['n']} q x 2 branches): ${cost:.4f}")
        print(f"extrapolated (1600 q x 2 branches):  ${cost_1600:.4f}")
        print("(prices are USD per 1M tokens you supplied; check the vendor page for current rates)")
    else:
        print("cost: not estimated (pass --price-in and --price-out, USD per 1M tokens)")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def default_out_name(preset, model):
    if preset and preset != "custom":
        return f"step3_{preset}"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", model or "custom").strip("_")
    return f"step3_{safe or 'custom'}"


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="Step 3: compare answer LLMs on paired HotpotQA A/B branches.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--data", required=True, help="Official-format HotpotQA JSON (e.g. pilot.json)")
    ap.add_argument("--preset", choices=("deepseek", "openai", "custom"), default="custom")
    ap.add_argument("--base-url", default=None, help="Override / required for --preset custom")
    ap.add_argument("--model", default=None, help="Override model name / required for custom")
    ap.add_argument("--key-env", default=None, help="Name of the env var that holds the API key")
    ap.add_argument("--n", type=int, default=30, help="Use the first N questions of the file")
    ap.add_argument("--k", type=int, default=2, help="Round-1 BM25 top-k (default 2)")
    ap.add_argument("--m", type=int, default=1, help="Round-2 paragraphs to add (default 1)")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int, default=128)
    ap.add_argument("--timeout", type=float, default=60.0, help="Per-request timeout in seconds")
    ap.add_argument("--max-retries", type=int, default=5)
    ap.add_argument("--sleep", type=float, default=0.0, help="Optional pause between new API calls")
    ap.add_argument("--tie-eps", type=float, default=0.0, help="Tie tolerance on F1_B - F1_A")
    ap.add_argument("--out", default=None, help="Output directory")
    ap.add_argument("--cache", default=None, help="Cache jsonl path (default: <out>/cache.jsonl)")
    ap.add_argument("--price-in", type=float, default=None, help="USD per 1M prompt tokens")
    ap.add_argument("--price-out", type=float, default=None, help="USD per 1M completion tokens")
    ap.add_argument("--no-cache", action="store_true", help="Do not read or write the cache")
    return ap.parse_args(argv)


def evaluate_branch(ex, indices, packed):
    parsed = parse_response(packed.get("content") or "")
    # Recompute answer-span logprobs now that we have the parsed answer
    mean_lp, min_lp, _ = summarize_logprobs(packed.get("token_logprobs") or [], parsed["answer"])
    if packed.get("token_logprobs"):
        packed["mean_logprob"] = None if mean_lp is None else round(float(mean_lp), 6)
        packed["min_logprob"] = None if min_lp is None else round(float(min_lp), 6)
    cites, cite_titles = map_citations(parsed["citations"], indices, ex)
    gold = ex.get("answer") or ""
    pred = parsed["answer"]
    f1, prec, rec = f1_score(pred, gold)
    em = 1.0 if exact_match_score(pred, gold) else 0.0
    titles = [ex["context"][i][0] for i in indices]
    return {
        "raw": packed.get("content") or "",
        "answer": pred,
        "parse_ok": parsed["parse_ok"],
        "citations": cites,
        "citation_titles": cite_titles,
        "paragraph_titles": titles,
        "paragraph_indices": list(indices),
        "F1": f1,
        "precision": prec,
        "recall": rec,
        "EM": em,
        "prompt_tokens": packed.get("prompt_tokens") or 0,
        "completion_tokens": packed.get("completion_tokens") or 0,
        "latency": packed.get("latency") or 0.0,
        "logprobs_supported": packed.get("logprobs_supported"),
        "mean_logprob": packed.get("mean_logprob"),
        "min_logprob": packed.get("min_logprob"),
        "error": packed.get("error"),
        "from_cache": packed.get("from_cache", False),
    }


def run_one_branch(client, model, ex, branch, indices, args, cache, cache_path):
    key = cache_key(model, ex["_id"], branch)
    if cache is not None and key in cache:
        rec = cache[key]
        packed = {
            "content": rec.get("content") or "",
            "prompt_tokens": rec.get("prompt_tokens") or 0,
            "completion_tokens": rec.get("completion_tokens") or 0,
            "latency": rec.get("latency") or 0.0,
            "logprobs_supported": rec.get("logprobs_supported"),
            "mean_logprob": rec.get("mean_logprob"),
            "min_logprob": rec.get("min_logprob"),
            "token_logprobs": rec.get("token_logprobs") or [],
            "error": rec.get("error"),
            "from_cache": True,
        }
        return evaluate_branch(ex, indices, packed), False

    messages = build_messages(ex, indices)
    packed = call_with_retries(client, model, messages, args)
    result = evaluate_branch(ex, indices, packed)
    if cache is not None and cache_path:
        rec = {
            "model": model,
            "_id": ex["_id"],
            "branch": branch,
            "k": args.k,
            "m": args.m,
            "content": packed.get("content") or "",
            "prompt_tokens": packed.get("prompt_tokens") or 0,
            "completion_tokens": packed.get("completion_tokens") or 0,
            "latency": packed.get("latency") or 0.0,
            "logprobs_supported": packed.get("logprobs_supported"),
            "mean_logprob": result["mean_logprob"],
            "min_logprob": result["min_logprob"],
            "token_logprobs": packed.get("token_logprobs") or [],
            "error": packed.get("error"),
        }
        append_cache(cache_path, rec)
        cache[key] = rec
    if args.sleep > 0 and not packed.get("from_cache"):
        time.sleep(args.sleep)
    return result, True


def main(argv=None):
    args = parse_args(argv)
    if args.n <= 0:
        die("--n must be positive")
    if args.k < 1:
        die("--k must be >= 1")
    if args.m < 0:
        die("--m must be >= 0")

    base_url, model, key_env, allow_missing = resolve_endpoint(args)
    out_dir = args.out or default_out_name(args.preset, model)
    os.makedirs(out_dir, exist_ok=True)
    cache_path = None if args.no_cache else (args.cache or os.path.join(out_dir, "cache.jsonl"))

    data_path = args.data
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        die("Expected a JSON list of HotpotQA examples")
    data = data[: args.n]

    print(f"bm25 helpers: {_BM25_SRC or 'built-in copy of bm25_topk.py tok/para_text'}")
    print(f"data={data_path}  n={len(data)}  k={args.k}  m={args.m}")
    print(f"preset={args.preset}  model={model}  base_url={base_url or '(OpenAI default)'}")
    print(f"key: {env_flag(key_env)}  out={out_dir}", flush=True)

    client = make_client(base_url, key_env, allow_missing)
    cache = {} if args.no_cache else load_cache(cache_path, model, args.k, args.m)
    if cache:
        print(f"cache loaded: {len(cache)} entries from {cache_path}")

    rows = []
    branch_records = []
    api_calls = 0
    cache_hits = 0

    for idx, ex in enumerate(data, start=1):
        r1, r2 = retrieve_indices(ex, args.k, args.m)
        idx_a = list(r1)
        idx_b = list(r1) + list(r2)
        res_a, new_a = run_one_branch(client, model, ex, "A", idx_a, args, cache, cache_path)
        res_b, new_b = run_one_branch(client, model, ex, "B", idx_b, args, cache, cache_path)
        api_calls += int(new_a) + int(new_b)
        cache_hits += int(res_a["from_cache"]) + int(res_b["from_cache"])
        delta = res_b["F1"] - res_a["F1"]
        gold_titles = sorted({t for t, _ in ex.get("supporting_facts") or []})
        row = {
            "_id": ex["_id"],
            "question": ex.get("question", ""),
            "gold_answer": ex.get("answer", ""),
            "answer_A": res_a["answer"],
            "answer_B": res_b["answer"],
            "F1_A": res_a["F1"],
            "F1_B": res_b["F1"],
            "delta": delta,
            "EM_A": res_a["EM"],
            "EM_B": res_b["EM"],
            "prompt_tokens_A": res_a["prompt_tokens"],
            "completion_tokens_A": res_a["completion_tokens"],
            "prompt_tokens_B": res_b["prompt_tokens"],
            "completion_tokens_B": res_b["completion_tokens"],
            "total_tokens": (
                res_a["prompt_tokens"] + res_a["completion_tokens"]
                + res_b["prompt_tokens"] + res_b["completion_tokens"]
            ),
            "latency_A": res_a["latency"],
            "latency_B": res_b["latency"],
            "mean_logprob_A": res_a["mean_logprob"],
            "min_logprob_A": res_a["min_logprob"],
            "mean_logprob_B": res_b["mean_logprob"],
            "min_logprob_B": res_b["min_logprob"],
            "logprobs_supported_A": res_a["logprobs_supported"],
            "logprobs_supported_B": res_b["logprobs_supported"],
            "citations_A": " | ".join(res_a["citation_titles"]),
            "citations_B": " | ".join(res_b["citation_titles"]),
            "r1_titles": " | ".join(res_a["paragraph_titles"]),
            "r2_titles": " | ".join(
                ex["context"][i][0] for i in r2
            ),
            "parse_ok_A": res_a["parse_ok"],
            "parse_ok_B": res_b["parse_ok"],
            "error_A": res_a["error"] or "",
            "error_B": res_b["error"] or "",
            "delta_class": classify_delta(delta, args.tie_eps),
        }
        rows.append(row)
        rec = {
            "_id": ex["_id"],
            "question": ex.get("question", ""),
            "gold_answer": ex.get("answer", ""),
            "type": ex.get("type"),
            "level": ex.get("level"),
            "gold_titles": gold_titles,
            "r1_indices": list(r1),
            "r2_indices": list(r2),
            "A": res_a,
            "B": res_b,
            "delta": delta,
            "delta_class": row["delta_class"],
            "oracle_F1": max(res_a["F1"], res_b["F1"]),
        }
        branch_records.append(rec)
        # drop bulky token_logprobs from the printed record's memory? keep in branches? 
        # Keep mean/min in branches; omit raw token list to keep the file smaller.
        for side in ("A", "B"):
            rec[side] = {k: v for k, v in rec[side].items()}
        print(
            f"[{idx}/{len(data)}] {ex['_id']}  "
            f"F1_A={res_a['F1']:.3f} F1_B={res_b['F1']:.3f} d={delta:+.3f}  "
            f"{'cache' if res_a['from_cache'] and res_b['from_cache'] else 'api'}"
        )

    # write outputs
    csv_path = os.path.join(out_dir, "per_question.csv")
    fieldnames = list(rows[0].keys()) if rows else ["_id"]
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    branches_path = os.path.join(out_dir, "branches.jsonl")
    with open(branches_path, "w", encoding="utf-8") as f:
        for rec in branch_records:
            # do not dump huge token lists into branches.jsonl; they live in the cache
            slim = json.loads(json.dumps(rec, ensure_ascii=False, default=str))
            f.write(json.dumps(slim, ensure_ascii=False) + "\n")

    n = len(rows)
    def col(name):
        return [r[name] for r in rows]

    lp_flags = [
        r["logprobs_supported_A"] for r in rows if r["logprobs_supported_A"] is not None
    ] + [
        r["logprobs_supported_B"] for r in rows if r["logprobs_supported_B"] is not None
    ]
    if not lp_flags:
        lp_supported = None
    elif all(lp_flags):
        lp_supported = True
    elif not any(lp_flags):
        lp_supported = False
    else:
        lp_supported = "mixed"

    prompt_tokens = sum(r["prompt_tokens_A"] + r["prompt_tokens_B"] for r in rows)
    completion_tokens = sum(r["completion_tokens_A"] + r["completion_tokens_B"] for r in rows)
    n_calls = 2 * n if n else 0
    latencies = [r["latency_A"] for r in rows] + [r["latency_B"] for r in rows]
    n_improved = sum(1 for r in rows if r["delta_class"] == "improved")
    n_tie = sum(1 for r in rows if r["delta_class"] == "tie")
    n_degraded = sum(1 for r in rows if r["delta_class"] == "degraded")
    n_errors = sum(1 for r in rows if r["error_A"] or r["error_B"])
    n_parse_fallback = sum(1 for r in rows if (not r["parse_ok_A"]) or (not r["parse_ok_B"]))

    oracle_f1 = mean([max(r["F1_A"], r["F1_B"]) for r in rows]) if rows else float("nan")
    summary = {
        "data": os.path.abspath(data_path),
        "n": n,
        "k": args.k,
        "m": args.m,
        "preset": args.preset,
        "model": model,
        "base_url": base_url,
        "key_env": key_env,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "tie_eps": args.tie_eps,
        "mean_EM_A": mean(col("EM_A")) if rows else float("nan"),
        "mean_EM_B": mean(col("EM_B")) if rows else float("nan"),
        "mean_F1_A": mean(col("F1_A")) if rows else float("nan"),
        "mean_F1_B": mean(col("F1_B")) if rows else float("nan"),
        "oracle_F1": oracle_f1,
        "n_improved": n_improved,
        "n_tie": n_tie,
        "n_degraded": n_degraded,
        "mean_prompt_tokens_per_call": (prompt_tokens / n_calls) if n_calls else 0.0,
        "mean_completion_tokens_per_call": (completion_tokens / n_calls) if n_calls else 0.0,
        "total_prompt_tokens": prompt_tokens,
        "total_completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "mean_latency": mean(latencies) if latencies else float("nan"),
        "logprobs_supported": lp_supported,
        "cache_hits": cache_hits,
        "api_calls": api_calls,
        "n_errors": n_errors,
        "n_parse_fallback": n_parse_fallback,
        "bm25_source": _BM25_SRC,
        "out": os.path.abspath(out_dir),
    }
    if args.price_in is not None and args.price_out is not None:
        cost = (prompt_tokens * args.price_in + completion_tokens * args.price_out) / 1_000_000.0
        summary["price_in_per_1m"] = args.price_in
        summary["price_out_per_1m"] = args.price_out
        summary["estimated_cost_this_run"] = cost
        summary["estimated_cost_1600x2"] = (cost / n * 1600.0) if n else None

    summary_path = os.path.join(out_dir, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print_table(summary, args.price_in, args.price_out)
    print(f"wrote {csv_path}")
    print(f"wrote {branches_path}")
    print(f"wrote {summary_path}")
    if cache_path:
        print(f"cache {cache_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

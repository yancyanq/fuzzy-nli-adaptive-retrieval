#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 6a: check that a local vLLM model's token logprobs are non-degenerate.

Scope: first 30 questions of the tune split (or --data with --n / --offset),
branch A only (first-round BM25 top-k, k=2), temperature 0, max_tokens 128,
logprobs=True, top_logprobs=5. Thirty calls.

Why: Step 5b (experiment log 2026-11-15 12:08) showed that deepseek-chat at
temperature 0 reports the chosen-token logprob as 0.0 and almost all
alternatives as the placeholder -9999.0, so logprob signals were unusable.
This check gates whether logprob-based signals may enter the fuzzy gate in
the main experiment.

This step tests DEGENERACY only, not predictive power. No AUC is computed.

Pre-registered PASS criteria (locked before any real run; CLI-overridable,
defaults below). Verdict is PASS only if all four hold; otherwise FAIL,
listing which criteria failed. Thresholds marked subjective are judgment
calls, not derived from a statistical test.

  (1) At most 50% of answer-span chosen tokens have logprob exactly 0.0.
      Rationale: greedy decoding on a confident token can legitimately yield
      a value that rounds to 0 (e.g. -1e-6). If most tokens are exactly 0.0,
      the API is clamping, as DeepSeek did. The 50% cutoff is subjective and
      pre-registered.
  (2) Placeholder alternatives (logprob <= -9000) are under 5% of all
      reported alternatives. Rationale: Step 5b found -9999.0 used as "not
      reported". The cutoff -9000 and the 5% rate are subjective and
      pre-registered.
  (3) The per-question mean chosen-token logprob (answer span; fallback: all
      output tokens) takes at least 10 distinct values across the 30
      questions and has nonzero variance. The number 10 is subjective and
      pre-registered (one-third of 30; ties across questions are allowed).
  (4) The same requirement on per-question mean margin (top-1 minus top-2
      alternative logprob, same span rule as Step 5b).

If any scheduled question has no usable tokens (failed call or empty
logprobs), the run is incomplete and the verdict is FAIL: the check cannot
certify non-degeneracy.

Default endpoint: model Qwen/Qwen2.5-7B-Instruct, base_url
http://localhost:8000/v1, key from VLLM_API_KEY or the placeholder EMPTY.

Windows (G:\\NLP_project; key only via env var, never on the command line):

  python check_logprobs.py --data tune.json --out step6a_check

Re-analyse from the cache only (no API calls):

  python check_logprobs.py --data tune.json --out step6a_check --analyze-only
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import os
import statistics
import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _import_module(name, rel_dirs):
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [os.path.join(os.getcwd(), f"{name}.py"), os.path.join(here, f"{name}.py")]
    candidates += [os.path.join(here, d, f"{name}.py") for d in rel_dirs]
    candidates += [f"/workspace/exp/{d.strip('./')}/{name}.py" for d in rel_dirs]
    seen = set()
    for path in candidates:
        path = os.path.abspath(path)
        if path in seen or not os.path.isfile(path):
            continue
        seen.add(path)
        directory = os.path.dirname(path)
        if directory not in sys.path:
            sys.path.insert(0, directory)
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod, path
    sys.stderr.write(
        f"Cannot find {name}.py. Copy it next to this script "
        f"(for example G:\\NLP_project\\{name}.py).\n"
    )
    raise SystemExit(2)


cm, COMPARE_MODELS_SRC = _import_module("compare_models", ["../step3"])
rt, RERUN_TOPLP_SRC = _import_module("rerun_toplogprobs", ["../step5b"])

CACHE_NAME = "cache_logprob_check.jsonl"
DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct"
DEFAULT_BASE_URL = "http://localhost:8000/v1"
DEFAULT_KEY_ENV = "VLLM_API_KEY"
LP_DIGITS = 6

# Pre-registered defaults (do not change after seeing a real run).
DEFAULT_MAX_ZERO_CHOSEN_FRAC = 0.50
DEFAULT_MAX_PLACEHOLDER_ALT_FRAC = 0.05
DEFAULT_PLACEHOLDER_THRESHOLD = -9000.0
DEFAULT_MIN_DISTINCT = 10

PURPOSE_NOTE = (
    "This check tests degeneracy only, not predictive power. No AUC is computed. "
    "A PASS means logprob-based signals may be considered for the fuzzy gate on "
    "this endpoint and these settings; a FAIL means they must not enter the gate "
    "until the endpoint reports non-degenerate logprobs. Criteria were "
    "pre-registered before any real local-model run."
)


def die(msg, code=2):
    sys.stderr.write(msg.rstrip() + "\n")
    raise SystemExit(code)


# ---------------------------------------------------------------------------
# Data path, cache
# ---------------------------------------------------------------------------
def resolve_data_path(explicit):
    if explicit:
        if not os.path.isfile(explicit):
            die(f"Data file not found: {explicit}")
        return os.path.abspath(explicit)
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(os.getcwd(), "tune.json"),
        os.path.join(here, "tune.json"),
        os.path.join(here, "..", "tune.json"),
        os.path.join("G:\\NLP_project", "tune.json"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return os.path.abspath(path)
    die(
        "No --data given and tune.json was not found in the current directory "
        "or next to this script. Pass --data path/to/tune.json (official "
        "HotpotQA JSON, same format as pilot.json) and optionally --n 30 --offset 0."
    )


def assert_cache_isolated(cache_path):
    if not cache_path:
        return
    if os.path.basename(cache_path) == "cache.jsonl":
        die(
            f"Refusing to use {cache_path}: the cache must not be named cache.jsonl "
            f"(that name is used by Steps 3 and 5). Use a separate file such as "
            f"<out>/{CACHE_NAME}."
        )


def cache_key(model, qid, branch, top_n):
    return (str(model), str(qid), str(branch), int(top_n))


def load_check_cache(path, model, args):
    """Last successful record per key wins; records with errors are retried."""
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
                continue  # half-written last line after a crash
            if rec.get("model") != model or rec.get("error"):
                continue
            same = (
                int(rec.get("k", -1)) == args.k
                and float(rec.get("temperature", -1)) == float(args.temperature)
                and int(rec.get("max_tokens", -1)) == args.max_tokens
            )
            if not same:
                skipped += 1
                continue
            table[cache_key(model, rec["_id"], rec.get("branch", "A"), rec.get("top_logprobs", -1))] = rec
    if skipped:
        sys.stderr.write(
            f"[cache] skipped {skipped} entries whose k/temperature/max_tokens differ\n"
        )
    return table


def append_check_cache(path, rec):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
        f.flush()


# ---------------------------------------------------------------------------
# Token / question statistics
# ---------------------------------------------------------------------------
def is_placeholder(lp, threshold):
    if lp is None:
        return False
    return float(lp) <= float(threshold)


def token_row(qid, q_index, tok_index, rec, in_span, fallback, placeholder_threshold):
    alts = rt.sorted_alternatives(rec.get("top"))
    top1_t = top1_lp = top2_t = top2_lp = None
    if alts:
        top1_t, top1_lp = alts[0]
    if len(alts) >= 2:
        top2_t, top2_lp = alts[1]
    chosen_lp = rec.get("lp")
    chosen_t = rec.get("t", "") or ""
    n_ph = sum(1 for _, lp in alts if is_placeholder(lp, placeholder_threshold))
    eq_lp = (
        chosen_lp is not None
        and top1_lp is not None
        and float(chosen_lp) == float(top1_lp)
    )
    eq_tok = top1_t is not None and chosen_t == top1_t
    return {
        "_id": qid,
        "question_index": q_index,
        "token_index": tok_index,
        "token": chosen_t,
        "chosen_logprob": None if chosen_lp is None else round(float(chosen_lp), LP_DIGITS),
        "in_answer_span": bool(in_span),
        "span_fallback": bool(fallback),
        "top1_token": top1_t if top1_t is not None else "",
        "top1_logprob": None if top1_lp is None else round(float(top1_lp), LP_DIGITS),
        "top2_token": top2_t if top2_t is not None else "",
        "top2_logprob": None if top2_lp is None else round(float(top2_lp), LP_DIGITS),
        "margin": None if top1_lp is None or top2_lp is None else round(float(top1_lp) - float(top2_lp), LP_DIGITS),
        "n_alternatives": len(alts),
        "n_placeholder_alternatives": n_ph,
        "chosen_lp_equals_top1_lp": bool(eq_lp),
        "chosen_token_equals_top1_token": bool(eq_tok),
    }


def question_metrics(token_recs, answer, placeholder_threshold):
    tokens = [r.get("t", "") for r in token_recs]
    idx, fallback = rt.answer_span_indices(tokens, answer)
    span_set = set(idx)
    chosen_span = []
    margins_span = []
    for i in idx:
        lp = token_recs[i].get("lp")
        if lp is not None and not (isinstance(lp, float) and math.isnan(lp)):
            chosen_span.append(float(lp))
        m = rt.token_margin(token_recs[i].get("top"))
        if m is not None:
            margins_span.append(m)
    mean_lp = (sum(chosen_span) / len(chosen_span)) if chosen_span else None
    mean_margin = (sum(margins_span) / len(margins_span)) if margins_span else None
    n_zero_span = sum(1 for x in chosen_span if x == 0.0)
    return {
        "span_indices": idx,
        "span_fallback": bool(fallback) if token_recs else None,
        "n_tokens": len(token_recs),
        "n_span_tokens": len(idx),
        "n_span_chosen_with_lp": len(chosen_span),
        "n_span_chosen_zero": n_zero_span,
        "mean_chosen_logprob": mean_lp,
        "mean_margin": mean_margin,
        "min_chosen_logprob": min(chosen_span) if chosen_span else None,
        "max_chosen_logprob": max(chosen_span) if chosen_span else None,
        "n_margin_ok": len(margins_span),
        "usable": bool(token_recs) and (mean_lp is not None),
    }


def _round_list(xs, digits=LP_DIGITS):
    return [round(float(x), digits) for x in xs]


def describe_distribution(values, digits=LP_DIGITS):
    xs = [float(v) for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not xs:
        return {
            "n": 0, "min": None, "median": None, "max": None,
            "n_distinct": 0, "variance": None, "values": [],
        }
    rounded = _round_list(xs, digits)
    distinct = sorted(set(rounded))
    var = statistics.pvariance(xs) if len(xs) >= 1 else None
    return {
        "n": len(xs),
        "min": min(xs),
        "median": statistics.median(xs),
        "max": max(xs),
        "n_distinct": len(distinct),
        "variance": var,
        "values": rounded,
    }


# ---------------------------------------------------------------------------
# Pre-registered verdict
# ---------------------------------------------------------------------------
def evaluate_criteria(stats, args, n_scheduled, n_usable):
    """Apply the four pre-registered criteria. Returns a structured verdict.

    stats keys used:
      frac_zero_span, frac_placeholder_alts,
      mean_lp_dist, mean_margin_dist
    """
    results = {}
    failed = []

    incomplete = n_usable < n_scheduled or n_scheduled <= 0
    results["0_complete"] = {
        "id": "complete",
        "passed": not incomplete,
        "n_scheduled": n_scheduled,
        "n_usable": n_usable,
        "detail": (
            "All scheduled questions have usable answer-span (or fallback) "
            "chosen-token logprobs."
            if not incomplete
            else (
                f"Incomplete: {n_usable}/{n_scheduled} questions have usable "
                "logprobs, so non-degeneracy cannot be certified."
            )
        ),
    }
    if incomplete:
        failed.append("incomplete")

    obs1 = stats["frac_zero_span"]
    cap1 = float(args.max_zero_chosen_frac)
    p1 = (obs1 is not None) and (obs1 <= cap1) and not incomplete
    results["1_zero_chosen_frac"] = {
        "id": "zero_chosen_frac",
        "passed": bool(p1),
        "observed": obs1,
        "threshold": cap1,
        "rule": "at most this fraction of answer-span chosen tokens have logprob exactly 0.0",
        "subjective_pre_registered": True,
    }
    if not p1:
        failed.append("zero_chosen_frac")

    obs2 = stats["frac_placeholder_alts"]
    cap2 = float(args.max_placeholder_alt_frac)
    p2 = (obs2 is not None) and (obs2 < cap2) and not incomplete
    # "under 5%" is a strict inequality
    results["2_placeholder_alt_frac"] = {
        "id": "placeholder_alt_frac",
        "passed": bool(p2),
        "observed": obs2,
        "threshold": cap2,
        "placeholder_cutoff": float(args.placeholder_threshold),
        "rule": "fraction of reported alternatives with logprob <= cutoff is under the threshold",
        "subjective_pre_registered": True,
    }
    if not p2:
        failed.append("placeholder_alt_frac")

    dlp = stats["mean_lp_dist"]
    need = int(args.min_distinct_values)
    var_lp = dlp.get("variance")
    p3 = (
        not incomplete
        and dlp.get("n", 0) > 0
        and int(dlp.get("n_distinct") or 0) >= need
        and var_lp is not None
        and var_lp > 0
    )
    results["3_mean_chosen_logprob_spread"] = {
        "id": "mean_chosen_logprob_spread",
        "passed": bool(p3),
        "n": dlp.get("n"),
        "n_distinct": dlp.get("n_distinct"),
        "min_distinct_required": need,
        "variance": var_lp,
        "min": dlp.get("min"),
        "median": dlp.get("median"),
        "max": dlp.get("max"),
        "rule": "per-question mean chosen-token logprob has >= min_distinct values and nonzero variance",
        "subjective_pre_registered": True,
    }
    if not p3:
        failed.append("mean_chosen_logprob_spread")

    dm = stats["mean_margin_dist"]
    var_m = dm.get("variance")
    p4 = (
        not incomplete
        and dm.get("n", 0) > 0
        and int(dm.get("n_distinct") or 0) >= need
        and var_m is not None
        and var_m > 0
    )
    results["4_mean_margin_spread"] = {
        "id": "mean_margin_spread",
        "passed": bool(p4),
        "n": dm.get("n"),
        "n_distinct": dm.get("n_distinct"),
        "min_distinct_required": need,
        "variance": var_m,
        "min": dm.get("min"),
        "median": dm.get("median"),
        "max": dm.get("max"),
        "rule": "per-question mean margin has >= min_distinct values and nonzero variance",
        "subjective_pre_registered": True,
    }
    if not p4:
        failed.append("mean_margin_spread")

    # Unique, stable order
    order = ["incomplete", "zero_chosen_frac", "placeholder_alt_frac",
             "mean_chosen_logprob_spread", "mean_margin_spread"]
    failed_u = [x for x in order if x in failed]
    verdict = "PASS" if not failed_u else "FAIL"
    return verdict, failed_u, results


def print_criteria_banner(args):
    print("Pre-registered PASS criteria (defaults locked before any real run; CLI-overridable):")
    print(
        f"  (1) answer-span chosen-token logprob is exactly 0.0 for at most "
        f"{args.max_zero_chosen_frac:.0%} of those tokens "
        f"(subjective, pre-registered)."
    )
    print(
        f"  (2) alternatives with logprob <= {args.placeholder_threshold:g} are "
        f"under {args.max_placeholder_alt_frac:.0%} of all reported alternatives "
        f"(subjective, pre-registered)."
    )
    print(
        f"  (3) per-question mean chosen-token logprob has at least "
        f"{args.min_distinct_values} distinct values and nonzero variance "
        f"(subjective, pre-registered)."
    )
    print(
        f"  (4) per-question mean margin has at least "
        f"{args.min_distinct_values} distinct values and nonzero variance "
        f"(subjective, pre-registered)."
    )
    print("This check tests degeneracy only, not predictive power. No AUC is computed.")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="Step 6a: check that a local vLLM model's token logprobs are non-degenerate.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument(
        "--data",
        default=None,
        help="Official-format HotpotQA JSON (tune.json). If omitted, look for tune.json in the current directory.",
    )
    ap.add_argument("--n", type=int, default=30, help="Number of questions (default 30)")
    ap.add_argument("--offset", type=int, default=0, help="Skip this many leading questions (default 0 = first N)")
    ap.add_argument("--k", type=int, default=2, help="Round-1 BM25 top-k (default 2); branch A only")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"OpenAI-compatible base URL (default {DEFAULT_BASE_URL})")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"Served model name (default {DEFAULT_MODEL})")
    ap.add_argument(
        "--key-env",
        default=DEFAULT_KEY_ENV,
        help=f"Env var holding the API key (default {DEFAULT_KEY_ENV}; optional, defaults to EMPTY)",
    )
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int, default=128)
    ap.add_argument("--top-logprobs", type=int, default=5)
    ap.add_argument("--timeout", type=float, default=120.0, help="Per-request timeout in seconds (default 120)")
    ap.add_argument("--max-retries", type=int, default=5)
    ap.add_argument("--sleep", type=float, default=0.0, help="Optional pause between new API calls")
    ap.add_argument("--out", default="step6a_check", help="Output directory (default step6a_check)")
    ap.add_argument("--cache", default=None, help=f"Cache jsonl path (default: <out>/{CACHE_NAME})")
    ap.add_argument("--analyze-only", action="store_true", help="Recompute the verdict from the cache; make no API calls")
    ap.add_argument("--skip-api", action="store_true", help="Alias of --analyze-only")
    # Criteria (defaults are the pre-registered values)
    ap.add_argument(
        "--max-zero-chosen-frac",
        type=float,
        default=DEFAULT_MAX_ZERO_CHOSEN_FRAC,
        help="Criterion 1 cap on the fraction of answer-span chosen tokens with logprob exactly 0.0 (default 0.50)",
    )
    ap.add_argument(
        "--max-placeholder-alt-frac",
        type=float,
        default=DEFAULT_MAX_PLACEHOLDER_ALT_FRAC,
        help="Criterion 2 exclusive cap on the fraction of alternatives with logprob <= --placeholder-threshold (default 0.05)",
    )
    ap.add_argument(
        "--placeholder-threshold",
        type=float,
        default=DEFAULT_PLACEHOLDER_THRESHOLD,
        help="Logprob at or below this value is treated as a placeholder (default -9000)",
    )
    ap.add_argument(
        "--min-distinct-values",
        type=int,
        default=DEFAULT_MIN_DISTINCT,
        help="Criteria 3 and 4: minimum distinct per-question means (default 10)",
    )
    return ap.parse_args(argv)


def r6(x):
    if x is None:
        return None
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    return round(float(x), LP_DIGITS)


def json_safe(obj):
    if obj is None or isinstance(obj, (str, int, bool)):
        return obj
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    return str(obj)


def write_csv(path, rows, fields):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in fields})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv=None):
    args = parse_args(argv)
    if args.n <= 0:
        die("--n must be positive")
    if args.offset < 0:
        die("--offset must be >= 0")
    if args.k < 1:
        die("--k must be >= 1")
    if args.top_logprobs < 2:
        die("--top-logprobs must be >= 2 (margin needs a top-2 alternative)")
    if not (0.0 <= args.max_zero_chosen_frac <= 1.0):
        die("--max-zero-chosen-frac must be in [0, 1]")
    if not (0.0 <= args.max_placeholder_alt_frac <= 1.0):
        die("--max-placeholder-alt-frac must be in [0, 1]")
    if args.min_distinct_values < 1:
        die("--min-distinct-values must be >= 1")

    analyze_only = bool(args.analyze_only or args.skip_api)
    data_path = resolve_data_path(args.data)
    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)
    cache_path = args.cache or os.path.join(out_dir, CACHE_NAME)
    assert_cache_isolated(cache_path)

    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        die("Expected a JSON list of HotpotQA examples")
    sliced = data[args.offset : args.offset + args.n]
    if not sliced:
        die(f"No questions in slice offset={args.offset}, n={args.n} of {data_path}")
    if len(sliced) < args.n:
        sys.stderr.write(
            f"[warn] requested n={args.n} from offset={args.offset}, "
            f"but only {len(sliced)} questions are available.\n"
        )

    model = args.model
    base_url = args.base_url
    key_env = args.key_env or DEFAULT_KEY_ENV

    print(f"bm25 helpers: {getattr(cm, '_BM25_SRC', None) or 'compare_models built-in'}")
    print(f"compare_models: {COMPARE_MODELS_SRC}")
    print(f"rerun_toplogprobs: {RERUN_TOPLP_SRC}")
    print(f"data={data_path}  n={len(sliced)}  offset={args.offset}  k={args.k}  branch=A")
    print(f"model={model}  base_url={base_url}")
    print(
        f"key: {cm.env_flag(key_env)}  temperature={args.temperature}  "
        f"max_tokens={args.max_tokens}  top_logprobs={args.top_logprobs}"
    )
    print(f"out={out_dir}  cache={cache_path}  analyze_only={analyze_only}", flush=True)
    print_criteria_banner(args)

    cache = load_check_cache(cache_path, model, args)
    if cache:
        print(f"cache loaded: {len(cache)} successful entries from {cache_path}")

    client = None
    if not analyze_only:
        # Local vLLM typically does not check keys; allow a missing env var.
        client = cm.make_client(base_url, key_env, allow_missing_key=True)

    api_calls = 0
    cache_hits = 0
    n_errors = 0
    missing_not_called = 0
    token_rows = []
    qrows = []

    for qi, ex in enumerate(sliced):
        qid = ex["_id"]
        r1, _r2 = cm.retrieve_indices(ex, args.k, 1)
        indices = list(r1)
        key = cache_key(model, qid, "A", args.top_logprobs)
        rec = cache.get(key)
        from_cache = rec is not None
        if rec is None:
            if analyze_only:
                missing_not_called += 1
                n_errors += 1
                qrows.append({
                    "_id": qid,
                    "question": ex.get("question", ""),
                    "gold_answer": ex.get("answer", ""),
                    "answer": "",
                    "parse_ok": False,
                    "EM": None,
                    "F1": None,
                    "error": "missing_from_cache",
                    "from_cache": False,
                    "usable": False,
                    "n_tokens": 0,
                    "span_fallback": None,
                    "mean_chosen_logprob": None,
                    "mean_margin": None,
                    "n_span_chosen_zero": 0,
                    "n_span_chosen_with_lp": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "latency": 0.0,
                })
                continue
            messages = cm.build_messages(ex, indices)
            packed = rt.call_toplp(client, model, messages, args)
            rec = {
                "model": model,
                "_id": qid,
                "branch": "A",
                "k": args.k,
                "m": 1,
                "temperature": args.temperature,
                "max_tokens": args.max_tokens,
                "top_logprobs": args.top_logprobs,
                "content": packed.get("content") or "",
                "prompt_tokens": packed.get("prompt_tokens") or 0,
                "completion_tokens": packed.get("completion_tokens") or 0,
                "latency": packed.get("latency") or 0.0,
                "tokens": packed.get("tokens") or [],
                "error": packed.get("error"),
            }
            append_check_cache(cache_path, rec)
            cache[key] = rec
            api_calls += 1
            if args.sleep > 0:
                time.sleep(args.sleep)
        else:
            cache_hits += 1

        err = rec.get("error")
        parsed = cm.parse_response(rec.get("content") or "")
        pred = parsed.get("answer") or ""
        gold = ex.get("answer") or ""
        f1, _prec, _rec = cm.f1_score(pred, gold)
        em = 1.0 if cm.exact_match_score(pred, gold) else 0.0
        token_recs = rec.get("tokens") or []
        qmet = question_metrics(token_recs, pred, args.placeholder_threshold)
        if err or not qmet["usable"]:
            n_errors += 1
        span_set = set(qmet["span_indices"])
        for ti, trec in enumerate(token_recs):
            token_rows.append(
                token_row(
                    qid, qi, ti, trec,
                    in_span=(ti in span_set),
                    fallback=qmet["span_fallback"],
                    placeholder_threshold=args.placeholder_threshold,
                )
            )
        qrows.append({
            "_id": qid,
            "question": ex.get("question", ""),
            "gold_answer": gold,
            "answer": pred,
            "parse_ok": bool(parsed.get("parse_ok")),
            "EM": em if not err else None,
            "F1": f1 if not err else None,
            "error": err or "",
            "from_cache": from_cache,
            "usable": bool(qmet["usable"]) and not err,
            "n_tokens": qmet["n_tokens"],
            "n_span_tokens": qmet["n_span_tokens"],
            "span_fallback": qmet["span_fallback"],
            "mean_chosen_logprob": qmet["mean_chosen_logprob"],
            "mean_margin": qmet["mean_margin"],
            "n_span_chosen_zero": qmet["n_span_chosen_zero"],
            "n_span_chosen_with_lp": qmet["n_span_chosen_with_lp"],
            "n_margin_ok": qmet["n_margin_ok"],
            "prompt_tokens": rec.get("prompt_tokens") or 0,
            "completion_tokens": rec.get("completion_tokens") or 0,
            "latency": rec.get("latency") or 0.0,
        })

    # ---- aggregates (no invented fillers; missing values stay None) ----
    n_scheduled = len(sliced)
    usable_rows = [r for r in qrows if r.get("usable")]
    n_usable = len(usable_rows)

    span_rows = [t for t in token_rows if t.get("in_answer_span")]
    n_span = len(span_rows)
    n_zero_span = sum(1 for t in span_rows if t.get("chosen_logprob") == 0.0)
    frac_zero_span = (n_zero_span / n_span) if n_span else None

    all_rows = token_rows
    n_all = len(all_rows)
    n_zero_all = sum(1 for t in all_rows if t.get("chosen_logprob") == 0.0)
    frac_zero_all = (n_zero_all / n_all) if n_all else None

    n_alts = sum(int(t.get("n_alternatives") or 0) for t in all_rows)
    n_ph = sum(int(t.get("n_placeholder_alternatives") or 0) for t in all_rows)
    frac_ph = (n_ph / n_alts) if n_alts else None

    n_eq_lp = sum(1 for t in all_rows if t.get("chosen_lp_equals_top1_lp"))
    n_with_top1 = sum(1 for t in all_rows if t.get("top1_logprob") is not None and t.get("chosen_logprob") is not None)
    frac_eq_lp = (n_eq_lp / n_with_top1) if n_with_top1 else None
    n_eq_tok = sum(1 for t in all_rows if t.get("chosen_token_equals_top1_token"))

    mean_lp_dist = describe_distribution([r["mean_chosen_logprob"] for r in usable_rows])
    mean_margin_dist = describe_distribution([r["mean_margin"] for r in usable_rows if r.get("mean_margin") is not None])

    stats = {
        "frac_zero_span": frac_zero_span,
        "frac_placeholder_alts": frac_ph,
        "mean_lp_dist": mean_lp_dist,
        "mean_margin_dist": mean_margin_dist,
    }
    verdict, failed, crit_results = evaluate_criteria(stats, args, n_scheduled, n_usable)

    scored = [r for r in qrows if r.get("EM") is not None]
    mean_em = (sum(r["EM"] for r in scored) / len(scored)) if scored else None
    mean_f1 = (sum(r["F1"] for r in scored) / len(scored)) if scored else None
    n_parse_ok = sum(1 for r in qrows if r.get("parse_ok"))
    n_fallback = sum(1 for r in usable_rows if r.get("span_fallback"))

    summary = {
        "step": "6a",
        "purpose": PURPOSE_NOTE,
        "model": model,
        "base_url": base_url,
        "key_env": key_env,
        "data": data_path,
        "n_requested": args.n,
        "n_offset": args.offset,
        "n_scheduled": n_scheduled,
        "k": args.k,
        "branch": "A",
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "top_logprobs": args.top_logprobs,
        "analyze_only": analyze_only,
        "criteria_defaults_pre_registered": {
            "max_zero_chosen_frac": DEFAULT_MAX_ZERO_CHOSEN_FRAC,
            "max_placeholder_alt_frac": DEFAULT_MAX_PLACEHOLDER_ALT_FRAC,
            "placeholder_threshold": DEFAULT_PLACEHOLDER_THRESHOLD,
            "min_distinct_values": DEFAULT_MIN_DISTINCT,
            "note": (
                "Thresholds 50%, 5%, -9000, and 10 distinct values are subjective "
                "judgment calls, pre-registered before any real local-model run."
            ),
        },
        "criteria_used": {
            "max_zero_chosen_frac": args.max_zero_chosen_frac,
            "max_placeholder_alt_frac": args.max_placeholder_alt_frac,
            "placeholder_threshold": args.placeholder_threshold,
            "min_distinct_values": args.min_distinct_values,
        },
        "calls": {
            "new_api_calls_this_run": api_calls,
            "cache_hits": cache_hits,
            "errors_or_unusable": n_errors,
            "missing_not_called": missing_not_called,
        },
        "tokens": {
            "n_output_tokens": n_all,
            "n_answer_span_tokens": n_span,
            "n_span_fallback_questions": n_fallback,
            "n_chosen_lp_exactly_zero_all": n_zero_all,
            "frac_chosen_lp_exactly_zero_all": r6(frac_zero_all),
            "n_chosen_lp_exactly_zero_span": n_zero_span,
            "frac_chosen_lp_exactly_zero_span": r6(frac_zero_span),
            "n_alternatives_reported": n_alts,
            "n_placeholder_alternatives": n_ph,
            "frac_placeholder_alternatives": r6(frac_ph),
            "n_tokens_with_top1_and_chosen_lp": n_with_top1,
            "n_chosen_lp_equals_top1_alt_lp": n_eq_lp,
            "frac_chosen_lp_equals_top1_alt_lp": r6(frac_eq_lp),
            "n_chosen_token_equals_top1_alt_token": n_eq_tok,
        },
        "per_question_distributions": {
            "mean_chosen_logprob_span": {
                "n": mean_lp_dist["n"],
                "min": r6(mean_lp_dist["min"]),
                "median": r6(mean_lp_dist["median"]),
                "max": r6(mean_lp_dist["max"]),
                "n_distinct": mean_lp_dist["n_distinct"],
                "variance": mean_lp_dist["variance"],
            },
            "mean_margin_span": {
                "n": mean_margin_dist["n"],
                "min": r6(mean_margin_dist["min"]),
                "median": r6(mean_margin_dist["median"]),
                "max": r6(mean_margin_dist["max"]),
                "n_distinct": mean_margin_dist["n_distinct"],
                "variance": mean_margin_dist["variance"],
            },
        },
        "answer_quality_info_only": {
            "n_scored": len(scored),
            "mean_EM": r6(mean_em),
            "mean_F1": r6(mean_f1),
            "n_parse_ok": n_parse_ok,
            "note": "Informational only; not used in the PASS/FAIL verdict.",
        },
        "n_usable_questions": n_usable,
        "verdict": verdict,
        "failed_criteria": failed,
        "criteria_results": json_safe(crit_results),
        "questions": [
            {
                "_id": r["_id"],
                "usable": r["usable"],
                "error": r.get("error") or "",
                "EM": r6(r.get("EM")),
                "F1": r6(r.get("F1")),
                "span_fallback": r.get("span_fallback"),
                "n_tokens": r.get("n_tokens"),
                "mean_chosen_logprob": r6(r.get("mean_chosen_logprob")),
                "mean_margin": r6(r.get("mean_margin")),
            }
            for r in qrows
        ],
    }

    summary_path = os.path.join(out_dir, "logprob_check.json")
    tokens_path = os.path.join(out_dir, "logprob_check_tokens.csv")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(json_safe(summary), f, ensure_ascii=False, indent=2)
        f.write("\n")
    tok_fields = [
        "_id", "question_index", "token_index", "token", "chosen_logprob",
        "in_answer_span", "span_fallback", "top1_token", "top1_logprob",
        "top2_token", "top2_logprob", "margin", "n_alternatives",
        "n_placeholder_alternatives", "chosen_lp_equals_top1_lp",
        "chosen_token_equals_top1_token",
    ]
    write_csv(tokens_path, token_rows, tok_fields)

    # Terminal summary (no secrets)
    print("------------------------------------------------------------------------")
    print(f"VERDICT: {verdict}")
    if failed:
        print("Failed criteria: " + ", ".join(failed))
    else:
        print("All four pre-registered criteria held.")
    print(f"usable questions: {n_usable}/{n_scheduled}")
    def _fmt(x):
        return "n/a" if x is None else f"{x:.4f}"
    print(f"frac chosen logprob == 0.0 (answer span): {_fmt(frac_zero_span)}  ({n_zero_span}/{n_span})")
    print(f"frac chosen logprob == 0.0 (all tokens):  {_fmt(frac_zero_all)}  ({n_zero_all}/{n_all})")
    print(f"frac placeholder alternatives (<= {args.placeholder_threshold:g}): {_fmt(frac_ph)}  ({n_ph}/{n_alts})")
    print(f"frac chosen logprob == top-1 alternative logprob: {_fmt(frac_eq_lp)}  ({n_eq_lp}/{n_with_top1})")
    print(
        "mean chosen-token logprob (per question): "
        f"min={_fmt(mean_lp_dist['min'])}  median={_fmt(mean_lp_dist['median'])}  "
        f"max={_fmt(mean_lp_dist['max'])}  n_distinct={mean_lp_dist['n_distinct']}  "
        f"var={_fmt(mean_lp_dist['variance'])}"
    )
    print(
        "mean margin (per question): "
        f"min={_fmt(mean_margin_dist['min'])}  median={_fmt(mean_margin_dist['median'])}  "
        f"max={_fmt(mean_margin_dist['max'])}  n_distinct={mean_margin_dist['n_distinct']}  "
        f"var={_fmt(mean_margin_dist['variance'])}"
    )
    print(
        f"answer quality (info only, not in verdict): mean EM={_fmt(mean_em)}  "
        f"mean F1={_fmt(mean_f1)}  parse_ok={n_parse_ok}/{n_scheduled}"
    )
    print(f"calls: new={api_calls}  cache_hits={cache_hits}  errors_or_unusable={n_errors}")
    print(f"wrote {summary_path}")
    print(f"wrote {tokens_path}")
    print(PURPOSE_NOTE)
    return 0


if __name__ == "__main__":
    sys.exit(main())

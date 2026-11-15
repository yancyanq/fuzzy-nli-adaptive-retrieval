#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 5b: re-run the 100-question pilot with top_logprobs and analyse a
margin-based uncertainty signal (pre-registered 2026-11-15 11:51, Option 1).

Why: at temperature 0, deepseek-chat reports logprob 0.0 for every chosen
output token, but its top_logprobs alternatives are non-zero (user probe).
So the chosen-token logprob is unusable; this script uses the gap between the
top-1 and top-2 returned alternatives instead.

Pre-registered definitions (do not change after seeing results):
  margin(token)  = logprob(top-1 alternative) - logprob(top-2 alternative),
                   alternatives sorted by logprob; < 2 alternatives -> missing
  PRIMARY        = mean margin over answer-span tokens of branch A
                   (fallback: all output tokens if the span is not found; counted)
  secondary      = min margin over span, margin of first answer token,
                   mean entropy of the renormalised top-k alternatives
  orientation    = low margin / high entropy -> expected "improved"
  labels         = Step 5 delta_class (improved / tie / degraded), unchanged
  primary subset = questions whose re-run A and B answers both equal the
                   Step 5 answers (HotpotQA normalisation); sensitivity = all
  comparison     = NLI entailment_A AUC on the exact same subsets
AUC improved vs tie, bootstrap 95% CI (B=5000, seed 42), reusing
analyze_signals.auc_score / bootstrap_ci. No gate threshold is selected.
The Step 5 GO verdict is not re-decided.

Windows (G:\\NLP_project; key only via env var, never on the command line):
  set DEEPSEEK_API_KEY=...
  python rerun_toplogprobs.py --data pilot.json --step5-dir step5_pilot --out step5b_toplp

Re-analyse from the cache only (no API calls):
  python rerun_toplogprobs.py --data pilot.json --step5-dir step5_pilot --out step5b_toplp --analyze-only
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import os
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
asig, ANALYZE_SIGNALS_SRC = _import_module("analyze_signals", ["../step5"])

CACHE_NAME = "cache_toplp.jsonl"
BOOT_B = 5000
BOOT_SEED = 42
LP_DIGITS = 6
CLASSES = ("improved", "tie", "degraded")

# (column, orientation for AUC: score = orientation * value, role)
SIGNALS = (
    ("mean_margin_A", -1.0, "PRIMARY"),
    ("min_margin_A", -1.0, "secondary"),
    ("first_margin_A", -1.0, "secondary"),
    ("mean_entropy_A", +1.0, "secondary"),
    ("nli_entailment_A", -1.0, "comparison (Step 5 NLI)"),
)

METHOD_NOTE = (
    "The margin (top-1 minus top-2 alternative logprob) is a workaround for the API "
    "reporting logprob 0.0 for the chosen token at temperature 0. It is NOT the same "
    "quantity as the chosen-token logprob planned for the local vLLM model, and DeepSeek "
    "logprob distributions do not transfer to the main-experiment model. Pilot results are "
    "evidence about the signal type only. No gate threshold is selected here; the gate is "
    "tuned on tune.json. Labels are Step 5 delta_class; the Step 5 GO verdict is not re-decided."
)


def die(msg, code=2):
    sys.stderr.write(msg.rstrip() + "\n")
    raise SystemExit(code)


# ---------------------------------------------------------------------------
# Token-level maths (pure functions; unit-tested)
# ---------------------------------------------------------------------------
def sorted_alternatives(alts):
    """alts: list of [token, logprob] (or dicts). Returns list sorted by logprob desc."""
    out = []
    for a in alts or []:
        if isinstance(a, dict):
            t, lp = a.get("token"), a.get("logprob")
        else:
            t, lp = a[0], a[1]
        if lp is None:
            continue
        lp = float(lp)
        if math.isnan(lp):
            continue
        out.append((t if t is not None else "", lp))
    out.sort(key=lambda x: -x[1])
    return out


def token_margin(alts):
    s = sorted_alternatives(alts)
    if len(s) < 2:
        return None
    return s[0][1] - s[1][1]


def token_entropy(alts):
    """Entropy (nats) of the returned alternatives renormalised to sum to 1."""
    s = sorted_alternatives(alts)
    if len(s) < 2:
        return None
    mx = s[0][1]
    ws = [math.exp(lp - mx) for _, lp in s]
    z = sum(ws)
    h = 0.0
    for w in ws:
        p = w / z
        if p > 0:
            h -= p * math.log(p)
    return h


def answer_span_indices(tokens, answer):
    """Indices of tokens overlapping the parsed answer.

    Same matching rule as compare_models.summarize_logprobs (concatenate token
    strings, map 'Ġ'/'Ċ', exact then case-insensitive find, overlap test).
    Returns (indices, fallback) where fallback=True means all tokens are used.
    """
    n = len(tokens)
    if n == 0:
        return [], True
    if answer:
        needle = answer.strip()
        pieces = [(t or "").replace("Ġ", " ").replace("Ċ", "\n") for t in tokens]
        concat_norm = "".join(pieces)
        start = concat_norm.find(needle) if needle else -1
        if start < 0 and needle:
            start = concat_norm.lower().find(needle.lower())
        if start >= 0:
            end = start + len(needle)
            pos = 0
            span = []
            for i, piece in enumerate(pieces):
                nxt = pos + len(piece)
                if nxt > start and pos < end:
                    span.append(i)
                pos = nxt
            if span:
                return span, False
    return list(range(n)), True


def branch_metrics(token_recs, answer):
    """token_recs: list of {"t": str, "lp": float, "top": [[tok, lp], ...]}."""
    tokens = [r.get("t", "") for r in token_recs]
    idx, fallback = answer_span_indices(tokens, answer)
    margins = [token_margin(token_recs[i].get("top")) for i in idx]
    ents = [token_entropy(token_recs[i].get("top")) for i in idx]
    m_ok = [x for x in margins if x is not None]
    e_ok = [x for x in ents if x is not None]
    chosen_ne_top1 = 0
    top1_zero = 0
    chosen_zero = 0
    for r in token_recs:
        s = sorted_alternatives(r.get("top"))
        if s:
            if s[0][0] != r.get("t", ""):
                chosen_ne_top1 += 1
            if s[0][1] == 0.0:
                top1_zero += 1
        if r.get("lp") == 0.0:
            chosen_zero += 1
    return {
        "n_tokens": len(token_recs),
        "n_span_tokens": len(idx),
        "span_fallback": bool(fallback) if token_recs else None,
        "n_margin_missing": len(margins) - len(m_ok),
        "mean_margin": (sum(m_ok) / len(m_ok)) if m_ok else None,
        "min_margin": min(m_ok) if m_ok else None,
        "first_margin": margins[0] if margins else None,
        "mean_entropy": (sum(e_ok) / len(e_ok)) if e_ok else None,
        "n_chosen_ne_top1": chosen_ne_top1,
        "n_top1_alt_zero": top1_zero,
        "n_chosen_lp_zero": chosen_zero,
    }


# ---------------------------------------------------------------------------
# API call with top_logprobs
# ---------------------------------------------------------------------------
def compact_tokens(resp):
    """Extract per-token {t, lp, top:[[tok, lp], ...]} from an OpenAI-style response."""
    out = []
    try:
        lp_obj = resp.choices[0].logprobs
        content = getattr(lp_obj, "content", None) if lp_obj is not None else None
    except Exception:
        content = None
    for t in content or []:
        lp = getattr(t, "logprob", None)
        top = []
        for a in getattr(t, "top_logprobs", None) or []:
            alp = getattr(a, "logprob", None)
            if alp is None:
                continue
            top.append([getattr(a, "token", "") or "", round(float(alp), LP_DIGITS)])
        out.append({
            "t": getattr(t, "token", "") or "",
            "lp": None if lp is None else round(float(lp), LP_DIGITS),
            "top": top,
        })
    return out


def call_toplp(client, model, messages, args):
    kwargs = {
        "model": model,
        "messages": messages,
        "max_tokens": args.max_tokens,
        "temperature": args.temperature,
        "logprobs": True,
        "top_logprobs": args.top_logprobs,
    }
    if args.timeout is not None:
        kwargs["timeout"] = args.timeout
    last_exc = None
    max_retries = max(1, args.max_retries)
    for attempt in range(max_retries):
        try:
            t0 = time.perf_counter()
            resp = client.chat.completions.create(**kwargs)
            latency = time.perf_counter() - t0
            content = ""
            try:
                content = resp.choices[0].message.content or ""
            except Exception:
                pass
            pt = ct = 0
            try:
                if resp.usage is not None:
                    pt = int(resp.usage.prompt_tokens or 0)
                    ct = int(resp.usage.completion_tokens or 0)
            except Exception:
                pass
            return {
                "content": content, "prompt_tokens": pt, "completion_tokens": ct,
                "latency": round(latency, 4), "tokens": compact_tokens(resp), "error": None,
            }
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if cm.is_logprobs_error(exc):
                die(
                    "The endpoint rejected logprobs/top_logprobs: "
                    f"{type(exc).__name__}: {cm.sanitize(exc)}\n"
                    "Step 5b needs top_logprobs; nothing was cached for this call."
                )
            if cm.is_retryable(exc) and attempt < max_retries - 1:
                delay = min(30.0, (2 ** attempt) + 0.25 * attempt)
                sys.stderr.write(f"[retry] {type(exc).__name__}: {cm.sanitize(exc)}  sleep={delay:.1f}s\n")
                time.sleep(delay)
                continue
            break
    return {
        "content": "", "prompt_tokens": 0, "completion_tokens": 0, "latency": 0.0, "tokens": [],
        "error": f"{type(last_exc).__name__ if last_exc else 'Error'}: {cm.sanitize(last_exc)}",
    }


# ---------------------------------------------------------------------------
# Separate cache: <out>/cache_toplp.jsonl, key (model, _id, branch, top_logprobs)
# ---------------------------------------------------------------------------
def toplp_key(model, qid, branch, top_n):
    return (str(model), str(qid), str(branch), int(top_n))


def load_toplp_cache(path, model, args):
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
                continue  # a half-written last line after a crash
            if rec.get("model") != model or rec.get("error"):
                continue
            same = (
                int(rec.get("k", -1)) == args.k and int(rec.get("m", -1)) == args.m
                and float(rec.get("temperature", -1)) == float(args.temperature)
                and int(rec.get("max_tokens", -1)) == args.max_tokens
            )
            if not same:
                skipped += 1
                continue
            table[toplp_key(model, rec["_id"], rec["branch"], rec.get("top_logprobs", -1))] = rec
    if skipped:
        sys.stderr.write(f"[cache] skipped {skipped} entries whose k/m/temperature/max_tokens differ\n")
    return table


def append_toplp_cache(path, rec):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
        f.flush()


def assert_cache_isolated(cache_path, step5_dir):
    """Refuse to write into any Step 5 cache file."""
    cp = os.path.normcase(os.path.abspath(cache_path))
    forbidden = {
        os.path.normcase(os.path.abspath(os.path.join(step5_dir, "cache.jsonl"))),
    }
    if cp in forbidden or os.path.basename(cp) == "cache.jsonl":
        die(
            f"Refusing to use {cache_path} as the Step 5b cache: Step 5 caches must not be "
            f"modified. Use a separate file such as <out>/{CACHE_NAME}."
        )


# ---------------------------------------------------------------------------
# Step 5 reference and consistency
# ---------------------------------------------------------------------------
def load_step5_rows(step5_dir):
    path = os.path.join(step5_dir, "per_question.csv")
    if not os.path.isfile(path):
        die(f"missing {path} (Step 5 output). Pass --step5-dir.")
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    need = {"_id", "delta_class", "answer_A", "answer_B"}
    if rows:
        missing = [c for c in need if c not in rows[0]]
        if missing:
            die(f"{path} lacks columns {missing}")
    return {r["_id"]: r for r in rows}, path


def answers_equal(a, b):
    return cm.normalize_answer(a or "") == cm.normalize_answer(b or "")


def fmt(x, d=3):
    return asig.fmt(x, d)


def to_float(v):
    return asig.to_float(v)


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
def auc_block(rows, col, orient, n_boot, seed):
    pos = [orient * r[col] for r in rows if r["label"] == "improved" and r.get(col) is not None]
    neg = [orient * r[col] for r in rows if r["label"] == "tie" and r.get(col) is not None]
    auc = asig.auc_score(pos, neg)
    lo, hi = asig.bootstrap_ci(pos, neg, asig.auc_score, n_boot=n_boot, seed=seed)
    raw_mean = lambda lab: (  # noqa: E731
        lambda xs: (sum(xs) / len(xs)) if xs else None
    )([r[col] for r in rows if r["label"] == lab and r.get(col) is not None])
    return {
        "auc_improved_vs_tie": auc,
        "auc_ci95": [lo, hi],
        "n_improved": len(pos),
        "n_tie": len(neg),
        "mean_improved": raw_mean("improved"),
        "mean_tie": raw_mean("tie"),
        "mean_degraded": raw_mean("degraded"),
        "score_used": ("-" if orient < 0 else "+") + col,
    }


def analyze(qrows, n_boot=BOOT_B, seed=BOOT_SEED):
    """qrows: per-question dicts with label, unchanged_both, signals.

    A question enters a subset only if it has a Step 5 label, a primary
    margin value and an NLI value, so every signal is compared on the same
    questions (secondary signals may still drop a question with a missing value;
    their n is reported).
    """
    base = [
        r for r in qrows
        if r.get("label") in CLASSES and r.get("mean_margin_A") is not None
        and r.get("nli_entailment_A") is not None
    ]
    subsets = {
        "primary_unchanged_AB": [r for r in base if r.get("unchanged_both")],
        "sensitivity_all": base,
    }
    out = {}
    for name, rows in subsets.items():
        counts = {c: sum(1 for r in rows if r["label"] == c) for c in CLASSES}
        sig = {}
        for col, orient, role in SIGNALS:
            b = auc_block(rows, col, orient, n_boot, seed)
            b["role"] = role
            sig[col] = b
        out[name] = {"n_questions": len(rows), "n_by_class": counts, "signals": sig}
    excluded = {
        "no_step5_label": sum(1 for r in qrows if r.get("label") not in CLASSES),
        "no_margin_A": sum(1 for r in qrows if r.get("label") in CLASSES and r.get("mean_margin_A") is None),
        "no_nli_A": sum(
            1 for r in qrows
            if r.get("label") in CLASSES and r.get("mean_margin_A") is not None and r.get("nli_entailment_A") is None
        ),
    }
    return out, excluded


def print_analysis(analysis, n_boot=BOOT_B):
    print()
    print("Improved vs tie AUC (labels = Step 5 delta_class; 0.5 = chance; >0.5 = signal points the expected way)")
    print("score: low margin -> improved (score = -margin); high entropy -> improved; low NLI -> improved")
    for name, title in (("primary_unchanged_AB", "PRIMARY subset: A and B answers unchanged vs Step 5"),
                        ("sensitivity_all", "SENSITIVITY: all questions")):
        a = analysis[name]
        c = a["n_by_class"]
        print("-" * 96)
        print(f"{title}   n={a['n_questions']} (improved {c['improved']}, tie {c['tie']}, degraded {c['degraded']} not in AUC)")
        print(f"  {'signal (branch A)':20} {'role':26} {'imp mean':>9} {'tie mean':>9} {'AUC':>7}  95% CI (B={n_boot})   n_imp/n_tie")
        for col, _, role in SIGNALS:
            s = a["signals"][col]
            lo, hi = s["auc_ci95"]
            print(
                f"  {col:20} {role:26} {fmt(s['mean_improved']):>9} {fmt(s['mean_tie']):>9} "
                f"{fmt(s['auc_improved_vs_tie']):>7}  [{fmt(lo)}, {fmt(hi)}]        {s['n_improved']}/{s['n_tie']}"
            )
    print("-" * 96)
    print("Pre-registered PRIMARY result = mean_margin_A on the PRIMARY subset. Everything else is secondary/descriptive.")
    print("No gate threshold is selected. " + "Margin is an API workaround, not the chosen-token logprob.")
    print()


# ---------------------------------------------------------------------------
# CLI / main
# ---------------------------------------------------------------------------
def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="Step 5b: re-run pilot with top_logprobs; margin-signal AUC vs Step 5 labels.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--data", default="pilot.json", help="Official-format HotpotQA JSON (default pilot.json)")
    ap.add_argument("--preset", choices=("deepseek", "openai", "custom"), default="deepseek")
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--key-env", default=None, help="Name of the env var holding the API key")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--k", type=int, default=2)
    ap.add_argument("--m", type=int, default=1)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int, default=128)
    ap.add_argument("--top-logprobs", type=int, default=5, help="Alternatives per token (default 5)")
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--max-retries", type=int, default=5)
    ap.add_argument("--sleep", type=float, default=0.0, help="Pause between new API calls (s)")
    ap.add_argument("--out", default="step5b_toplp")
    ap.add_argument("--step5-dir", default="step5_pilot", help="Folder with Step 5 per_question.csv")
    ap.add_argument("--cache", default=None, help=f"Override cache path (default <out>/{CACHE_NAME})")
    ap.add_argument("--analyze-only", "--skip-api", dest="analyze_only", action="store_true",
                    help="No API calls; analyse whatever is in the cache")
    ap.add_argument("--price-in", type=float, default=None, help="USD per 1M prompt tokens (optional)")
    ap.add_argument("--price-out", type=float, default=None, help="USD per 1M completion tokens (optional)")
    ap.add_argument("--bootstrap-samples", type=int, default=BOOT_B)
    ap.add_argument("--bootstrap-seed", type=int, default=BOOT_SEED)
    return ap.parse_args(argv)


def write_csv(path, rows, fields):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})


def r6(x):
    return None if x is None else round(float(x), 6)


def main(argv=None):
    args = parse_args(argv)
    if args.top_logprobs < 2:
        die("--top-logprobs must be >= 2 (the margin needs two alternatives)")
    base_url, model, key_env, allow_missing = cm.resolve_endpoint(args)
    if not os.path.isfile(args.data):
        die(f"missing --data {args.data}")
    with open(args.data, "r", encoding="utf-8") as f:
        data = json.load(f)
    examples = data[: args.n]
    step5, step5_csv = load_step5_rows(args.step5_dir)
    os.makedirs(args.out, exist_ok=True)
    cache_path = args.cache or os.path.join(args.out, CACHE_NAME)
    assert_cache_isolated(cache_path, args.step5_dir)
    cache = load_toplp_cache(cache_path, model, args)

    print(f"Step 5b  model={model}  n={len(examples)}  k={args.k} m={args.m}  T={args.temperature}  "
          f"max_tokens={args.max_tokens}  top_logprobs={args.top_logprobs}")
    print(f"key: {cm.env_flag(key_env)}   cache: {cache_path} ({len(cache)} usable entries)   "
          f"mode: {'ANALYZE-ONLY (no API calls)' if args.analyze_only else 'API + analysis'}")

    client = None
    api_calls = cache_hits = missing = errors = 0
    qrows, cons_rows = [], []
    for qi, ex in enumerate(examples, start=1):
        r1, r2 = cm.retrieve_indices(ex, args.k, args.m)
        ref = step5.get(ex["_id"])
        row = {"_id": ex["_id"], "label": (ref or {}).get("delta_class", "").strip().lower() or None,
               "nli_entailment_A": to_float((ref or {}).get("nli_entailment_A")),
               "nli_entailment_B": to_float((ref or {}).get("nli_entailment_B"))}
        unchanged = []
        for branch, idx in (("A", list(r1)), ("B", list(r1) + list(r2))):
            key = toplp_key(model, ex["_id"], branch, args.top_logprobs)
            rec = cache.get(key)
            if rec is not None:
                cache_hits += 1
            elif args.analyze_only:
                missing += 1
            else:
                if client is None:
                    client = cm.make_client(base_url, key_env, allow_missing)
                messages = cm.build_messages(ex, idx)
                packed = call_toplp(client, model, messages, args)
                api_calls += 1
                rec = {"model": model, "_id": ex["_id"], "branch": branch, "top_logprobs": args.top_logprobs,
                       "k": args.k, "m": args.m, "temperature": args.temperature,
                       "max_tokens": args.max_tokens, **packed}
                append_toplp_cache(cache_path, rec)
                if packed["error"]:
                    errors += 1
                    sys.stderr.write(f"[error] {ex['_id']} {branch}: {packed['error']}\n")
                    rec = None
                else:
                    cache[key] = rec
                if args.sleep > 0:
                    time.sleep(args.sleep)
            if rec is None:
                row[f"answer_{branch}"] = None
                unchanged.append(False)
                cons_rows.append({"_id": ex["_id"], "branch": branch, "status": "missing",
                                  "step5_answer": (ref or {}).get(f"answer_{branch}")})
                continue
            parsed = cm.parse_response(rec.get("content") or "")
            ans = parsed["answer"]
            gold = ex.get("answer") or ""
            f1 = cm.f1_score(ans, gold)[0]
            em = 1.0 if cm.exact_match_score(ans, gold) else 0.0
            met = branch_metrics(rec.get("tokens") or [], ans)
            row.update({
                f"answer_{branch}": ans, f"F1_new_{branch}": r6(f1), f"EM_new_{branch}": em,
                f"parse_ok_{branch}": parsed["parse_ok"],
                f"prompt_tokens_{branch}": rec.get("prompt_tokens") or 0,
                f"completion_tokens_{branch}": rec.get("completion_tokens") or 0,
                f"n_tokens_{branch}": met["n_tokens"], f"n_span_tokens_{branch}": met["n_span_tokens"],
                f"span_fallback_{branch}": met["span_fallback"],
                f"n_margin_missing_{branch}": met["n_margin_missing"],
                f"mean_margin_{branch}": r6(met["mean_margin"]), f"min_margin_{branch}": r6(met["min_margin"]),
                f"first_margin_{branch}": r6(met["first_margin"]),
                f"mean_entropy_{branch}": r6(met["mean_entropy"]),
                f"n_chosen_ne_top1_{branch}": met["n_chosen_ne_top1"],
                f"n_top1_alt_zero_{branch}": met["n_top1_alt_zero"],
                f"n_chosen_lp_zero_{branch}": met["n_chosen_lp_zero"],
            })
            if ref is None:
                unchanged.append(False)
                cons_rows.append({"_id": ex["_id"], "branch": branch, "status": "no_step5_row",
                                  "new_answer": ans, "new_F1": r6(f1)})
                continue
            old = ref.get(f"answer_{branch}") or ""
            same = answers_equal(ans, old)
            unchanged.append(same)
            old_f1 = to_float(ref.get(f"F1_{branch}"))
            cons_rows.append({
                "_id": ex["_id"], "branch": branch, "status": "unchanged" if same else "CHANGED",
                "step5_answer": old, "new_answer": ans, "step5_F1": old_f1, "new_F1": r6(f1),
                "F1_diff_new_minus_step5": None if old_f1 is None else r6(f1 - old_f1),
                "step5_delta_class": ref.get("delta_class"), "question": ex.get("question"),
                "gold_answer": ex.get("answer"),
            })
        row["unchanged_both"] = bool(ref is not None and all(unchanged))
        if row.get("F1_new_A") is not None and row.get("F1_new_B") is not None:
            row["delta_class_new_descriptive"] = asig_classify(row["F1_new_B"] - row["F1_new_A"])
        qrows.append(row)
        if not args.analyze_only and qi % 10 == 0:
            print(f"  {qi}/{len(examples)} questions  (new calls {api_calls}, cache hits {cache_hits})")

    analysis, excluded = analyze(qrows, args.bootstrap_samples, args.bootstrap_seed)

    def count(branch, pred):
        return sum(1 for r in qrows if r.get(f"answer_{branch}") is not None and pred(r, branch))

    changed = {b: sum(1 for c in cons_rows if c["branch"] == b and c["status"] == "CHANGED") for b in "AB"}
    pt = sum((r.get("prompt_tokens_A") or 0) + (r.get("prompt_tokens_B") or 0) for r in qrows)
    ct = sum((r.get("completion_tokens_A") or 0) + (r.get("completion_tokens_B") or 0) for r in qrows)
    tok_tot = {b: sum(r.get(f"n_tokens_{b}") or 0 for r in qrows) for b in "AB"}
    summary = {
        "step": "5b",
        "model": model, "base_url": base_url, "key_env": key_env,
        "data": os.path.abspath(args.data), "step5_per_question_csv": os.path.abspath(step5_csv),
        "n_questions": len(examples), "k": args.k, "m": args.m, "temperature": args.temperature,
        "max_tokens": args.max_tokens, "top_logprobs": args.top_logprobs,
        "analyze_only": args.analyze_only,
        "calls": {"new_api_calls_this_run": api_calls, "cache_hits": cache_hits,
                  "missing_not_called": missing, "errors_this_run": errors,
                  "cache_path": os.path.abspath(cache_path)},
        "tokens_in_analysed_records": {"prompt": pt, "completion": ct, "total": pt + ct,
                                       "output_tokens_with_logprobs_A": tok_tot["A"],
                                       "output_tokens_with_logprobs_B": tok_tot["B"]},
        "consistency_vs_step5": {
            "changed_answers_A": changed["A"], "changed_answers_B": changed["B"],
            "questions_both_unchanged": sum(1 for r in qrows if r["unchanged_both"]),
            "changed_ids_A": [c["_id"] for c in cons_rows if c["branch"] == "A" and c["status"] == "CHANGED"],
            "changed_ids_B": [c["_id"] for c in cons_rows if c["branch"] == "B" and c["status"] == "CHANGED"],
            "rule": "HotpotQA-normalised string equality (compare_models.normalize_answer)",
        },
        "span_fallback_to_all_tokens": {b: count(b, lambda r, b: r.get(f"span_fallback_{b}")) for b in "AB"},
        "margin_missing_span_tokens": {b: sum(r.get(f"n_margin_missing_{b}") or 0 for r in qrows) for b in "AB"},
        "chosen_ne_top1_tokens": {b: sum(r.get(f"n_chosen_ne_top1_{b}") or 0 for r in qrows) for b in "AB"},
        "top1_alternative_logprob_exactly_zero_tokens": {
            b: sum(r.get(f"n_top1_alt_zero_{b}") or 0 for r in qrows) for b in "AB"},
        "chosen_logprob_exactly_zero_tokens": {
            b: sum(r.get(f"n_chosen_lp_zero_{b}") or 0 for r in qrows) for b in "AB"},
        "parse_fallback": {b: count(b, lambda r, b: not r.get(f"parse_ok_{b}")) for b in "AB"},
        "excluded_from_analysis": excluded,
        "analysis": analysis,
        "primary_result": {
            "signal": "mean_margin_A", "subset": "primary_unchanged_AB",
            **{k: analysis["primary_unchanged_AB"]["signals"]["mean_margin_A"][k]
               for k in ("auc_improved_vs_tie", "auc_ci95", "n_improved", "n_tie")},
        },
        "bootstrap_samples": args.bootstrap_samples, "bootstrap_seed": args.bootstrap_seed,
        "note": METHOD_NOTE,
        "top1_zero_caveat": (
            "If the top-1 alternative itself is reported as 0.0 (the chosen token at T=0), the margin "
            "equals -logprob(top-2) and the renormalised entropy treats p(top-1)=1 before renormalising; "
            "see top1_alternative_logprob_exactly_zero_tokens. Definitions were kept as pre-registered."
        ),
        "compare_models_src": COMPARE_MODELS_SRC, "analyze_signals_src": ANALYZE_SIGNALS_SRC,
    }
    if args.price_in is not None and args.price_out is not None:
        summary["estimated_cost_usd_records_analysed"] = (pt * args.price_in + ct * args.price_out) / 1e6
        summary["price_in_per_1m"], summary["price_out_per_1m"] = args.price_in, args.price_out

    fields = ["_id", "label", "unchanged_both", "delta_class_new_descriptive", "nli_entailment_A", "nli_entailment_B"]
    for b in "AB":
        fields += [f"answer_{b}", f"F1_new_{b}", f"EM_new_{b}", f"parse_ok_{b}", f"mean_margin_{b}",
                   f"min_margin_{b}", f"first_margin_{b}", f"mean_entropy_{b}", f"n_tokens_{b}",
                   f"n_span_tokens_{b}", f"span_fallback_{b}", f"n_margin_missing_{b}",
                   f"n_chosen_ne_top1_{b}", f"n_top1_alt_zero_{b}", f"n_chosen_lp_zero_{b}",
                   f"prompt_tokens_{b}", f"completion_tokens_{b}"]
    pq_path = os.path.join(args.out, "per_question_toplp.csv")
    write_csv(pq_path, qrows, fields)
    cons_rows.sort(key=lambda c: (c["status"] != "CHANGED", c["_id"], c["branch"]))
    cons_path = os.path.join(args.out, "consistency.csv")
    write_csv(cons_path, cons_rows, ["_id", "branch", "status", "step5_answer", "new_answer", "step5_F1",
                                     "new_F1", "F1_diff_new_minus_step5", "step5_delta_class",
                                     "gold_answer", "question"])
    sum_path = os.path.join(args.out, "toplp_summary.json")
    with open(sum_path, "w", encoding="utf-8") as f:
        json.dump(asig_json_safe(summary), f, indent=2, ensure_ascii=False)

    print()
    print(f"calls: new {api_calls}, cache hits {cache_hits}, missing {missing}, errors {errors}   "
          f"tokens prompt {pt} / completion {ct}")
    print(f"changed answers vs Step 5: A {changed['A']}, B {changed['B']}   "
          f"(both unchanged: {summary['consistency_vs_step5']['questions_both_unchanged']}/{len(qrows)})")
    for c in cons_rows:
        if c["status"] == "CHANGED":
            print(f"  CHANGED {c['_id']} {c['branch']}: '{c['step5_answer']}' -> '{c['new_answer']}'  "
                  f"F1 {fmt(c['step5_F1'])} -> {fmt(c['new_F1'])}")
    print(f"span fallback (all tokens): A {summary['span_fallback_to_all_tokens']['A']}, "
          f"B {summary['span_fallback_to_all_tokens']['B']}   chosen!=top1 tokens: "
          f"A {summary['chosen_ne_top1_tokens']['A']}, B {summary['chosen_ne_top1_tokens']['B']}   "
          f"top1 alt == 0.0 tokens: A {summary['top1_alternative_logprob_exactly_zero_tokens']['A']}, "
          f"B {summary['top1_alternative_logprob_exactly_zero_tokens']['B']}")
    if "estimated_cost_usd_records_analysed" in summary:
        print(f"estimated cost (USD, your prices): {summary['estimated_cost_usd_records_analysed']:.4f}")
    print_analysis(analysis, args.bootstrap_samples)
    print(f"wrote {pq_path}\nwrote {cons_path}\nwrote {sum_path}\ncache {cache_path}")
    return 0


def asig_classify(delta, eps=0.0):
    return cm.classify_delta(delta, eps)


def asig_json_safe(obj):
    if isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else obj
    if isinstance(obj, dict):
        return {str(k): asig_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [asig_json_safe(v) for v in obj]
    return obj


if __name__ == "__main__":
    sys.exit(main())

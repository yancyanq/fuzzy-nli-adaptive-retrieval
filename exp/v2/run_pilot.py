#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 5: 100-question pilot (cached A/B branches + local DeBERTa NLI).

Locked settings (overridable by flags; defaults match the pre-registered plan):
  k=2, m=1, answer model deepseek-chat, temperature 0, max_tokens 128
  tie epsilon=0, Oracle chooses A on a tie, positive class = F1_B > F1_A
  go/no-go: bootstrap 95% CI lower bound of mean(Oracle F1 - A F1) > 0
            AND point estimate >= 0.05; improved share >= 10%;
            degraded count <= half of improved count
  NLI: MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli, max 512 tokens
  hypothesis template (deterministic, not an LLM rewrite):
      The answer to the question "{question}" is: {answer}.

Windows (copy this file next to compare_models.py, bm25_topk.py, and pilot.json
under G:\\NLP_project; never put API keys on the command line):

  set DEEPSEEK_API_KEY=...
  python run_pilot.py --data pilot.json --preset deepseek --n 100 ^
      --out step5_pilot --answer-cache step3_deepseek\\cache.jsonl --skip-nli

  python run_pilot.py --data pilot.json --preset deepseek --n 100 ^
      --out step5_pilot --nli-only --nli-backend hf
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import random
import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _import_compare_models():
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(os.getcwd(), "compare_models.py"),
        os.path.join(here, "compare_models.py"),
        os.path.join(here, "..", "step3", "compare_models.py"),
        "/workspace/exp/step3/compare_models.py",
    ]
    seen = set()
    for path in candidates:
        path = os.path.abspath(path)
        if path in seen or not os.path.isfile(path):
            continue
        seen.add(path)
        directory = os.path.dirname(path)
        if directory not in sys.path:
            sys.path.insert(0, directory)
        spec = importlib.util.spec_from_file_location("compare_models", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["compare_models"] = mod
        spec.loader.exec_module(mod)
        return mod, path
    sys.stderr.write(
        "Cannot find compare_models.py. Copy it next to this script "
        "(for example G:\\NLP_project\\compare_models.py) together with bm25_topk.py.\n"
    )
    raise SystemExit(2)


cm, COMPARE_MODELS_SRC = _import_compare_models()

DEFAULT_NLI_MODEL = "MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli"
HYPOTHESIS_TEMPLATE = 'The answer to the question "{question}" is: {answer}.'
MIN_HEADROOM_POINT = 0.05
MIN_IMPROVED_SHARE = 0.10
MAX_DEGRADED_RATIO = 0.5
BOOTSTRAP_B = 10000
BOOTSTRAP_SEED = 42
AUDIT_TARGETS = {
    "false_entailment": 7,
    "false_non_entailment": 7,
    "truncated_or_disagreement": 6,
}
NLI_LABELS = ("entailment", "neutral", "contradiction")


def die(msg, code=2):
    sys.stderr.write(msg.rstrip() + "\n")
    raise SystemExit(code)


def build_hypothesis(question, answer):
    """Deterministic template; not an LLM rewrite of the question+answer."""
    return f'The answer to the question "{question}" is: {answer}.'


def gold_title_set(ex):
    titles = {c[0] for c in ex.get("context") or []}
    return {t for t, _ in (ex.get("supporting_facts") or []) if t in titles}


def unique_in_order(items):
    seen = set()
    out = []
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def paragraph_text(ex, index):
    title, sents = ex["context"][index]
    body = " ".join(sents)
    if body:
        return f"{title}. {body}"
    return str(title)


def build_premise(ex, citation_nums, retrieved_indices):
    """Cited paragraphs in citation order; fallback to retrieved order.

    Duplicate citation numbers are kept only at first occurrence so the same
    paragraph is not repeated in the premise (which would inflate length).

    Returns dict with premise, titles, source_indices, used_fallback.
    """
    usable = []
    n = len(retrieved_indices)
    for c in citation_nums or []:
        if isinstance(c, int) and 1 <= c <= n:
            usable.append(retrieved_indices[c - 1])
    usable = unique_in_order(usable)
    used_fallback = len(usable) == 0
    if used_fallback:
        source = unique_in_order(list(retrieved_indices))
    else:
        source = usable
    titles = [ex["context"][i][0] for i in source] if source else []
    parts = [paragraph_text(ex, i) for i in source]
    return {
        "premise": "\n\n".join(parts),
        "titles": titles,
        "source_indices": list(source),
        "used_fallback": used_fallback,
    }


def coverage_from_titles(pred_titles, gold_titles):
    gold = set(gold_titles)
    pred = unique_in_order(pred_titles)
    n_gold = len(gold)
    hits = len(gold & set(pred))
    recall = (hits / n_gold) if n_gold else float("nan")
    all_gold = bool(n_gold) and hits == n_gold
    any_gold = hits > 0
    return {
        "n_gold": n_gold,
        "hits": hits,
        "recall": recall,
        "all_gold": all_gold,
        "any_gold": any_gold,
    }


def citations_have_sentence_indices(citations):
    """True only when citations include (title_or_para, sentence_index) pairs."""
    if not citations:
        return False
    for item in citations:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            return True
        if isinstance(item, dict) and (
            "sent" in item or "sentence" in item or "sent_id" in item
        ):
            return True
    return False


def official_sp_f1(prediction_pairs, gold_pairs):
    """Sentence-level supporting-fact F1 (HotpotQA official semantics)."""
    pred = set((str(t), int(s)) for t, s in prediction_pairs)
    gold = set((str(t), int(s)) for t, s in gold_pairs)
    if not pred and not gold:
        return 1.0
    if not pred or not gold:
        return 0.0
    tp = len(pred & gold)
    prec = tp / len(pred)
    rec = tp / len(gold)
    if prec + rec == 0:
        return 0.0
    return (2 * prec * rec) / (prec + rec)


def branch_official_sp_f1(ex, citations):
    """Return official SP F1, or None if citations are paragraph-level only."""
    if not citations_have_sentence_indices(citations):
        return None
    pairs = []
    context = ex.get("context") or []
    for item in citations:
        title, sent = None, None
        if isinstance(item, dict):
            title = item.get("title")
            if title is None and item.get("para") is not None:
                idx = int(item["para"]) - 1
                if 0 <= idx < len(context):
                    title = context[idx][0]
            sent = item.get("sent", item.get("sentence", item.get("sent_id")))
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            title, sent = item[0], item[1]
            if isinstance(title, int):
                idx = int(title) - 1
                title = context[idx][0] if 0 <= idx < len(context) else None
        if title is None or sent is None:
            continue
        try:
            pairs.append((str(title), int(sent)))
        except (TypeError, ValueError):
            continue
    gold = [(t, int(s)) for t, s in (ex.get("supporting_facts") or [])]
    return official_sp_f1(pairs, gold)


def classify_delta(delta, eps=0.0):
    """eps=0: improved iff F1_B > F1_A, tie iff equal, degraded iff F1_B < F1_A."""
    return cm.classify_delta(delta, eps)


def oracle_choice(f1_a, f1_b, eps=0.0):
    """Oracle selects B only when F1_B > F1_A + eps; on a tie it selects A.

    With the locked eps=0 this is: choose B iff F1_B > F1_A. Oracle F1 therefore
    equals max(F1_A, F1_B) when eps=0 (on a degradation the max is F1_A).
    """
    if f1_b > f1_a + eps:
        return "B", f1_b
    return "A", f1_a


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def paired_bootstrap_mean_ci(values, n_boot=BOOTSTRAP_B, seed=BOOTSTRAP_SEED, alpha=0.05):
    """Paired bootstrap 95% CI for the mean of per-question values.

    Method: resample the n questions with replacement, B times, using
    random.Random(seed). The point estimate is the mean of the original
    sample. The CI bounds are the empirical alpha/2 and 1-alpha/2
    percentiles of the B bootstrap means, using linear interpolation at
    index q*(B-1) (numpy default / Hyndman-Fan type 7).

    values should already be the paired per-question differences
    (e.g. Oracle F1 - A F1). We do not resample the two branches separately.
    """
    values = list(values)
    n = len(values)
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    point = sum(values) / n
    if n_boot < 1:
        return point, point, point
    rng = random.Random(seed)
    boot = [0.0] * n_boot
    for b in range(n_boot):
        s = 0.0
        for _ in range(n):
            s += values[rng.randrange(n)]
        boot[b] = s / n
    boot.sort()

    def quantile(q):
        if n_boot == 1:
            return boot[0]
        pos = q * (n_boot - 1)
        lo = int(math.floor(pos))
        hi = int(math.ceil(pos))
        lo = max(0, min(n_boot - 1, lo))
        hi = max(0, min(n_boot - 1, hi))
        if lo == hi:
            return boot[lo]
        w = pos - lo
        return boot[lo] * (1.0 - w) + boot[hi] * w

    lo = quantile(alpha / 2.0)
    hi = quantile(1.0 - alpha / 2.0)
    return point, lo, hi


def go_nogo(
    n,
    n_improved,
    n_degraded,
    point,
    ci_lo,
    min_headroom=MIN_HEADROOM_POINT,
    min_improved_share=MIN_IMPROVED_SHARE,
    max_degraded_ratio=MAX_DEGRADED_RATIO,
):
    """Pre-registered go/no-go. Overall GO only if all three criteria pass."""
    improved_share = (n_improved / n) if n else float("nan")
    if n_improved > 0:
        degraded_ratio = n_degraded / n_improved
        ratio_pass = n_degraded <= max_degraded_ratio * n_improved
    else:
        # 0 improved: ratio is undefined if any degradation; 0/0 counts as 0.
        degraded_ratio = float("inf") if n_degraded > 0 else 0.0
        ratio_pass = n_degraded <= 0

    headroom_point_pass = (point == point) and point >= min_headroom
    headroom_ci_pass = (ci_lo == ci_lo) and ci_lo > 0
    headroom_pass = bool(headroom_point_pass and headroom_ci_pass)
    improved_pass = (improved_share == improved_share) and improved_share >= min_improved_share

    criteria = [
        {
            "id": "headroom_point",
            "name": "headroom point (mean Oracle F1 - A F1)",
            "observed": point,
            "threshold": f">= {min_headroom}",
            "pass": bool(headroom_point_pass),
        },
        {
            "id": "headroom_ci_lo",
            "name": "headroom 95% CI lower bound",
            "observed": ci_lo,
            "threshold": "> 0",
            "pass": bool(headroom_ci_pass),
        },
        {
            "id": "improved_share",
            "name": "improved share",
            "observed": improved_share,
            "observed_count": n_improved,
            "n": n,
            "threshold": f">= {min_improved_share:.0%}",
            "pass": bool(improved_pass),
        },
        {
            "id": "degraded_ratio",
            "name": "degraded / improved",
            "observed": degraded_ratio if degraded_ratio != float("inf") else None,
            "n_degraded": n_degraded,
            "n_improved": n_improved,
            "threshold": f"<= {max_degraded_ratio}",
            "pass": bool(ratio_pass),
        },
    ]
    overall = bool(headroom_pass and improved_pass and ratio_pass)
    return {
        "overall": "GO" if overall else "NO-GO",
        "overall_pass": overall,
        "headroom_pass": headroom_pass,
        "criteria": criteria,
        "improved_share": improved_share,
        "degraded_ratio": None if degraded_ratio == float("inf") else degraded_ratio,
    }


def softmax(logits):
    vals = [float(x) for x in logits]
    top = max(vals)
    exps = [math.exp(x - top) for x in vals]
    total = sum(exps) or 1.0
    return [e / total for e in exps]


def normalize_label_name(name):
    s = str(name).strip().lower()
    if s in {"entailment", "entails", "entailed", "entail", "e"}:
        return "entailment"
    if s in {"neutral", "n"}:
        return "neutral"
    if s in {"contradiction", "contradictory", "contradicts", "contradict", "c"}:
        return "contradiction"
    return s


def id2label_map(raw):
    """Accept {0: 'entailment'} or {'0': 'ENTAILMENT'} and normalize names."""
    out = {}
    for k, v in (raw or {}).items():
        try:
            idx = int(k)
        except (TypeError, ValueError):
            continue
        out[idx] = normalize_label_name(v)
    return out


def probs_from_logits(logits, id2label):
    mapping = id2label_map(id2label)
    probs = softmax(logits)
    out = {lab: 0.0 for lab in NLI_LABELS}
    unknown = []
    for i, p in enumerate(probs):
        name = mapping.get(i, f"label_{i}")
        if name in out:
            out[name] = p
        else:
            unknown.append({"index": i, "name": name, "prob": p})
    argmax = max(NLI_LABELS, key=lambda lab: out[lab])
    return out, argmax, unknown


def mock_token_count(premise, hypothesis):
    """MOCK-ONLY length: whitespace tokens plus 3 special-token placeholders.

    This is not a DeBERTa tokenizer and must not be reported as a real
    truncation count from the Hugging Face model.
    """
    return len((premise or "").split()) + len((hypothesis or "").split()) + 3


def mock_nli_score(premise, hypothesis, max_length=512):
    """Deterministic fake NLI scores. NOT experimental results."""
    n_tokens = mock_token_count(premise, hypothesis)
    truncated = n_tokens > max_length
    digest = hashlib.sha256(f"{premise}\n{hypothesis}".encode("utf-8")).digest()
    logits = [
        (digest[0] / 127.5) - 1.0,
        (digest[1] / 127.5) - 1.0,
        (digest[2] / 127.5) - 1.0,
    ]
    id2label = {0: "entailment", 1: "neutral", 2: "contradiction"}
    probs, argmax, unknown = probs_from_logits(logits, id2label)
    return {
        "probs": probs,
        "argmax": argmax,
        "logits": logits,
        "n_tokens": n_tokens,
        "truncated": truncated,
        "id2label": {str(k): v for k, v in id2label.items()},
        "unknown_labels": unknown,
        "backend": "mock",
    }


class MockNliScorer:
    def __init__(self, max_length=512, model_name="mock-nli"):
        self.max_length = max_length
        self.model_name = model_name
        self.backend = "mock"
        sys.stderr.write(
            "\n"
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
            "WARNING: --nli-backend mock is active. NLI scores are FAKE\n"
            "and must not be reported as experimental results.\n"
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n\n"
        )

    def score_many(self, items):
        out = []
        for it in items:
            rec = mock_nli_score(it["premise"], it["hypothesis"], self.max_length)
            rec["model"] = self.model_name
            out.append(rec)
        return out


class HFNliScorer:
    def __init__(self, model_name, device, max_length=512, batch_size=4):
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError:
            die(
                "Missing dependency for --nli-backend hf: "
                "pip install transformers torch\n"
                "On YangQS (CUDA), install a CUDA build of torch from https://pytorch.org "
                "if `python -c \"import torch; print(torch.cuda.is_available())\"` is False."
            )
        self.torch = torch
        self.max_length = max_length
        self.batch_size = max(1, int(batch_size))
        self.model_name = model_name
        self.backend = "hf"
        self.device = device
        sys.stderr.write(f"[nli] loading {model_name} on {device} ...\n")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.model.eval()
        self.model.to(device)
        raw_map = dict(self.model.config.id2label or {})
        self.id2label = id2label_map(raw_map)
        self.id2label_raw = {str(k): str(v) for k, v in raw_map.items()}
        mapped = sorted(set(self.id2label.values()))
        sys.stderr.write(
            f"[nli] model id2label (raw)={self.id2label_raw}  "
            f"normalized={self.id2label}\n"
        )
        missing = [lab for lab in NLI_LABELS if lab not in mapped]
        if missing:
            sys.stderr.write(
                f"[nli] warning: normalized id2label is missing {missing}; "
                "probabilities for those labels will be 0. Check the checkpoint.\n"
            )

    def _n_tokens(self, premise, hypothesis):
        enc = self.tokenizer(
            premise,
            hypothesis,
            truncation=False,
            add_special_tokens=True,
        )
        return len(enc["input_ids"])

    def score_many(self, items):
        torch = self.torch
        results = [None] * len(items)
        token_counts = [self._n_tokens(it["premise"], it["hypothesis"]) for it in items]
        bs = self.batch_size
        for start in range(0, len(items), bs):
            chunk = items[start : start + bs]
            premises = [it["premise"] for it in chunk]
            hyps = [it["hypothesis"] for it in chunk]
            enc = self.tokenizer(
                premises,
                hyps,
                truncation=True,
                max_length=self.max_length,
                padding=True,
                return_tensors="pt",
            )
            enc = {k: v.to(self.device) for k, v in enc.items()}
            try:
                with torch.inference_mode():
                    if self.device == "cuda":
                        with torch.autocast(device_type="cuda", dtype=torch.float16):
                            logits = self.model(**enc).logits
                    else:
                        logits = self.model(**enc).logits
                logits = logits.detach().float().cpu().tolist()
            except RuntimeError as exc:
                if "out of memory" in str(exc).lower():
                    die(
                        f"CUDA out of memory during NLI (batch_size={self.batch_size}). "
                        "Re-run with a smaller --nli-batch-size, e.g. 1 or 2."
                    )
                raise
            for offset, logit_row in enumerate(logits):
                idx = start + offset
                probs, argmax, unknown = probs_from_logits(logit_row, self.id2label)
                n_tokens = token_counts[idx]
                results[idx] = {
                    "probs": probs,
                    "argmax": argmax,
                    "logits": [float(x) for x in logit_row],
                    "n_tokens": n_tokens,
                    "truncated": n_tokens > self.max_length,
                    "id2label": self.id2label_raw,
                    "unknown_labels": unknown,
                    "backend": "hf",
                    "model": self.model_name,
                }
            done = min(start + bs, len(items))
            if done == len(items) or done % max(bs, 10) == 0 or start == 0:
                sys.stderr.write(f"[nli] scored {done}/{len(items)}\n")
        return results


def resolve_nli_device(requested):
    if requested and requested != "auto":
        return requested
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"


def make_nli_scorer(args):
    if args.nli_backend == "mock":
        return MockNliScorer(max_length=args.nli_max_length, model_name="mock-nli")
    device = resolve_nli_device(args.nli_device)
    if device == "cpu":
        sys.stderr.write(
            "[warn] NLI will run on CPU. The 4060 should use --nli-device cuda "
            "(or --nli-device auto when CUDA is visible). CPU is slow but valid.\n"
        )
    if device == "cuda":
        try:
            import torch
            if not torch.cuda.is_available():
                die(
                    "Requested CUDA but torch.cuda.is_available() is False. "
                    "Install a CUDA build of torch, or pass --nli-device cpu."
                )
        except ImportError:
            die("Missing dependency for --nli-backend hf: pip install transformers torch")
    return HFNliScorer(
        model_name=args.nli_model,
        device=device,
        max_length=args.nli_max_length,
        batch_size=args.nli_batch_size,
    )


def classify_nli_error(row, branch):
    """Return an audit error type or None.

    Priority if several would apply: (a) false entailment, then (b) false
    non-entailment, then (c) truncated or remaining entailment/coverage
    disagreement. A (question, branch) is assigned at most one type.
    """
    p = branch.upper()
    argmax = row.get(f"nli_argmax_{p}")
    if not argmax:
        return None
    f1 = row.get(f"F1_{p}")
    em = row.get(f"EM_{p}")
    cite_hits = row.get(f"cite_gold_hits_{p}") or 0
    retr_titles = row.get(f"retrieved_titles_{p}") or []
    cite_titles = row.get(f"citation_titles_{p}") or []
    gold = set(row.get("gold_titles") or [])
    in_cite_or_retr = bool(gold & (set(cite_titles) | set(retr_titles)))
    premise_titles = row.get(f"nli_premise_titles_{p}") or []
    gold_in_premise = bool(gold & set(premise_titles))
    truncated = bool(row.get(f"nli_truncated_{p}"))
    answer_wrong = (f1 is not None and f1 == 0.0)
    cites_miss_all = cite_hits == 0
    strong_answer = (em == 1.0) or (f1 is not None and f1 >= 0.5)

    if argmax == "entailment" and (answer_wrong or cites_miss_all):
        return "false_entailment"
    if argmax != "entailment" and strong_answer and in_cite_or_retr:
        return "false_non_entailment"
    disagree = (argmax == "entailment" and not gold_in_premise) or (
        argmax != "entailment" and gold_in_premise
    )
    if truncated or disagree:
        return "truncated_or_disagreement"
    return None


def _interleave_branches(items, rng):
    a = [x for x in items if x.get("branch") == "A"]
    b = [x for x in items if x.get("branch") == "B"]
    rng.shuffle(a)
    rng.shuffle(b)
    out = []
    i = j = 0
    while i < len(a) or j < len(b):
        if i <= j and i < len(a):
            out.append(a[i])
            i += 1
        elif j < len(b):
            out.append(b[j])
            j += 1
        else:
            out.append(a[i])
            i += 1
    return out


def sample_audit(rows, n_target=20, targets=None, seed=42):
    """Stratified sample of up to 20 (question, branch) rows.

    If a type has fewer candidates than its quota, take all of them and
    record the shortfall. Quotas are not back-filled from other types.
    """
    targets = dict(targets or AUDIT_TARGETS)
    type_names = ("false_entailment", "false_non_entailment", "truncated_or_disagreement")
    rng = random.Random(seed)
    pools = {t: [] for t in type_names}
    for row in rows:
        for branch in ("A", "B"):
            typ = classify_nli_error(row, branch)
            if not typ:
                continue
            pools[typ].append({"_id": row["_id"], "branch": branch, "error_type": typ, "row": row})

    selected = []
    shortfalls = {}
    pool_sizes = {t: len(pools[t]) for t in type_names}
    for typ in type_names:
        quota = targets.get(typ, 0)
        ordered = _interleave_branches(pools[typ], rng)
        take = ordered[:quota]
        selected.extend(take)
        if len(take) < quota:
            shortfalls[typ] = {
                "target": quota,
                "available": len(ordered),
                "taken": len(take),
                "shortfall": quota - len(take),
            }
    selected = selected[:n_target]
    notes = []
    for typ, info in shortfalls.items():
        notes.append(
            f"{typ}: available {info['available']} < target {info['target']} "
            f"(shortfall {info['shortfall']})"
        )
    return selected, {
        "targets": targets,
        "pool_sizes": pool_sizes,
        "shortfalls": shortfalls,
        "n_selected": len(selected),
        "notes": notes,
        "seed": seed,
    }


def load_merged_cache(write_path, answer_cache_path, model, k, m, no_cache):
    table = {}
    source = {}
    if answer_cache_path:
        extra = cm.load_cache(answer_cache_path, model, k, m)
        for key, rec in extra.items():
            table[key] = rec
            source[key] = "answer-cache"
        print(f"answer-cache loaded: {len(extra)} entries from {answer_cache_path}")
    if not no_cache and write_path:
        own = cm.load_cache(write_path, model, k, m)
        for key, rec in own.items():
            table[key] = rec
            source[key] = "out-cache"
        if own:
            print(f"cache loaded: {len(own)} entries from {write_path}")
    return table, source


def packed_from_cache_rec(rec):
    return {
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


def write_cache_rec(cache_path, cache, source, key, rec):
    if cache_path:
        already = source.get(key) == "out-cache"
        if not already:
            cm.append_cache(cache_path, rec)
            source[key] = "out-cache"
    cache[key] = rec


def evaluate_from_cache_or_api(client_holder, model, ex, branch, indices, args, cache, source, cache_path):
    key = cm.cache_key(model, ex["_id"], branch)
    if cache is not None and key in cache:
        rec = cache[key]
        packed = packed_from_cache_rec(rec)
        result = cm.evaluate_branch(ex, indices, packed)
        if cache_path and source.get(key) != "out-cache":
            out_rec = {k: rec.get(k) for k in cm.CACHE_FIELDS}
            out_rec["model"] = model
            out_rec["_id"] = ex["_id"]
            out_rec["branch"] = branch
            out_rec["k"] = args.k
            out_rec["m"] = args.m
            write_cache_rec(cache_path, cache, source, key, out_rec)
        return result, False
    if args.nli_only:
        die(
            f"Missing cached answer for _id={ex['_id']} branch={branch}. "
            "Run without --nli-only first (with --answer-cache if reusing Step 3)."
        )
    client = client_holder.get()
    messages = cm.build_messages(ex, indices)
    packed = cm.call_with_retries(client, model, messages, args)
    result = cm.evaluate_branch(ex, indices, packed)
    if cache is not None:
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
        if cache_path:
            write_cache_rec(cache_path, cache, source, key, rec)
        else:
            cache[key] = rec
    if args.sleep > 0 and not packed.get("from_cache"):
        time.sleep(args.sleep)
    return result, True


class ClientHolder:
    def __init__(self, base_url, key_env, allow_missing):
        self.base_url = base_url
        self.key_env = key_env
        self.allow_missing = allow_missing
        self._client = None

    def get(self):
        if self._client is None:
            self._client = cm.make_client(self.base_url, self.key_env, self.allow_missing)
        return self._client


def load_branches_jsonl(path):
    recs = []
    if not path or not os.path.isfile(path):
        return recs
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            recs.append(json.loads(line))
    return recs


def attach_branch_coverage(ex, res, r_indices, prefix, gold):
    retr_titles = [ex["context"][i][0] for i in r_indices]
    cite_titles = list(res.get("citation_titles") or [])
    retr = coverage_from_titles(retr_titles, gold)
    cite = coverage_from_titles(cite_titles, gold)
    official = branch_official_sp_f1(ex, res.get("citations") or [])
    return {
        f"retrieved_titles_{prefix}": retr_titles,
        f"citation_titles_{prefix}": cite_titles,
        f"retr_gold_hits_{prefix}": retr["hits"],
        f"retr_recall_{prefix}": retr["recall"],
        f"retr_all_gold_{prefix}": retr["all_gold"],
        f"cite_gold_hits_{prefix}": cite["hits"],
        f"cite_recall_{prefix}": cite["recall"],
        f"cite_all_gold_{prefix}": cite["all_gold"],
        f"official_sp_f1_{prefix}": official,
    }


def build_question_row(ex, r1, r2, res_a, res_b, tie_eps):
    gold = sorted(gold_title_set(ex))
    idx_a = list(r1)
    idx_b = list(r1) + list(r2)
    delta = res_b["F1"] - res_a["F1"]
    klass = classify_delta(delta, tie_eps)
    oracle_branch, oracle_f1 = oracle_choice(res_a["F1"], res_b["F1"], tie_eps)
    row = {
        "_id": ex["_id"],
        "question": ex.get("question", ""),
        "gold_answer": ex.get("answer", ""),
        "type": ex.get("type"),
        "level": ex.get("level"),
        "gold_titles": gold,
        "n_gold": len(gold),
        "answer_A": res_a["answer"],
        "answer_B": res_b["answer"],
        "F1_A": res_a["F1"],
        "F1_B": res_b["F1"],
        "delta": delta,
        "delta_class": klass,
        "EM_A": res_a["EM"],
        "EM_B": res_b["EM"],
        "oracle_branch": oracle_branch,
        "oracle_F1": oracle_f1,
        "oracle_minus_A": oracle_f1 - res_a["F1"],
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
        "citations_A": " | ".join(res_a.get("citation_titles") or []),
        "citations_B": " | ".join(res_b.get("citation_titles") or []),
        "r1_titles": " | ".join(ex["context"][i][0] for i in r1),
        "r2_titles": " | ".join(ex["context"][i][0] for i in r2),
        "parse_ok_A": res_a["parse_ok"],
        "parse_ok_B": res_b["parse_ok"],
        "error_A": res_a["error"] or "",
        "error_B": res_b["error"] or "",
        "from_cache_A": res_a.get("from_cache", False),
        "from_cache_B": res_b.get("from_cache", False),
        "r1_indices": list(r1),
        "r2_indices": list(r2),
    }
    cov_r1 = coverage_from_titles([ex["context"][i][0] for i in r1], gold)
    cov_r2 = coverage_from_titles([ex["context"][i][0] for i in idx_b], gold)
    row["r1_recall"] = cov_r1["recall"]
    row["r1_both_gold"] = cov_r1["all_gold"]
    row["r2_recall"] = cov_r2["recall"]
    row["r2_both_gold"] = cov_r2["all_gold"]
    row.update(attach_branch_coverage(ex, res_a, idx_a, "A", gold))
    row.update(attach_branch_coverage(ex, res_b, idx_b, "B", gold))
    row["_res_A"] = res_a
    row["_res_B"] = res_b
    row["_ex"] = ex
    return row


def attach_nli_to_row(row, branch, premise_info, hyp, score):
    p = branch.upper()
    probs = score["probs"]
    row[f"nli_entailment_{p}"] = probs["entailment"]
    row[f"nli_neutral_{p}"] = probs["neutral"]
    row[f"nli_contradiction_{p}"] = probs["contradiction"]
    row[f"nli_argmax_{p}"] = score["argmax"]
    row[f"nli_truncated_{p}"] = bool(score["truncated"])
    row[f"nli_tokens_{p}"] = score["n_tokens"]
    row[f"nli_fallback_{p}"] = bool(premise_info["used_fallback"])
    row[f"nli_premise_titles_{p}"] = list(premise_info["titles"])
    row[f"nli_hypothesis_{p}"] = hyp
    return {
        "_id": row["_id"],
        "branch": p,
        "premise": premise_info["premise"],
        "hypothesis": hyp,
        "used_fallback_premise": bool(premise_info["used_fallback"]),
        "premise_titles": list(premise_info["titles"]),
        "source_indices": list(premise_info["source_indices"]),
        "n_tokens": score["n_tokens"],
        "truncated": bool(score["truncated"]),
        "max_length": score.get("max_length"),
        "probs": probs,
        "argmax": score["argmax"],
        "nli_backend": score.get("backend"),
        "nli_model": score.get("model"),
        "id2label": score.get("id2label"),
    }


CSV_SKIP_KEYS = {
    "_res_A",
    "_res_B",
    "_ex",
    "retrieved_titles_A",
    "retrieved_titles_B",
    "citation_titles_A",
    "citation_titles_B",
    "nli_premise_titles_A",
    "nli_premise_titles_B",
    "nli_hypothesis_A",
    "nli_hypothesis_B",
    "r1_indices",
    "r2_indices",
    "gold_titles",
}


def flatten_for_csv(row):
    out = {}
    for k, v in row.items():
        if k in CSV_SKIP_KEYS:
            continue
        if isinstance(v, bool):
            out[k] = v
        elif isinstance(v, float):
            out[k] = "" if v != v else v
        elif v is None:
            out[k] = ""
        elif isinstance(v, (list, tuple, dict)):
            out[k] = json.dumps(v, ensure_ascii=False)
        else:
            out[k] = v
    out["gold_titles"] = " | ".join(row.get("gold_titles") or [])
    out["nli_premise_titles_A"] = " | ".join(row.get("nli_premise_titles_A") or [])
    out["nli_premise_titles_B"] = " | ".join(row.get("nli_premise_titles_B") or [])
    out["nli_fallback_A"] = row.get("nli_fallback_A", "")
    out["nli_fallback_B"] = row.get("nli_fallback_B", "")
    return out


def write_csv(path, rows, fieldnames=None):
    flat = [flatten_for_csv(r) for r in rows]
    if not fieldnames:
        fieldnames = list(flat[0].keys()) if flat else ["_id"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(flat)


def write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            slim = json.loads(json.dumps(rec, ensure_ascii=False, default=str))
            f.write(json.dumps(slim, ensure_ascii=False) + "\n")


def json_safe(obj):
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    return obj


def _fmt(x, digits=3):
    if x is None:
        return "-"
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return "-"
    if isinstance(x, float):
        return f"{x:.{digits}f}"
    return str(x)


def print_quality_table(summary):
    s = summary
    print()
    print(
        f"model={s['model']}  data={s['data']}  n={s['n']}  k={s['k']}  m={s['m']}"
    )
    print("-" * 72)
    print(f"{'':28} {'A (round1)':>14} {'B (round1+2)':>14} {'Oracle':>14}")
    print(f"{'mean EM':28} {s['mean_EM_A']:14.3f} {s['mean_EM_B']:14.3f} {'-':>14}")
    print(f"{'mean F1':28} {s['mean_F1_A']:14.3f} {s['mean_F1_B']:14.3f} {s['oracle_F1']:14.3f}")
    print(
        f"improved / tie / degraded (eps={s['tie_eps']}): "
        f"{s['n_improved']} / {s['n_tie']} / {s['n_degraded']}"
    )
    print(
        f"mean(Oracle F1 - A F1):      {_fmt(s['oracle_minus_A_point'])}  "
        f"95% CI [{_fmt(s['oracle_minus_A_ci_lo'])}, {_fmt(s['oracle_minus_A_ci_hi'])}]"
    )
    print(f"oracle branch = B (re-retrieve): {s['n_oracle_B']} / {s['n']}")
    print(
        f"retrieval recall / both-gold:  "
        f"A {_fmt(s['retrieval']['r1_recall'])} / {_fmt(s['retrieval']['r1_both_gold'])}   "
        f"B {_fmt(s['retrieval']['r2_recall'])} / {_fmt(s['retrieval']['r2_both_gold'])}"
    )
    print(
        f"citation recall / all-gold:    "
        f"A {_fmt(s['citation']['cite_recall_A'])} / {_fmt(s['citation']['cite_all_gold_A'])}   "
        f"B {_fmt(s['citation']['cite_recall_B'])} / {_fmt(s['citation']['cite_all_gold_B'])}"
    )
    print(f"official sentence-level SP F1: {s['official_sp_f1_note']}")
    print(f"mean prompt tokens / call:     {s['mean_prompt_tokens_per_call']:.1f}")
    print(f"mean completion tokens / call: {s['mean_completion_tokens_per_call']:.1f}")
    print(f"total tokens:                  {s['total_tokens']}")
    print(f"mean latency / call (s):       {_fmt(s['mean_latency'])}")
    print(f"logprobs_supported:            {s['logprobs_supported']}")
    print(f"cache hits / new API calls:    {s['cache_hits']} / {s['api_calls']}")
    if s.get("n_errors"):
        print(f"API / parse errors:            {s['n_errors']} API, {s['n_parse_fallback']} parse-fallback")
    if s.get("nli_ran"):
        nli = s["nli"]
        fake = "  (FAKE — mock backend, not a result)" if nli.get("scores_are_fake") else ""
        print(
            f"NLI mean P(entailment):        "
            f"A {_fmt(nli['mean_entailment_A'])}  B {_fmt(nli['mean_entailment_B'])}{fake}"
        )
        print(
            f"NLI truncated:                 "
            f"A {nli['n_truncated_A']}/{s['n']}  "
            f"B {nli['n_truncated_B']}/{s['n']}  "
            f"overall {nli['n_truncated']}/{2 * s['n']}"
        )
        print(
            f"NLI fallback (no usable cites): "
            f"A {nli['n_fallback_A']}/{s['n']}  B {nli['n_fallback_B']}/{s['n']}"
        )
    else:
        print("NLI: not run (--skip-nli). Answer-quality go/no-go is still computed.")
    if s.get("estimated_cost_this_run") is not None:
        print(f"estimated cost ({s['n']} q x 2 branches): ${s['estimated_cost_this_run']:.4f}")
        if s.get("estimated_cost_1600x2") is not None:
            print(f"extrapolated (1600 q x 2 branches):  ${s['estimated_cost_1600x2']:.4f}")
        print("(prices are USD per 1M tokens you supplied; check the vendor page for current rates)")
    else:
        print("cost: not estimated (pass --price-in and --price-out, USD per 1M tokens)")
    print()


def print_gonogo_table(summary):
    g = summary["go_nogo"]
    print("Go / no-go (pre-registered criteria; not tuned on these results)")
    print("-" * 88)
    print(f"{'criterion':<42} {'observed':>18} {'threshold':>16} {'result':>8}")
    for c in g["criteria"]:
        if c["id"] == "improved_share":
            obs = f"{c['observed_count']}/{c['n']} = {_fmt(c['observed'] * 100, 1)}%"
        elif c["id"] == "degraded_ratio":
            if c["n_improved"] == 0:
                obs = f"{c['n_degraded']}/{c['n_improved']} (undef)" if c["n_degraded"] else "0/0 = 0"
            else:
                obs = f"{c['n_degraded']}/{c['n_improved']} = {_fmt(c['observed'], 3)}"
        else:
            obs = _fmt(c["observed"])
        mark = "PASS" if c["pass"] else "FAIL"
        print(f"{c['name']:<42} {obs:>18} {c['threshold']:>16} {mark:>8}")
    print("-" * 88)
    print(f"{'OVERALL':<42} {g['overall']:>18}")
    if not summary.get("nli_ran"):
        print("Note: NLI was not run in this invocation; the verdict above is answer-quality only.")
    if summary.get("nli", {}).get("scores_are_fake"):
        print("Note: NLI scores in this run are FAKE (mock backend) and are not experimental results.")
    print()


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="Step 5: 100-question pilot with cached A/B branches and local NLI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--data", required=True, help="Official-format HotpotQA JSON (e.g. pilot.json)")
    ap.add_argument("--preset", choices=("deepseek", "openai", "custom"), default="deepseek")
    ap.add_argument("--base-url", default=None, help="Override / required for --preset custom")
    ap.add_argument("--model", default=None, help="Override model name / required for custom")
    ap.add_argument("--key-env", default=None, help="Name of the env var that holds the API key")
    ap.add_argument("--n", type=int, default=100, help="Use the first N questions of the file")
    ap.add_argument("--k", type=int, default=2, help="Round-1 BM25 top-k (default 2)")
    ap.add_argument("--m", type=int, default=1, help="Round-2 paragraphs to add (default 1)")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int, default=128)
    ap.add_argument("--timeout", type=float, default=60.0, help="Per-request timeout in seconds")
    ap.add_argument("--max-retries", type=int, default=5)
    ap.add_argument("--sleep", type=float, default=0.0, help="Optional pause between new API calls")
    ap.add_argument("--tie-eps", type=float, default=0.0, help="Tie tolerance on F1_B - F1_A (locked: 0)")
    ap.add_argument("--out", default="step5_pilot", help="Output directory (default step5_pilot)")
    ap.add_argument(
        "--answer-cache",
        default=None,
        help="Read-only extra cache (e.g. step3_deepseek\\cache.jsonl) reused before new API calls",
    )
    ap.add_argument("--cache", default=None, help="Write cache jsonl path (default: <out>/cache.jsonl)")
    ap.add_argument("--no-cache", action="store_true", help="Do not read or write <out>/cache.jsonl")
    ap.add_argument("--price-in", type=float, default=None, help="USD per 1M prompt tokens")
    ap.add_argument("--price-out", type=float, default=None, help="USD per 1M completion tokens")
    ap.add_argument("--min-headroom", type=float, default=MIN_HEADROOM_POINT)
    ap.add_argument("--min-improved-share", type=float, default=MIN_IMPROVED_SHARE)
    ap.add_argument("--max-degraded-ratio", type=float, default=MAX_DEGRADED_RATIO)
    ap.add_argument("--bootstrap-samples", type=int, default=BOOTSTRAP_B)
    ap.add_argument("--bootstrap-seed", type=int, default=BOOTSTRAP_SEED)
    ap.add_argument("--nli-model", default=DEFAULT_NLI_MODEL)
    ap.add_argument("--nli-device", default="auto", help="auto, cuda, or cpu")
    ap.add_argument("--nli-batch-size", type=int, default=4)
    ap.add_argument("--nli-max-length", type=int, default=512)
    ap.add_argument(
        "--nli-backend",
        choices=("hf", "mock"),
        default="hf",
        help="hf = Hugging Face DeBERTa (default). mock = FAKE scores for tests only.",
    )
    ap.add_argument("--skip-nli", action="store_true", help="Answer branches only; no NLI")
    ap.add_argument(
        "--nli-only",
        action="store_true",
        help="Read existing answers under --out or --answer-cache and (re)run NLI only",
    )
    ap.add_argument("--audit-n", type=int, default=20, help="Max rows in audit_sample.csv")
    ap.add_argument("--audit-seed", type=int, default=42)
    return ap.parse_args(argv)


def load_examples(path, n):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        die("Expected a JSON list of HotpotQA examples")
    if n <= 0:
        die("--n must be positive")
    return data[:n]


def collect_quality(rows, args, data_path, model, base_url, key_env, out_dir, cache_hits, api_calls, nli_ran, nli_meta, audit_meta):
    n = len(rows)

    def col(name):
        return [r[name] for r in rows]

    n_improved = sum(1 for r in rows if r["delta_class"] == "improved")
    n_tie = sum(1 for r in rows if r["delta_class"] == "tie")
    n_degraded = sum(1 for r in rows if r["delta_class"] == "degraded")
    n_oracle_b = sum(1 for r in rows if r["oracle_branch"] == "B")
    deltas = [r["oracle_minus_A"] for r in rows]
    point, ci_lo, ci_hi = paired_bootstrap_mean_ci(
        deltas, n_boot=args.bootstrap_samples, seed=args.bootstrap_seed
    )
    verdict = go_nogo(
        n,
        n_improved,
        n_degraded,
        point,
        ci_lo,
        min_headroom=args.min_headroom,
        min_improved_share=args.min_improved_share,
        max_degraded_ratio=args.max_degraded_ratio,
    )

    def mean_bool(key):
        xs = [1.0 if r[key] else 0.0 for r in rows if r.get(key) == r.get(key)]
        return mean(xs) if xs else float("nan")

    def mean_num(key):
        xs = [r[key] for r in rows if r.get(key) is not None and r[key] == r[key]]
        return mean(xs) if xs else float("nan")

    official_vals = [
        r[k]
        for r in rows
        for k in ("official_sp_f1_A", "official_sp_f1_B")
        if r.get(k) is not None
    ]
    if official_vals:
        official_note = f"computed; mean={mean(official_vals):.3f} over {len(official_vals)} branches"
    else:
        official_note = (
            "null (answer format cites paragraph numbers only; "
            "official supporting-fact F1 is sentence-level and was not computed)"
        )

    prompt_tokens = sum(r["prompt_tokens_A"] + r["prompt_tokens_B"] for r in rows)
    completion_tokens = sum(r["completion_tokens_A"] + r["completion_tokens_B"] for r in rows)
    n_calls = 2 * n if n else 0
    latencies = [r["latency_A"] for r in rows] + [r["latency_B"] for r in rows]
    n_errors = sum(1 for r in rows if r["error_A"] or r["error_B"])
    n_parse_fallback = sum(1 for r in rows if (not r["parse_ok_A"]) or (not r["parse_ok_B"]))

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
        "oracle_F1": mean(col("oracle_F1")) if rows else float("nan"),
        "oracle_minus_A_point": point,
        "oracle_minus_A_ci_lo": ci_lo,
        "oracle_minus_A_ci_hi": ci_hi,
        "oracle_minus_A_ci": [ci_lo, ci_hi],
        "bootstrap_samples": args.bootstrap_samples,
        "bootstrap_seed": args.bootstrap_seed,
        "n_improved": n_improved,
        "n_tie": n_tie,
        "n_degraded": n_degraded,
        "improved_rate": (n_improved / n) if n else float("nan"),
        "tie_rate": (n_tie / n) if n else float("nan"),
        "degraded_rate": (n_degraded / n) if n else float("nan"),
        "degraded_improved_ratio": verdict["degraded_ratio"],
        "n_oracle_B": n_oracle_b,
        "oracle_reretrieve_rate": (n_oracle_b / n) if n else float("nan"),
        "retrieval": {
            "r1_recall": mean_num("r1_recall"),
            "r1_both_gold": mean_bool("r1_both_gold"),
            "r2_recall": mean_num("r2_recall"),
            "r2_both_gold": mean_bool("r2_both_gold"),
        },
        "citation": {
            "cite_recall_A": mean_num("cite_recall_A"),
            "cite_all_gold_A": mean_bool("cite_all_gold_A"),
            "cite_recall_B": mean_num("cite_recall_B"),
            "cite_all_gold_B": mean_bool("cite_all_gold_B"),
        },
        "official_sp_f1_note": official_note,
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
        "bm25_source": getattr(cm, "_BM25_SRC", None),
        "compare_models_src": COMPARE_MODELS_SRC,
        "hypothesis_template": HYPOTHESIS_TEMPLATE,
        "nli_ran": bool(nli_ran),
        "go_nogo": verdict,
        "out": os.path.abspath(out_dir),
    }
    if args.price_in is not None and args.price_out is not None:
        cost = (prompt_tokens * args.price_in + completion_tokens * args.price_out) / 1_000_000.0
        summary["price_in_per_1m"] = args.price_in
        summary["price_out_per_1m"] = args.price_out
        summary["estimated_cost_this_run"] = cost
        summary["estimated_cost_1600x2"] = (cost / n * 1600.0) if n else None
    else:
        summary["estimated_cost_this_run"] = None
        summary["estimated_cost_1600x2"] = None
    if nli_ran:
        summary["nli"] = nli_meta
    else:
        summary["nli"] = {"ran": False, "reason": "skip-nli"}
    if audit_meta is not None:
        summary["audit"] = audit_meta
    return summary


def write_audit_csv(path, selected, audit_meta):
    fieldnames = [
        "_id",
        "branch",
        "error_type",
        "question",
        "gold_answer",
        "model_answer",
        "F1",
        "EM",
        "gold_titles",
        "citation_titles",
        "retrieved_titles",
        "nli_premise_titles",
        "nli_argmax",
        "nli_entailment",
        "nli_neutral",
        "nli_contradiction",
        "nli_truncated",
        "nli_tokens",
        "nli_fallback",
        "hypothesis",
        "cite_gold_hits",
        "human_label",
        "shortfall_note",
    ]
    notes = "; ".join(audit_meta.get("notes") or [])
    out_rows = []
    for i, item in enumerate(selected):
        row = item["row"]
        b = item["branch"]
        out_rows.append({
            "_id": item["_id"],
            "branch": b,
            "error_type": item["error_type"],
            "question": row.get("question", ""),
            "gold_answer": row.get("gold_answer", ""),
            "model_answer": row.get(f"answer_{b}", ""),
            "F1": row.get(f"F1_{b}", ""),
            "EM": row.get(f"EM_{b}", ""),
            "gold_titles": " | ".join(row.get("gold_titles") or []),
            "citation_titles": " | ".join(row.get(f"citation_titles_{b}") or []),
            "retrieved_titles": " | ".join(row.get(f"retrieved_titles_{b}") or []),
            "nli_premise_titles": " | ".join(row.get(f"nli_premise_titles_{b}") or []),
            "nli_argmax": row.get(f"nli_argmax_{b}", ""),
            "nli_entailment": row.get(f"nli_entailment_{b}", ""),
            "nli_neutral": row.get(f"nli_neutral_{b}", ""),
            "nli_contradiction": row.get(f"nli_contradiction_{b}", ""),
            "nli_truncated": row.get(f"nli_truncated_{b}", ""),
            "nli_tokens": row.get(f"nli_tokens_{b}", ""),
            "nli_fallback": row.get(f"nli_fallback_{b}", ""),
            "hypothesis": row.get(f"nli_hypothesis_{b}", ""),
            "cite_gold_hits": row.get(f"cite_gold_hits_{b}", ""),
            "human_label": "",
            "shortfall_note": notes if i == 0 else "",
        })
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)


def run_nli_on_rows(rows, args):
    scorer = make_nli_scorer(args)
    items = []
    index = []
    for row in rows:
        ex = row["_ex"]
        for branch, res_key, retrieved in (
            ("A", "_res_A", row["r1_indices"]),
            ("B", "_res_B", list(row["r1_indices"]) + list(row["r2_indices"])),
        ):
            res = row[res_key]
            premise_info = build_premise(ex, res.get("citations") or [], retrieved)
            hyp = build_hypothesis(row["question"], res.get("answer") or "")
            items.append({"premise": premise_info["premise"], "hypothesis": hyp})
            index.append((row, branch, premise_info, hyp))
    scores = scorer.score_many(items)
    nli_records = []
    for score, (row, branch, premise_info, hyp) in zip(scores, index):
        score = dict(score)
        score["max_length"] = args.nli_max_length
        rec = attach_nli_to_row(row, branch, premise_info, hyp, score)
        rec["max_length"] = args.nli_max_length
        nli_records.append(rec)

    def mean_prob(branch, lab="entailment"):
        key = f"nli_{lab}_{branch}"
        return mean(r[key] for r in rows if r.get(key) is not None)

    n = len(rows)
    n_trunc_a = sum(1 for r in rows if r.get("nli_truncated_A"))
    n_trunc_b = sum(1 for r in rows if r.get("nli_truncated_B"))
    n_fb_a = sum(1 for r in rows if r.get("nli_fallback_A"))
    n_fb_b = sum(1 for r in rows if r.get("nli_fallback_B"))
    meta = {
        "ran": True,
        "backend": args.nli_backend,
        "model": args.nli_model if args.nli_backend == "hf" else "mock-nli",
        "device_requested": args.nli_device,
        "max_length": args.nli_max_length,
        "batch_size": args.nli_batch_size,
        "hypothesis_template": HYPOTHESIS_TEMPLATE,
        "scores_are_fake": args.nli_backend == "mock",
        "mean_entailment_A": mean_prob("A"),
        "mean_entailment_B": mean_prob("B"),
        "mean_neutral_A": mean_prob("A", "neutral"),
        "mean_neutral_B": mean_prob("B", "neutral"),
        "mean_contradiction_A": mean_prob("A", "contradiction"),
        "mean_contradiction_B": mean_prob("B", "contradiction"),
        "n_truncated_A": n_trunc_a,
        "n_truncated_B": n_trunc_b,
        "n_truncated": n_trunc_a + n_trunc_b,
        "n_fallback_A": n_fb_a,
        "n_fallback_B": n_fb_b,
        "n_pairs": 2 * n,
    }
    return nli_records, meta


def rows_from_branch_records(branch_records, examples_by_id, tie_eps):
    rows = []
    missing = []
    for rec in branch_records:
        qid = rec.get("_id")
        ex = examples_by_id.get(qid)
        if ex is None:
            missing.append(qid)
            continue
        r1 = rec.get("r1_indices") or rec.get("A", {}).get("paragraph_indices") or []
        r2 = rec.get("r2_indices") or []
        res_a = rec["A"]
        res_b = rec["B"]
        row = build_question_row(ex, r1, r2, res_a, res_b, tie_eps)
        row["from_cache_A"] = res_a.get("from_cache", row["from_cache_A"])
        row["from_cache_B"] = res_b.get("from_cache", row["from_cache_B"])
        rows.append(row)
    if missing:
        die(f"--nli-only: {len(missing)} ids in branches.jsonl were not in --data (e.g. {missing[:3]})")
    return rows


def branch_record_from_row(row):
    rec = {
        "_id": row["_id"],
        "question": row["question"],
        "gold_answer": row["gold_answer"],
        "type": row.get("type"),
        "level": row.get("level"),
        "gold_titles": row.get("gold_titles"),
        "r1_indices": list(row["r1_indices"]),
        "r2_indices": list(row["r2_indices"]),
        "A": {k: v for k, v in row["_res_A"].items() if k != "token_logprobs"},
        "B": {k: v for k, v in row["_res_B"].items() if k != "token_logprobs"},
        "delta": row["delta"],
        "delta_class": row["delta_class"],
        "oracle_branch": row["oracle_branch"],
        "oracle_F1": row["oracle_F1"],
        "oracle_minus_A": row["oracle_minus_A"],
        "r1_recall": row["r1_recall"],
        "r1_both_gold": row["r1_both_gold"],
        "r2_recall": row["r2_recall"],
        "r2_both_gold": row["r2_both_gold"],
        "cite_recall_A": row["cite_recall_A"],
        "cite_recall_B": row["cite_recall_B"],
        "official_sp_f1_A": row["official_sp_f1_A"],
        "official_sp_f1_B": row["official_sp_f1_B"],
    }
    if row.get("nli_argmax_A"):
        rec["nli"] = {
            "A": {
                "probs": {
                    "entailment": row.get("nli_entailment_A"),
                    "neutral": row.get("nli_neutral_A"),
                    "contradiction": row.get("nli_contradiction_A"),
                },
                "argmax": row.get("nli_argmax_A"),
                "truncated": row.get("nli_truncated_A"),
                "n_tokens": row.get("nli_tokens_A"),
                "used_fallback": row.get("nli_fallback_A"),
                "premise_titles": row.get("nli_premise_titles_A"),
            },
            "B": {
                "probs": {
                    "entailment": row.get("nli_entailment_B"),
                    "neutral": row.get("nli_neutral_B"),
                    "contradiction": row.get("nli_contradiction_B"),
                },
                "argmax": row.get("nli_argmax_B"),
                "truncated": row.get("nli_truncated_B"),
                "n_tokens": row.get("nli_tokens_B"),
                "used_fallback": row.get("nli_fallback_B"),
                "premise_titles": row.get("nli_premise_titles_B"),
            },
        }
    return rec


def main(argv=None):
    args = parse_args(argv)
    if args.k < 1:
        die("--k must be >= 1")
    if args.m < 0:
        die("--m must be >= 0")
    if args.skip_nli and args.nli_only:
        die("Use only one of --skip-nli and --nli-only")

    data_path = args.data
    data = load_examples(data_path, args.n)
    examples_by_id = {ex["_id"]: ex for ex in data}

    base_url, model, key_env, allow_missing = cm.resolve_endpoint(args)
    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)
    cache_path = None if args.no_cache else (args.cache or os.path.join(out_dir, "cache.jsonl"))

    print(f"compare_models.py: {COMPARE_MODELS_SRC}")
    print(f"bm25 helpers: {getattr(cm, '_BM25_SRC', None) or 'built-in copy'}")
    print(f"data={data_path}  n={len(data)}  k={args.k}  m={args.m}")
    print(f"preset={args.preset}  model={model}  base_url={base_url or '(OpenAI default)'}")
    print(f"key: {cm.env_flag(key_env)}  out={out_dir}", flush=True)
    if args.nli_only:
        print("mode=nli-only (no new API calls)")
    elif args.skip_nli:
        print("mode=answers-only (--skip-nli)")
    else:
        print(f"mode=answers+NLI  nli-backend={args.nli_backend}")

    holder = ClientHolder(base_url, key_env, allow_missing)
    cache, source = load_merged_cache(
        cache_path, args.answer_cache, model, args.k, args.m, args.no_cache
    )
    if args.no_cache and not args.answer_cache:
        cache, source = {}, {}
        cache_path = None

    branches_path = os.path.join(out_dir, "branches.jsonl")
    rows = []
    api_calls = 0
    cache_hits = 0
    data_remaining = list(data)

    if args.nli_only and os.path.isfile(branches_path):
        existing = load_branches_jsonl(branches_path)
        by_id = {rec["_id"]: rec for rec in existing}
        ordered = [by_id[ex["_id"]] for ex in data if ex["_id"] in by_id]
        if len(ordered) < len(data):
            sys.stderr.write(
                f"[nli-only] branches.jsonl has {len(ordered)}/{len(data)} requested questions; "
                "filling the rest from cache if present.\n"
            )
        if ordered:
            rows = rows_from_branch_records(ordered, examples_by_id, args.tie_eps)
            have = {r["_id"] for r in rows}
            data_remaining = [ex for ex in data if ex["_id"] not in have]
            cache_hits = 2 * len(rows)
            api_calls = 0
        else:
            data_remaining = list(data)

    if data_remaining:
        start_index = len(rows)
        for i, ex in enumerate(data_remaining, start=start_index + 1):
            r1, r2 = cm.retrieve_indices(ex, args.k, args.m)
            idx_a = list(r1)
            idx_b = list(r1) + list(r2)
            res_a, new_a = evaluate_from_cache_or_api(
                holder, model, ex, "A", idx_a, args, cache, source, cache_path
            )
            res_b, new_b = evaluate_from_cache_or_api(
                holder, model, ex, "B", idx_b, args, cache, source, cache_path
            )
            api_calls += int(new_a) + int(new_b)
            cache_hits += int(res_a["from_cache"]) + int(res_b["from_cache"])
            row = build_question_row(ex, r1, r2, res_a, res_b, args.tie_eps)
            rows.append(row)
            print(
                f"[{i}/{len(data)}] {ex['_id']}  "
                f"F1_A={res_a['F1']:.3f} F1_B={res_b['F1']:.3f} d={row['delta']:+.3f}  "
                f"{row['delta_class']}  oracle={row['oracle_branch']}  "
                f"{'cache' if res_a['from_cache'] and res_b['from_cache'] else 'api'}"
            )

    if len(rows) != len(data):
        order = {ex["_id"]: i for i, ex in enumerate(data)}
        rows.sort(key=lambda r: order.get(r["_id"], 10**9))

    nli_records = []
    nli_meta = None
    audit_meta = None
    audit_path = os.path.join(out_dir, "audit_sample.csv")
    nli_path = os.path.join(out_dir, "nli_scores.jsonl")

    if not args.skip_nli:
        nli_records, nli_meta = run_nli_on_rows(rows, args)
        write_jsonl(nli_path, nli_records)
        selected, audit_meta = sample_audit(rows, n_target=args.audit_n, seed=args.audit_seed)
        write_audit_csv(audit_path, selected, audit_meta)
        if audit_meta["notes"]:
            sys.stderr.write("[audit] " + " | ".join(audit_meta["notes"]) + "\n")
        print(f"wrote {nli_path}")
        print(f"wrote {audit_path}  ({audit_meta['n_selected']} rows)")
    else:
        write_audit_csv(
            audit_path,
            [],
            {"notes": ["NLI was not run (--skip-nli); audit sample is empty."]},
        )
        print(f"wrote {audit_path}  (empty: --skip-nli)")

    summary = collect_quality(
        rows,
        args,
        data_path,
        model,
        base_url,
        key_env,
        out_dir,
        cache_hits,
        api_calls,
        nli_ran=not args.skip_nli,
        nli_meta=nli_meta,
        audit_meta=audit_meta,
    )

    csv_path = os.path.join(out_dir, "per_question.csv")
    write_csv(csv_path, rows)

    branch_records = [branch_record_from_row(r) for r in rows]
    write_jsonl(branches_path, branch_records)

    summary_path = os.path.join(out_dir, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(json_safe(summary), f, indent=2, ensure_ascii=False)

    print_quality_table(summary)
    print_gonogo_table(summary)
    print(f"wrote {csv_path}")
    print(f"wrote {branches_path}")
    print(f"wrote {summary_path}")
    if cache_path:
        print(f"cache {cache_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

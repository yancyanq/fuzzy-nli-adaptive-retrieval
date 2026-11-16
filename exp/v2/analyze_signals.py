#!/usr/bin/env python3
"""Offline diagnostic: can round-1 NLI / logprob separate improved vs tie?

Reads an existing Step 5 per_question.csv. Does not call any API, does not
run NLI, and does not choose a gate threshold. Pilot numbers are descriptive
only; gate parameters stay reserved for the tune set.

Usage (on YangQS, after Step 5):
    python analyze_signals.py --dir step5_pilot
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import sys


CLASSES = ("improved", "tie", "degraded")
# Features the gate could actually use at decision time (branch A only).
SIGNALS = (
    ("nli_entailment_A", "higher = more confident the first-round evidence supports the answer"),
    ("mean_logprob_A", "higher (closer to 0) = more confident generation"),
    ("min_logprob_A", "higher (closer to 0) = no very-low-probability token"),
)
# For AUC, the score must be oriented so that a *higher* value is meant to
# flag the positive class (improved = worth re-retrieving). Low entailment
# or low logprob is the expected direction, so we flip the sign.
AUC_ORIENTATION = {
    "nli_entailment_A": -1.0,
    "mean_logprob_A": -1.0,
    "min_logprob_A": -1.0,
}


def die(msg, code=2):
    sys.stderr.write(msg + "\n")
    raise SystemExit(code)


def to_float(v):
    if v is None:
        return None
    if isinstance(v, float):
        return None if math.isnan(v) else v
    s = str(v).strip()
    if s == "" or s.lower() in {"nan", "none", "null"}:
        return None
    try:
        x = float(s)
    except ValueError:
        return None
    return None if math.isnan(x) else x


def load_rows(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        die(f"no rows in {path}")
    need = {"delta_class", "nli_entailment_A"}
    missing = [c for c in need if c not in rows[0]]
    if missing:
        die(f"{path} is missing columns {missing}. Use Step 5 per_question.csv after NLI.")
    return rows


def group_by_class(rows):
    bags = {c: [] for c in CLASSES}
    other = 0
    for r in rows:
        k = (r.get("delta_class") or "").strip().lower()
        if k in bags:
            bags[k].append(r)
        else:
            other += 1
    return bags, other


def values(rows, col):
    out = []
    for r in rows:
        x = to_float(r.get(col))
        if x is not None:
            out.append(x)
    return out


def summarize_numeric(xs):
    xs = list(xs)
    n = len(xs)
    if n == 0:
        return {"n": 0, "mean": None, "std": None, "min": None,
                "q25": None, "median": None, "q75": None, "max": None}
    xs_sorted = sorted(xs)
    def pct(p):
        if n == 1:
            return xs_sorted[0]
        i = p * (n - 1)
        lo = int(math.floor(i))
        hi = int(math.ceil(i))
        if lo == hi:
            return xs_sorted[lo]
        w = i - lo
        return xs_sorted[lo] * (1 - w) + xs_sorted[hi] * w
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / n  # population; n is small
    return {
        "n": n,
        "mean": mean,
        "std": math.sqrt(var) if n else None,
        "min": xs_sorted[0],
        "q25": pct(0.25),
        "median": pct(0.50),
        "q75": pct(0.75),
        "max": xs_sorted[-1],
    }


def auc_score(pos, neg):
    """AUC = P(pos > neg) + 0.5 P(pos == neg). 0.5 is chance, 1 is perfect.

    `pos` and `neg` are already oriented (higher = more likely positive).
    """
    pos = list(pos)
    neg = list(neg)
    if not pos or not neg:
        return None
    # Mann-Whitney U / (n_pos * n_neg)
    # Sort all with labels; ties contribute 0.5
    pairs = [(x, 1) for x in pos] + [(y, 0) for y in neg]
    pairs.sort(key=lambda t: t[0])
    n_pos, n_neg = len(pos), len(neg)
    rank_sum = 0.0
    i = 0
    n = len(pairs)
    while i < n:
        j = i
        while j < n and pairs[j][0] == pairs[i][0]:
            j += 1
        # midrank for ties
        mid = 0.5 * (i + 1 + j)
        for k in range(i, j):
            if pairs[k][1] == 1:
                rank_sum += mid
        i = j
    u = rank_sum - n_pos * (n_pos + 1) / 2.0
    return u / (n_pos * n_neg)


def mean_diff(a, b):
    if not a or not b:
        return None
    return (sum(a) / len(a)) - (sum(b) / len(b))


def bootstrap_ci(pos, neg, fn, n_boot=5000, seed=42, alpha=0.05):
    """Bootstrap CI for fn(pos, neg). Returns (lo, hi) or (None, None)."""
    if not pos or not neg:
        return None, None
    rng = random.Random(seed)
    stats = []
    n_p, n_n = len(pos), len(neg)
    for _ in range(n_boot):
        p = [pos[rng.randrange(n_p)] for _ in range(n_p)]
        n = [neg[rng.randrange(n_n)] for _ in range(n_n)]
        v = fn(p, n)
        if v is not None and v == v:
            stats.append(v)
    if not stats:
        return None, None
    stats.sort()
    def pct(p):
        i = p * (len(stats) - 1)
        lo = int(math.floor(i))
        hi = int(math.ceil(i))
        if lo == hi:
            return stats[lo]
        w = i - lo
        return stats[lo] * (1 - w) + stats[hi] * w
    return pct(alpha / 2), pct(1 - alpha / 2)


def fmt(x, d=3):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x:.{d}f}"


def illustrative_thresholds(pos_raw, neg_raw, thresholds):
    """pos_raw / neg_raw are raw entailment (NOT flipped).

    A rule 're-retrieve if entailment_A < t' is shown only to describe the
    distribution. These thresholds are not selected and must not be reused
    as the gate.
    """
    out = []
    n_pos, n_neg = len(pos_raw), len(neg_raw)
    for t in thresholds:
        tp = sum(1 for x in pos_raw if x < t)
        fp = sum(1 for x in neg_raw if x < t)
        fn = n_pos - tp
        tn = n_neg - fp
        prec = tp / (tp + fp) if (tp + fp) else None
        rec = tp / n_pos if n_pos else None
        out.append({
            "rule": f"re-retrieve if nli_entailment_A < {t}",
            "threshold": t,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision_on_improved": prec,
            "recall_of_improved": rec,
        })
    return out


def analyze(rows, bootstrap_samples=5000, bootstrap_seed=42):
    bags, other = group_by_class(rows)
    counts = {c: len(bags[c]) for c in CLASSES}
    by_class = {}
    signals = {}
    for col, meaning in SIGNALS:
        class_stats = {}
        raw = {}
        for c in CLASSES:
            xs = values(bags[c], col)
            raw[c] = xs
            class_stats[c] = summarize_numeric(xs)
        pos = raw["improved"]
        neg = raw["tie"]  # primary contrast; degraded is reported separately
        orient = AUC_ORIENTATION[col]
        pos_o = [orient * x for x in pos]
        neg_o = [orient * x for x in neg]
        auc = auc_score(pos_o, neg_o)
        auc_lo, auc_hi = bootstrap_ci(
            pos_o, neg_o, auc_score,
            n_boot=bootstrap_samples, seed=bootstrap_seed,
        )
        diff = mean_diff(pos, neg)  # improved minus tie, on the raw scale
        diff_lo, diff_hi = bootstrap_ci(
            pos, neg, mean_diff,
            n_boot=bootstrap_samples, seed=bootstrap_seed,
        )
        signals[col] = {
            "meaning": meaning,
            "auc_orientation": (
                "score used for AUC is -" + col + " "
                "(low raw value → more likely improved / re-retrieve)"
            ),
            "auc_improved_vs_tie": auc,
            "auc_ci95": [auc_lo, auc_hi],
            "mean_improved_minus_tie": diff,
            "mean_diff_ci95": [diff_lo, diff_hi],
            "n_improved_with_value": len(pos),
            "n_tie_with_value": len(neg),
            "n_degraded_with_value": len(raw["degraded"]),
            "by_class": class_stats,
        }
    entail_pos = values(bags["improved"], "nli_entailment_A")
    entail_neg = values(bags["tie"], "nli_entailment_A")
    thresholds = (0.50, 0.80, 0.90, 0.95)
    return {
        "n": len(rows),
        "n_by_class": counts,
        "n_unclassified": other,
        "note": (
            "Diagnostic only. No gate threshold is chosen here. "
            "AUC is computed on improved vs tie, with low round-1 "
            "entailment / logprob treated as the signal to re-retrieve. "
            "0.5 is chance-level. Degraded questions are summarised but "
            "are not part of the AUC contrast (too few in the pilot). "
            "Do not tune the gate on these pilot numbers; use tune.json."
        ),
        "signals": signals,
        "illustrative_entailment_thresholds": illustrative_thresholds(
            entail_pos, entail_neg, thresholds
        ),
        "bootstrap_samples": bootstrap_samples,
        "bootstrap_seed": bootstrap_seed,
    }


def print_report(summary):
    c = summary["n_by_class"]
    print()
    print(f"n={summary['n']}   improved={c['improved']}  tie={c['tie']}  degraded={c['degraded']}")
    print("Diagnostic only — no gate threshold is selected. Tuning stays on tune.json.")
    print()
    print(f"{'signal (branch A)':22} {'imp mean':>10} {'tie mean':>10} {'diff':>10} {'AUC':>8}  95% CI")
    print("-" * 78)
    for col, _ in SIGNALS:
        s = summary["signals"][col]
        imp = s["by_class"]["improved"]["mean"]
        tie = s["by_class"]["tie"]["mean"]
        auc = s["auc_improved_vs_tie"]
        lo, hi = s["auc_ci95"]
        print(
            f"{col:22} {fmt(imp):>10} {fmt(tie):>10} {fmt(s['mean_improved_minus_tie']):>10} "
            f"{fmt(auc):>8}  [{fmt(lo)}, {fmt(hi)}]"
        )
    print()
    print("AUC: 0.5 = no better than chance; >0.5 means lower A-signal tends to mark improved questions.")
    print()
    print("Illustrative rules (NOT a chosen gate): re-retrieve if nli_entailment_A < t")
    print(f"{'t':>8} {'recall_imp':>12} {'prec_imp':>10} {'tp':>5} {'fp':>5} {'fn':>5} {'tn':>5}")
    for row in summary["illustrative_entailment_thresholds"]:
        print(
            f"{row['threshold']:8.2f} {fmt(row['recall_of_improved']):>12} "
            f"{fmt(row['precision_on_improved']):>10} {row['tp']:5d} {row['fp']:5d} "
            f"{row['fn']:5d} {row['tn']:5d}"
        )
    print()
    print(summary["note"])
    print()


def write_class_csv(path, summary):
    fields = ["signal", "class", "n", "mean", "std", "min", "q25", "median", "q75", "max"]
    rows = []
    for col, _ in SIGNALS:
        for c in CLASSES:
            st = summary["signals"][col]["by_class"][c]
            rows.append({"signal": col, "class": c, **st})
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Offline improved-vs-tie signal diagnostic")
    ap.add_argument("--dir", default="step5_pilot", help="Folder with per_question.csv")
    ap.add_argument("--csv", default=None, help="Override path to per_question.csv")
    ap.add_argument("--out", default=None, help="Output folder (default: same as --dir)")
    ap.add_argument("--bootstrap-samples", type=int, default=5000)
    ap.add_argument("--bootstrap-seed", type=int, default=42)
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    csv_path = args.csv or os.path.join(args.dir, "per_question.csv")
    if not os.path.isfile(csv_path):
        die(f"missing {csv_path}")
    out_dir = args.out or args.dir
    os.makedirs(out_dir, exist_ok=True)
    rows = load_rows(csv_path)
    summary = analyze(rows, args.bootstrap_samples, args.bootstrap_seed)
    summary["source_csv"] = os.path.abspath(csv_path)
    print_report(summary)
    jpath = os.path.join(out_dir, "signal_summary.json")
    cpath = os.path.join(out_dir, "signal_by_class.csv")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    write_class_csv(cpath, summary)
    print(f"wrote {jpath}")
    print(f"wrote {cpath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

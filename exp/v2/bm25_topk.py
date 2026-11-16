"""Step 2: BM25 top-k recall on HotpotQA distractor (official JSON format).

Usage:
  python bm25_topk.py --data pilot.json --ks 2 3 4 --m 1 --out step2_results

Round 1: BM25 over the question's own context paragraphs (title + sentences), query = question.
Round 2 (rule-based rewrite): query = question + title and first sentence of the top-1
round-1 paragraph; rank only paragraphs NOT used in round 1; add top-m of them.
Gold paragraphs = titles appearing in supporting_facts.
"""
import argparse, json, os, re, csv, random
from rank_bm25 import BM25Okapi

STOP = set("a an the of in on at to for and or is are was were be been by with from as that this which who whom what when where how did does do it its his her their they he she".split())

def tok(s):
    return [w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in STOP]

def para_text(title, sents):
    return title + " " + " ".join(sents)

def run(data, ks, m):
    rows = []
    for ex in data:
        titles = [c[0] for c in ex["context"]]
        texts = [para_text(c[0], c[1]) for c in ex["context"]]
        gold = set(t for t, _ in ex["supporting_facts"]) & set(titles)
        bm = BM25Okapi([tok(t) for t in texts])
        scores = bm.get_scores(tok(ex["question"]))
        order = sorted(range(len(texts)), key=lambda i: -scores[i])
        for k in ks:
            k_eff = min(k, len(texts))
            r1 = order[:k_eff]
            hit1 = len(gold & {titles[i] for i in r1})
            # round 2
            top = ex["context"][order[0]]
            q2 = ex["question"] + " " + top[0] + " " + (top[1][0] if top[1] else "")
            unused = [i for i in range(len(texts)) if i not in r1]
            r2 = []
            if unused:
                bm2 = BM25Okapi([tok(texts[i]) for i in unused])
                s2 = bm2.get_scores(tok(q2))
                r2 = [unused[j] for j in sorted(range(len(unused)), key=lambda j: -s2[j])[:m]]
            hit2 = len(gold & {titles[i] for i in r1 + r2})
            rows.append(dict(_id=ex["_id"], k=k, n_paras=len(texts), n_gold=len(gold),
                             r1_hits=hit1, r2_hits=hit2, n_unused=len(unused)))
    return rows

def summarize(rows, ks):
    out = []
    for k in ks:
        R = [r for r in rows if r["k"] == k and r["n_gold"] > 0]
        n = len(R)
        def frac(f): return sum(1 for r in R if f(r)) / n if n else float("nan")
        out.append(dict(
            k=k, n=n,
            r1_recall=sum(r["r1_hits"] / r["n_gold"] for r in R) / n,
            r1_all_gold=frac(lambda r: r["r1_hits"] == r["n_gold"]),
            r1_any_gold=frac(lambda r: r["r1_hits"] > 0),
            r2_recall=sum(r["r2_hits"] / r["n_gold"] for r in R) / n,
            r2_all_gold=frac(lambda r: r["r2_hits"] == r["n_gold"]),
            r2_gain_questions=frac(lambda r: r["r2_hits"] > r["r1_hits"]),
            no_unused=frac(lambda r: r["n_unused"] == 0),
        ))
    return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--ks", type=int, nargs="+", default=[2, 3, 4])
    ap.add_argument("--m", type=int, default=1, help="paragraphs added in round 2")
    ap.add_argument("--out", default="step2_results")
    a = ap.parse_args()
    data = json.load(open(a.data, encoding="utf-8"))
    os.makedirs(a.out, exist_ok=True)
    rows = run(data, a.ks, a.m)
    with open(os.path.join(a.out, "per_question.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    summ = summarize(rows, a.ks)
    with open(os.path.join(a.out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(dict(data=a.data, n_questions=len(data), m=a.m, results=summ), f, indent=2)
    print(f"data={a.data}  questions={len(data)}  round2 adds m={a.m}")
    print(f"{'k':>2} {'R1 recall':>10} {'R1 both':>8} {'R2 recall':>10} {'R2 both':>8} {'R2 gain%':>9} {'no unused%':>10}")
    for s in summ:
        print(f"{s['k']:>2} {s['r1_recall']:>10.3f} {s['r1_all_gold']:>8.3f} {s['r2_recall']:>10.3f} {s['r2_all_gold']:>8.3f} {s['r2_gain_questions']*100:>8.1f}% {s['no_unused']*100:>9.1f}%")

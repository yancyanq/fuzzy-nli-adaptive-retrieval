#!/usr/bin/env python3
"""Merge NLI premises into audit_sample.csv and pre-fill rule-based hints.

Hints are aids for the human annotator only; human_label must still be filled
by a person. Reads: audit_sample.csv, nli_scores.jsonl (same folder).
Writes: audit_review.csv (UTF-8 with BOM, opens in Excel).

Usage:  python audit_helper.py --dir step5_pilot
"""
import argparse, csv, json, os, re, string, sys


def norm(s):
    s = (s or "").lower()
    s = "".join(ch for ch in s if ch not in set(string.punctuation))
    s = re.sub(r"\b(a|an|the)\b", " ", s)
    return " ".join(s.split())


def load_nli(path):
    table = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            table[(str(rec.get("_id")), str(rec.get("branch")).upper())] = rec
    return table


def hints(row, premise):
    gold = norm(row.get("gold_answer"))
    pred = norm(row.get("model_answer"))
    prem = norm(premise)
    gold_titles = [t.strip() for t in (row.get("gold_titles") or "").split("|") if t.strip()]
    prem_titles = set(t.strip() for t in (row.get("nli_premise_titles") or "").split("|") if t.strip())
    out = {}
    out["hint_yes_no_question"] = "yes" if gold in ("yes", "no") else "no"
    if not pred:
        rel = "empty_answer"
    elif pred == gold:
        rel = "exact"
    elif gold and (gold in pred or pred in gold):
        rel = "substring (possible alias / extra words)"
    else:
        rel = "different"
    out["hint_answer_vs_gold"] = rel
    out["hint_answer_in_premise"] = "yes" if pred and pred in prem else "no"
    out["hint_gold_answer_in_premise"] = "yes" if gold and gold not in ("yes", "no") and gold in prem else ("n/a" if gold in ("yes", "no") else "no")
    n_gold_in = sum(1 for t in gold_titles if t in prem_titles)
    out["hint_gold_titles_in_premise"] = f"{n_gold_in}/{len(gold_titles)}"
    # Suggested checks (not labels)
    s = []
    if rel.startswith("substring"):
        s.append("F1 may understate correctness: check alias -> maybe nli_correct")
    if out["hint_yes_no_question"] == "yes":
        s.append("yes/no question: check hypothesis wording -> maybe nli_wrong_hypothesis")
    if n_gold_in == len(gold_titles) and gold_titles and row.get("nli_argmax") != "entailment":
        s.append("both gold paragraphs present but not entailment -> check multi-hop")
    if out["hint_answer_in_premise"] == "yes" and rel == "different" and row.get("nli_argmax") == "entailment":
        s.append("wrong answer string appears in premise -> check lexical overlap")
    out["hint_suggested_check"] = "; ".join(s)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="step5_pilot")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    audit_p = os.path.join(a.dir, "audit_sample.csv")
    nli_p = os.path.join(a.dir, "nli_scores.jsonl")
    for p in (audit_p, nli_p):
        if not os.path.isfile(p):
            sys.exit(f"missing file: {p}")
    nli = load_nli(nli_p)
    with open(audit_p, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out_rows, missing = [], 0
    for r in rows:
        rec = nli.get((str(r["_id"]), str(r["branch"]).upper()))
        premise = (rec or {}).get("premise", "")
        if rec is None:
            missing += 1
        if not r.get("hypothesis") and rec:
            r["hypothesis"] = rec.get("hypothesis", "")
        new = {
            "_id": r["_id"], "branch": r["branch"], "error_type": r["error_type"],
            "question": r["question"], "gold_answer": r["gold_answer"], "model_answer": r["model_answer"],
            "F1": r["F1"], "EM": r["EM"], "nli_argmax": r["nli_argmax"], "nli_entailment": r["nli_entailment"],
            "hypothesis": r["hypothesis"], "premise": premise,
            "gold_titles": r["gold_titles"], "nli_premise_titles": r["nli_premise_titles"],
        }
        new.update(hints(r, premise))
        new["human_answer_correct"] = ""
        new["human_premise_supports"] = ""
        new["human_label"] = ""
        new["note"] = ""
        out_rows.append(new)
    out_p = a.out or os.path.join(a.dir, "audit_review.csv")
    with open(out_p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()) if out_rows else ["_id"])
        w.writeheader(); w.writerows(out_rows)
    print(f"wrote {out_p}  rows={len(out_rows)}  missing_premise={missing}")
    print("Hints are aids only; fill human_answer_correct / human_premise_supports / human_label / note by hand.")


if __name__ == "__main__":
    main()

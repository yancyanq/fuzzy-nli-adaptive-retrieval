"""Offline analysis for V2 step 6. Run from the project directory."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path

import analyze_signals
import compare_models as cm
import generate_test_v2 as gen
from run_pilot import paired_bootstrap_mean_ci

CONTRASTS = (
    ("fuzzy", "crisp"),
    ("fuzzy", "nli_only"),
    ("fuzzy", "never"),
    ("oracle", "never"),
    ("full", "fuzzy"),
)
STRATA = {"missed_improved": 5, "triggered_degraded": 5, "missing_hop_candidate": 4,
          "wrong_citation_candidate": 4, "joint_support_candidate": 4}


def branch_rows(path, question_ids):
    result = {}
    with path.open(encoding="utf-8") as stream:
        for row in map(json.loads, stream):
            key = row["_id"], row["branch"]
            if key in result or row["model"] != gen.MODEL:
                raise ValueError(f"Duplicate branch or incompatible model in {path.name}: {key!r}")
            result[key] = row
    if result.keys() != {(qid, branch) for qid in question_ids for branch in ("A", "B", "full")}:
        raise ValueError(f"Incomplete branch coverage in {path}")
    return result


def contrasts(rows, n_boot=10_000):
    result = []
    for left, right in CONTRASTS:
        differences = [analyze_signals.to_float(row[left + "_f1"]) - analyze_signals.to_float(row[right + "_f1"]) for row in rows]
        point, lo, hi = paired_bootstrap_mean_ci(differences, n_boot=n_boot, seed=42, alpha=.05)
        result.append({"left": left, "right": right, "estimate": point, "lower": lo, "upper": hi})
    return result


def cited_indices(answer):
    return list(dict.fromkeys(answer["paragraph_indices"][num-1] for num in answer["citations"]))


def case_record(question, row, a, b, sp_a, sp_b):
    context = question["context"]
    gold = set(title for title, _ in question["supporting_facts"])
    gold_sentences = [{"title": title, "index": i, "text": dict(context)[title][i]}
                      for title, i in question["supporting_facts"]]
    result = {"_id": question["_id"], "question": question["question"], "gold": question["answer"],
              "gold_sentences": gold_sentences, "delta": float(row["delta_f1"]),
              "fuzzy_branch": row["fuzzy_branch"], "crisp_branch": row["crisp_branch"],
              "bridge_absent": row["bridge_absent"], "A_nli_truncated": row["nli_truncated_A"] == "True",
              "A_nli_fallback": row["nli_fallback_A"] == "True"}
    for branch, answer, sp in (("A", a, sp_a), ("B", b, sp_b)):
        name = "never" if branch == "A" else "always"
        cited = cited_indices(answer)
        retrieved = answer["paragraph_indices"]
        result[branch] = {"answer": answer["answer"], "answer_f1": float(row[name + "_f1"]),
                          "em": float(row[name + "_em"]), "entailment": float(row["entailment_" + branch]),
                          "retrieved_titles": [context[i][0] for i in retrieved],
                          "cited_titles": [context[i][0] for i in cited],
                          "retrieved_gold_count": len(gold & {context[i][0] for i in retrieved}),
                          "cited_gold_count": len(gold & {context[i][0] for i in cited}),
                          "nli_premise_paragraphs": [context[i] for i in (cited or retrieved)],
                          "selected_support": sp["sp"]}
    return result


def sample_audit(questions, rows, answers, evidence):
    eligible = {name: [] for name in STRATA}
    coverage = {name: Counter() for name in ("missed_improved", "triggered_degraded", "all")}
    overlap = Counter()
    for ex, row in zip(questions, rows, strict=True):
        qid = ex["_id"]
        if qid != row["_id"]:
            raise ValueError("Questions and score rows must be aligned")
        a, b = (answers[qid, branch] for branch in ("A", "B"))
        delta = float(row["always_f1"]) - float(row["never_f1"])
        if not math.isclose(delta, float(row["delta_f1"]), abs_tol=1e-12) or cm.classify_delta(delta, 0) != row["delta_class"]:
            raise ValueError(f"Inconsistent paired score on {qid}")
        subset = ["all"]
        if delta > 0 and row["fuzzy_branch"] == "A":
            subset.append("missed_improved")
        if delta < 0 and row["fuzzy_branch"] == "B":
            subset.append("triggered_degraded")
        context = ex["context"]
        gold = {title for title, _ in ex["supporting_facts"]}
        cited = cited_indices(a)
        covered = len(gold & {context[i][0] for i in cited})
        a_retrieved = {context[i][0] for i in a["paragraph_indices"]}
        b_retrieved = {context[i][0] for i in b["paragraph_indices"]}
        for name in subset:
            coverage[name].update({
                "n": 1, "retrieved_both_A": len(gold) == 2 and gold <= a_retrieved,
                "retrieved_both_B": len(gold) == 2 and gold <= b_retrieved,
                "added_gold_title": bool(gold & (b_retrieved - a_retrieved)),
                "cited_zero_gold_A": covered == 0, "cited_one_gold_A": covered == 1,
                "cited_both_gold_A": len(gold) == 2 and covered == 2,
            })
        for name in subset[1:]:
            eligible[name].append(ex)
        if cited and len(gold) == 2:
            if covered == 1:
                eligible["missing_hop_candidate"].append(ex)
            if covered == 0:
                eligible["wrong_citation_candidate"].append(ex)
            if covered == 2 and float(row["never_em"]) == 1.0:
                eligible["joint_support_candidate"].append(ex)
        overlap[(row["fuzzy_branch"], row["crisp_branch"])] += 1

    indexed = {row["_id"]: row for row in rows}
    sample = {}
    for stratum, examples in eligible.items():
        selected = gen.stable_sample(sorted(examples, key=lambda ex: ex["_id"]), STRATA[stratum])
        sample[stratum] = {"eligible": len(examples), "cases": [
            case_record(ex, indexed[ex["_id"]], answers[ex["_id"], "A"], answers[ex["_id"], "B"],
                        evidence[ex["_id"], "A"], evidence[ex["_id"], "B"]) for ex in selected
        ]}
    return sample, coverage, {"/".join(key): n for key, n in sorted(overlap.items())}


def cost_figure(path, quality, latency):
    from reportlab.lib.colors import HexColor, black
    from reportlab.pdfgen import canvas

    fig = canvas.Canvas(str(path), pagesize=(504, 169), invariant=1)
    fig.setTitle("Held-out HotpotQA answer quality and measured cost")
    oracle = 100 * quality["methods"]["oracle"]["f1"]
    colors = {"fuzzy": "#A53D23", "full": "#2C648A"}
    points = {"never": "1", "always": "2", "nli_only": "3", "crisp": "4", "fuzzy": "5", "full": "6"}
    offset = {
        "never": (4, -1), "always": (-9, 4), "nli_only": (-9, -10),
        "crisp": (-10, 4), "fuzzy": (4, 4), "full": (4, 3),
    }
    axes = [
        (0, 105, [0, 25, 50, 75, 100], "Extra retrieval (%)",
         lambda key: 100 * quality["methods"][key]["retrieval_rate"]),
        (18, 26, [18, 20, 22, 24, 26], "Mean latency (s)",
         lambda key: latency["methods"][key]["seconds_mean"]),
        (600, 2050, [600, 1000, 1400, 1800], "Mean LLM tokens",
         lambda key: latency["methods"][key]["prompt_tokens_mean"] + latency["methods"][key]["completion_tokens_mean"]),
    ]
    for panel, (lo, hi, ticks, xlabel, value) in enumerate(axes):
        x, y, width, height = 44 + panel * 159, 48, 123, 101
        def xp(v):
            return x + width * (v-lo)/(hi-lo)
        def yp(v):
            return y + height * (v-48)/18
        fig.setFont("Helvetica", 8)
        fig.setLineWidth(.45)
        for t in (50,55,60,65):
            fig.setStrokeColor(HexColor("#D4D9DD"))
            fig.line(x, yp(t), x+width, yp(t))
            if panel == 0:
                fig.setFillColor(black)
                fig.drawRightString(x-5, yp(t)-2.5, str(t))
        fig.setStrokeColor(black)
        fig.line(x,y,x+width,y)
        fig.line(x,y,x,y+height)
        fig.setDash(3, 2)
        fig.setStrokeColor(HexColor("#68717A"))
        fig.line(x,yp(oracle),x+width,yp(oracle))
        fig.setDash()
        for t in ticks:
            fig.setFillColor(black)
            fig.line(xp(t),y,xp(t),y-3)
            fig.drawCentredString(xp(t), y-13, str(t))
        fig.drawCentredString(x+width/2,y-25,xlabel)
        for key, number in points.items():
            fig.setFillColor(HexColor(colors.get(key, "#243342")))
            px, py = xp(value(key)), yp(100*quality["methods"][key]["f1"])
            fig.circle(px,py,2.1,stroke=0,fill=1)
            dx, dy = offset[key]
            fig.drawString(px+dx,py+dy,number)
    fig.setFillColor(black)
    fig.saveState()
    fig.translate(15, 99)
    fig.rotate(90)
    fig.drawCentredString(0,0,"Answer F1 (%)")
    fig.restoreState()
    fig.setFont("Helvetica", 8)
    fig.drawCentredString(252,7,"1 Never    2 Always    3 NLI threshold    4 Crisp    5 Fuzzy    6 Full-context")
    fig.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", type=Path, default=Path("test.json"))
    parser.add_argument("--results", type=Path, default=Path("step5_v2"))
    parser.add_argument("--out", type=Path, default=Path("step6_v2"))
    args = parser.parse_args()
    q = gen.load_test(args.test)
    ids = {ex["_id"] for ex in q}
    with (args.results / "per_question.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    per_question = {row["_id"]: row for row in rows}
    if len(rows) != len(ids) or per_question.keys() != ids:
        raise ValueError("Need one score row per ID in test.json")
    rows = [per_question[ex["_id"]] for ex in q]
    quality = gen.read_json(args.results / "quality_summary.json")
    latency = gen.read_json(args.results / "latency_summary.json")
    answers = branch_rows(args.results / "answers_test_v2.jsonl", ids)
    evidence = branch_rows(args.results / "evidence_test_v2.jsonl", ids)
    audit, coverage, overlap = sample_audit(q, rows, answers, evidence)
    result = {
        "n": len(q), "bootstrap": {"unit": "question", "replicates": 10000, "seed": 42, "level": .95},
        "contrasts": contrasts(rows), "changes_vs_never": {
            method: dict(Counter(cm.classify_delta(float(row[method+"_f1"]) - float(row["never_f1"]), 0)
                                 for row in rows)) for method in quality["methods"]},
        "exploratory": {"coverage": coverage, "fuzzy_crisp_branch_counts": overlap,
                        "audit_strata_sizes": {name: {"eligible": s["eligible"], "sampled": len(s["cases"])}
                                              for name, s in audit.items()},
                        "unique_sample_ids": len({case["_id"] for group in audit.values() for case in group["cases"]})},
        "inputs_sha256": {name: gen.sha256(args.results / name) for name in
                           ("per_question.csv", "quality_summary.json", "latency_summary.json",
                            "answers_test_v2.jsonl", "evidence_test_v2.jsonl")},
    }
    args.out.mkdir(parents=True, exist_ok=True)
    gen.write_json(args.out / "step6_summary.json", result)
    gen.write_json(args.out / "error_audit_cases.json", audit)
    with (args.out / "paired_bootstrap.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("left","right","estimate","lower","upper"))
        writer.writeheader()
        writer.writerows(result["contrasts"])
    cost_figure(args.out / "quality_cost.pdf", quality, latency)


if __name__ == "__main__":
    main()

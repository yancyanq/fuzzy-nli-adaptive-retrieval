"""Evaluate P2 cached signals and paired baselines on the fixed development set."""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from statistics import correlation, mean, median, quantiles, StatisticsError
import sys

from guided import EXAMPLE_FREE, validate_wire, wire_messages
from prepare import HERE, P1, P15, V2, jsonl, stable_hash
from verify import indexed


SIGNALS = ("old_nli_risk", "old_nli_bridge", "local_r_with_fallback", "local_g_with_fallback",
           "local_combined_with_fallback", "qwen_selfcheck_with_fallback")


def csv_out(path, records):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def index(rows, expected):
    by_id = {row["qid"]: row for row in rows}
    if len(rows) != len(by_id) or set(by_id) != expected:
        raise ValueError("Incomplete or duplicate development rows")
    return by_id


def timing(values):
    return {"mean": mean(values), "p50": median(values), "p95": quantiles(values, n=100, method="inclusive")[94]}


def selection_outcome(selected, delta, a):
    count = Counter((delta[qid] > 0) - (delta[qid] < 0) for qid in selected)
    return {
        "selected": len(selected),
        "improved_selected": count[1], "tie_selected": count[0], "degraded_selected": count[-1],
        "improved_missed": sum(value > 0 for value in delta.values()) - count[1],
        "selected_delta_sum": sum(delta[qid] for qid in selected),
        "panel_f1_after_selected_b": (sum(a.values()) + sum(delta[qid] for qid in selected)) / len(a),
        "selected_ids": "|".join(selected),
    }


def score_at_budget(name, rows, delta, a, budget, seed):
    positives = [r[name] for r in rows if delta[r["qid"]] > 0]
    others = [r[name] for r in rows if delta[r["qid"]] <= 0]
    sorted_rows = sorted(rows, key=lambda r: (-r[name], stable_hash(["p2-select", seed, r["qid"]])))
    selected = [r["qid"] for r in sorted_rows[:budget]]
    return {
        "signal": name, "n": len(rows), "unique_scores": len({r[name] for r in rows}),
        "auc": mean((pos > neg) + 0.5 * (pos == neg) for pos in positives for neg in others),
        **selection_outcome(selected, delta, a),
    }


def qwen_cost(rows, task):
    return {"task": task, "calls": len(rows),
            "http_attempts": sum(len(r["attempts"]) for r in rows),
            "input_tokens_sum": sum(r["input_tokens"] for r in rows),
            "output_tokens_sum": sum(r["output_tokens"] for r in rows),
            "input_tokens_mean": mean(r["input_tokens"] for r in rows),
            "output_tokens_mean": mean(r["output_tokens"] for r in rows),
            "wall_seconds": timing([r["seconds"] for r in rows]),
            "output_limit": sum(r["finish_reason"] == "length" for r in rows)}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--raw", required=True, type=Path)
    cli.add_argument("--guided", type=Path, help="Separate rerun; direct baselines are still read from --raw")
    cli.add_argument("--example-free", type=Path, help="Independent selfcheck prompt without a worked answer")
    cli.add_argument("--out", required=True, type=Path)
    args = cli.parse_args()
    cfg = json.loads((HERE / "protocol.json").read_text())
    panel = {r["qid"]: r for r in jsonl(HERE / "input/panel.jsonl")}
    qids = set(panel)
    verification_root = args.guided or args.raw
    rel, selfcheck = [index([r for r in jsonl(verification_root / f"live-qwen/{task}.jsonl") if r["ok"]], qids)
                      for task in ("relations", "selfcheck")]
    nli = index(jsonl(verification_root / "live-nli/nli.jsonl"), qids)
    warmup = json.loads((verification_root / "live-nli/warmup.json").read_text())
    if [r["argmax"] for r in warmup["records"]] != warmup["smoke_expected_classes"]:
        raise ValueError("Pinned NLI did not pass the label-order smoke check")
    for qid, row in nli.items():
        if row["pool_sha256"] != panel[qid]["pool_sha256"] or row["a_prompt_sha256"] != panel[qid]["a_prompt_sha256"]:
            raise ValueError("Frozen A hashes do not match")
        if row["local_nli_calls"] > cfg["nli"]["local_calls_max_per_qid"] or row["relation_validation"] != rel[qid]["validation"]:
            raise ValueError("Unexpected local inference records or relation validation")
        record = row["relation_validation"]["record"] if row["relation_validation"]["ok"] else None
        if record and any(set(item["evidence_ids"]) - indexed(panel[qid]).keys() for item in record["requirements"]):
            raise ValueError("Accepted references do not resolve against the frozen panel")
        for plan in row["local_claims"]:
            for bundle in plan["bundles"]:
                if bundle["input_tokens"] > cfg["nli"]["input_tokens_max"] or bundle.get("prediction", {}).get("truncated"):
                    raise ValueError("Unexpected local NLI truncation")

    size = cfg["pool_size"]
    with (P15 / "analysis/per_question.csv").open(encoding="utf-8") as stream:
        paired = {(r["qid"], r["route"]): r for r in csv.DictReader(stream) if int(r["pool_size"]) == size}
    a = {qid: float(paired[qid, "top2"]["f1"]) for qid in sorted(qids)}
    b = {m: {qid: float(paired[qid, f"2plus{m}"]["f1"]) for qid in a} for m in (2, 4)}
    per_question = [{"qid": qid, "p15_f1_a": a[qid], "p15_f1_b2": b[2][qid], "p15_f1_b4": b[4][qid],
                     "fallback_reason": nli[qid]["fallback_reason"], **nli[qid]["signals"]} for qid in a]
    example_free_summary, signal_names = None, SIGNALS
    if args.example_free:
        example_free = index([r for r in jsonl(args.example_free / "live-qwen/selfcheck.jsonl") if r["ok"]], qids)
        signal = "qwen_selfcheck_example_free_with_fallback"
        for row in per_question:
            qid = row["qid"]
            r = example_free[qid]
            if (r["format"] != EXAMPLE_FREE or r["pool_sha256"] != panel[qid]["pool_sha256"]
                    or r["a_prompt_sha256"] != panel[qid]["a_prompt_sha256"] or r["task"] != "selfcheck"
                    or r["prompt_sha256"] != stable_hash(wire_messages(panel[qid], "selfcheck", example_free=True))
                    or r["validation"] != validate_wire(r["raw"], panel[qid], "selfcheck")):
                raise ValueError(f"Unmatched example-free selfcheck for {qid}")
            row[signal] = r["validation"].get("risk", row["old_nli_bridge"])
        signal_names = (*signal_names, signal)
        example_free_summary = {"valid": sum(r["validation"]["ok"] for r in example_free.values()),
                                "risk_counts": dict(Counter(round(3 * r["validation"]["risk"]) for r in
                                                          example_free.values() if r["validation"]["ok"])),
                                "cost": qwen_cost(list(example_free.values()), "selfcheck_example_free")}
    selected = []
    for m in (4, 2):
        delta = {qid: b[m][qid] - a[qid] for qid in a}
        for method in signal_names:
            selected.append({"m": m, **score_at_budget(method, per_question, delta, a,
                             cfg["selection_budget"], cfg["sample_and_rank_seed"])})

    sys.path.insert(0, str(V2))
    from calibrate_gates_v2 import should_retrieve
    from generate_test_v2 import load_official

    locked_nli = json.loads((V2 / "step4_dev/gates/locked_gates.json").read_text())["gates"]["nli_only"]
    threshold_selected = [qid for qid, r in sorted(nli.items()) if should_retrieve(
        locked_nli, qid, r["old_whole"]["probs"]["entailment"], None)]
    fixed_threshold = {"old_nli_risk_cutoff": -locked_nli["boundary_sort_key"][0],
                       "outcomes": [{"m": m, **selection_outcome(threshold_selected,
                            {qid: b[m][qid] - a[qid] for qid in a}, a)} for m in (4, 2)]}
    official = load_official(V2 / "step5_v2/hotpot_evaluate_v1.py")
    gold = index(jsonl(P1 / "evaluation_only/gold.jsonl"), qids)
    p15_raw = {(r["qid"], r["route"]): r["calls"][-1] for r in jsonl(P15 / "remote-evidence/results/8192/records.jsonl")
               if r["pool_size"] == size and r["ok"] and r["route"] in {"2plus2", "2plus4"}}
    direct = []
    for m in (2, 4):
        route = f"direct_2plus{m}"
        rows = index([r for r in jsonl(args.raw / f"live-qwen/{route}.jsonl") if r["ok"]], qids)
        f1, em, changed = [], [], 0
        for qid, rec in rows.items():
            (call,) = rec["calls"]
            previous = p15_raw[qid, f"2plus{m}"]
            if call["prompt_sha256"] != previous["prompt_sha256"] or call["input_tokens"] != previous["input_tokens"]:
                raise ValueError("Direct baseline differs from locked B prompt")
            f1.append(official.f1_score(call["answer"], gold[qid]["answer"])[0])
            em.append(int(official.exact_match_score(call["answer"], gold[qid]["answer"])))
            changed += int(call["answer"] != previous["answer"])
        direct.append({"route": route, "n": len(rows), "f1": mean(f1), "em": mean(em),
                       "mean_inputs": mean(r["calls"][0]["input_tokens"] for r in rows.values()),
                       "mean_outputs": mean(r["calls"][0]["output_tokens"] for r in rows.values()),
                       "elapsed_seconds": timing([r["elapsed_seconds"] for r in rows.values()]),
                       "answer_text_changed_vs_two_stage": changed, "two_stage_f1": mean(b[m].values())})

    valid = [r["validation"]["record"] for r in rel.values() if r["validation"]["ok"]]
    relations = [item for r in valid for item in r["requirements"]]
    accepted_refs = sum(len(r["evidence_ids"]) for r in relations)
    raw_invalid_refs = sum(len(r["validation"]["invalid_refs"]) for r in rel.values())
    structure_rate = len(valid) / len(qids)
    available = [n["signals"] for n in nli.values() if n["signals"]["local_r"] is not None]
    try:
        risk_gap_corr = correlation([n["local_r"] for n in available], [n["local_g"] for n in available])
    except StatisticsError:
        risk_gap_corr = None
    summary = {
        "n": len(qids), "verified_structure": len(valid), "mode": "guided" if args.guided else "initial",
        "relation_json_syntax_ok": sum(r["validation"]["syntax_ok"] for r in rel.values()),
        "raw_unresolvable_references": raw_invalid_refs,
        "wire_duplicate_refs_collapsed": sum(r["validation"].get("wire_duplicate_refs_collapsed", 0) for r in rel.values()),
        "accepted_references": accepted_refs,
        "strict_structure_validation_rate": structure_rate,
        "strict_structure_target_met": structure_rate >= cfg["human_gate"]["strict_structure_success_min"],
        "validation_errors": dict(Counter(e for r in rel.values() for e in r["validation"]["errors"])),
        "relation_count": len(relations), "relation_statuses": dict(Counter(r["status"] for r in relations)),
        "relation_uncertainty": dict(Counter(r["uncertainty"] for r in relations)),
        "fallback": dict(Counter(r["fallback_reason"] for r in nli.values() if r["fallback_reason"])),
        "qwen_selfcheck_valid": sum(r["validation"]["ok"] for r in selfcheck.values()),
        "qwen_selfcheck_risk_counts": dict(Counter(round(3 * r["validation"]["risk"]) for r in
                                                  selfcheck.values() if r["validation"]["ok"])),
        "local_r_g_pearson_when_observed": risk_gap_corr,
        "old_nli_input_tokens": sum(r["old_whole"]["actual_input_tokens"] for r in nli.values()),
        "old_nli_truncated": sum(r["old_whole"]["truncated"] for r in nli.values()),
        "old_nli_seconds": timing([r["old_whole"]["seconds"] for r in nli.values()]),
        "local_nli_calls": sum(r["local_nli_calls"] for r in nli.values()),
        "local_nli_max_observed_calls": max(r["local_nli_calls"] for r in nli.values()),
        "local_nli_input_tokens": sum(r["local_nli_input_tokens"] for r in nli.values()),
        "local_nli_max_input_tokens": max((bundle["input_tokens"] for r in nli.values()
            for plan in r["local_claims"] for bundle in plan["bundles"] if bundle["status"] == "scored"), default=0),
        "local_claim_plans": dict(Counter(plan["kind"] for r in nli.values() for plan in r["local_claims"])),
        "local_nli_seconds_including_bundling": timing([r["local_build_and_nli_seconds"] for r in nli.values()]),
        "qwen_costs": [qwen_cost(list(rel.values()), "relations"), qwen_cost(list(selfcheck.values()), "selfcheck")],
        "direct_baselines": direct, "same_budget_results": selected, "fixed_v2_nli_threshold": fixed_threshold,
        "example_free_selfcheck": example_free_summary,
        "human_review_status": "pending",
    }
    args.out.mkdir(parents=True, exist_ok=True)
    csv_out(args.out / "per_question.csv", per_question)
    csv_out(args.out / "selection_diagnostic.csv", selected)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Analyzed {len(qids)} fixed development cases and {len(selected)} budget comparisons.")


if __name__ == "__main__":
    main()

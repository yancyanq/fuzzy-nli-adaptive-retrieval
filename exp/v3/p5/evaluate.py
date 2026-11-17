"""Evaluate complete frozen P5 evidence and separate measured from replayed times."""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
from random import Random
from statistics import mean, median, quantiles
import sys

HERE = Path(__file__).resolve().parent
SCORER = HERE.parents[2] / "exp/v2/step5_v2/hotpot_evaluate_v1.py"
SCORER_SHA256 = "d35fc91a6db21d791dbdda11daf3856e9359f5701d54e3eefba20d88fecc02c0"
ROUTES = ("no_context", "top2", "top3", "top6", "full", "v2_direct_2plus1", "direct_2plus4")
POLICIES = ("full_sugeno_seed17", "full_sugeno_seed42", "full_sugeno_seed73", "consequents_only_seed42",
            "ridge", "fixed_fuzzy", "locked_v2_fuzzy", "nli_only", "crisp", "constant_mean", "qwen_selfcheck")
BUDGETS = (10, 20, 30, 50)
NATIVE = "v2_native"
PRIMARY = "full_sugeno_seed42"
METRICS = ("answer_em", "answer_f1", "sp_f1", "retrieved_gold_title_recall",
           "input_tokens", "output_tokens", "qwen_requests", "attempted_prompt_tokens", "nli_input_tokens", "nli_calls",
           "live_path_input_tokens", "live_path_output_tokens", "live_path_qwen_requests")
COST_METRICS = METRICS[4:]
PAIR_METRICS = ("answer_f1", "answer_em", "sp_f1", "input_tokens")
TIMING_METRICS = ("replay_component_seconds", "live_path_seconds")


def records(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def keyed(rows, names, expected=None):
    result = {}
    for row in rows:
        key = tuple(row[field] for field in names)
        if key in result:
            raise ValueError(f"Duplicate row at {key}")
        result[key] = row
    if expected is not None and set(result) != expected:
        missing = sorted(expected - set(result))
        extra = sorted(set(result) - expected)
        raise ValueError(f"Incomplete {names}: {len(missing)} missing {missing[:3]}, {len(extra)} extra {extra[:3]}")
    return result


def cohort(split, cfg):
    primary, secondary = split["primary_qids"], split["secondary_qids"]
    cohorts = (("primary_qids", "primary_n"), ("secondary_qids", "secondary_n"),
               ("timing_qids", "timing_n"), ("human_qids", "human_n"), ("human_dual_qids", "human_dual_n"))
    for qids, limit in cohorts:
        if len(split[qids]) != cfg[limit] or len(set(split[qids])) != cfg[limit]:
            raise ValueError(f"Frozen cohort size differs from protocol: {qids}")
    if (split["primary_size"] != cfg["primary_size"] or not set(secondary) <= set(primary)
            or not set(split["timing_qids"]) <= set(primary) or not set(split["human_qids"]) <= set(primary)
            or not set(split["human_dual_qids"]) <= set(split["human_qids"])):
        raise ValueError("Invalid P5 same-question cohort")
    return {(qid, cfg["primary_size"]) for qid in primary} | {
        (qid, size) for qid in secondary for size in cfg["secondary_sizes"]}


def policy_registry(path, protocol, cfg):
    if not path.exists():
        return [(policy, budget) for policy in POLICIES for budget in BUDGETS] + [(NATIVE, -1)]
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock["protocol_sha256"] != hashlib.sha256(protocol.read_bytes()).hexdigest():
        raise ValueError("Policy lock does not match the signed P5 protocol")
    models = lock["models"]
    regular = set(models) - {NATIVE}
    if NATIVE not in models or regular != set(lock["boundaries"]):
        raise ValueError("Policy lock does not cover all configured models")
    budgets = {str(n) for n in cfg["budgets_percent"]}
    if any(set(boundaries) != budgets for boundaries in lock["boundaries"].values()):
        raise ValueError("Policy lock does not cover all configured budgets")
    return [(method, budget) for method in models
            for budget in ([-1] if method == NATIVE else cfg["budgets_percent"])]


def load_panel(source, raw, cfg, registry):
    """Load online data only, also used by the blinded review generator."""
    split = json.loads((source / "split.json").read_text(encoding="utf-8"))
    cases = cohort(split, cfg)
    if tuple(cfg["shared_routes"]) != ROUTES or tuple(cfg["budgets_percent"]) != BUDGETS:
        raise ValueError("P5 shared routes/budget grid differs from the evaluator")
    case_key = ("qid", "pool_size")
    pools = keyed(records(source / "pools.jsonl"), case_key, cases)
    quality = keyed(records(raw / "quality.jsonl"), (*case_key, "route"),
                    {(*key, route) for key in cases for route in ROUTES})
    decisions = keyed(records(raw / "decisions.jsonl"), (*case_key, "policy", "budget_percent"),
                      {(*key, *pair) for key in cases for pair in registry})
    validate_pool_ids(decisions, pools)
    return split, cases, pools, quality, decisions


def validate_pool_ids(rows, pools):
    for key, row in rows.items():
        if row["pool_sha256"] != pools[key[:2]]["pool_sha256"]:
            raise ValueError(f"Frozen pool identity mismatch for {key}")


def official_module():
    if hashlib.sha256(SCORER.read_bytes()).hexdigest() != SCORER_SHA256:
        raise ValueError("Official HotpotQA scorer has changed")
    spec = importlib.util.spec_from_file_location("hotpot_evaluate_v1", SCORER)
    module = importlib.util.module_from_spec(spec)
    # ujson only handles file I/O in the upstream CLI. The scorer functions use Python primitives.
    use_fallback = "ujson" not in sys.modules and importlib.util.find_spec("ujson") is None
    if use_fallback:
        sys.modules["ujson"] = json
    try:
        spec.loader.exec_module(module)
    finally:
        if use_fallback:
            del sys.modules["ujson"]
    return module


def visible_references(pool, quality):
    """Map valid (title, original sentence index) pairs from the actually read paragraphs."""
    if pool["pool_sha256"] != quality["pool_sha256"]:
        raise ValueError(f"Pool identity mismatch for {quality['qid']} / {quality['route']}")
    chunks = {chunk["chunk_id"]: chunk for chunk in pool["input"]["contexts"]}
    ids = quality["chunk_ids"]
    if len(ids) != len(set(ids)) or not set(ids) <= chunks.keys():
        raise ValueError(f"Unknown or duplicate read paragraph for {quality['qid']} / {quality['route']}")
    visible = {}
    for chunk_id in ids:
        chunk = chunks[chunk_id]
        for sentence in chunk["sentences"]:
            sid = sentence["sentence_id"]
            prefix, index = sid.rsplit(":", 1)
            if prefix != chunk_id:
                raise ValueError(f"Invalid original sentence ID {sid}")
            visible[chunk["title"], int(index)] = sentence["text"]
    for title, index in quality["sp"]:
        if type(index) is not int or (title, index) not in visible:
            raise ValueError(f"Citation outside the read paragraphs for {quality['qid']}: {title}, {index}")
    return visible


def score_branch(official, gold, pool, row):
    if not isinstance(row["answer"], str):
        raise ValueError(f"Invalid answer for {row['qid']} / {row['route']}")
    visible = visible_references(pool, row)
    targets = [[fact["title"], fact["source_sentence_index"]] for fact in gold["supporting_facts"]]
    scores = Counter()
    official.update_answer(scores, row["answer"], gold["answer"])
    official.update_sp(scores, row["sp"], targets)
    gold_titles = {title for title, _ in targets}
    if not gold_titles:
        raise ValueError(f"Missing gold supporting facts for {row['qid']}")
    return {"answer_em": scores["em"], "answer_f1": scores["f1"], "sp_f1": scores["sp_f1"],
            "retrieved_gold_title_recall": len(gold_titles & {title for title, _ in visible}) / len(gold_titles)}


def sum_observed(values):
    return None if any(value is None for value in values) else sum(values)


def call_cost(calls):
    """Count observed costs. A failed API response can leave usage unavailable."""
    def attempts(call):
        count = call.get("attempts")
        return len(count) if isinstance(count, list) else count

    def reserved(call):
        size = call.get("expected_input_tokens")
        n = attempts(call)
        return size * n if size is not None and n is not None else None

    return {"input_tokens": sum_observed([c.get("input_tokens") for c in calls]),
            "output_tokens": sum_observed([c.get("output_tokens") for c in calls]),
            "qwen_calls": len(calls),
            "qwen_requests": sum_observed([attempts(c) for c in calls]),
            "attempted_prompt_tokens": sum_observed([reserved(c) for c in calls]),
            "failed_qwen_calls": sum(c.get("ok") is False for c in calls),
            "call_seconds": sum_observed([c.get("seconds") for c in calls])}


def live_cost(cost):
    return {f"live_path_{name}": cost.get(name) for name in ("input_tokens", "output_tokens", "qwen_requests")}


def replay_calls(quality, key, decision, selfcheck):
    first = quality[*key, "top2"]
    a = first["calls"]
    check = selfcheck[key]["calls"] if decision["policy"] == "qwen_selfcheck" else []
    b_route = "v2_direct_2plus1" if decision["policy"] == NATIVE else "direct_2plus4"
    route = decision["final_route"]
    attempted = decision["triggered"]
    expanded = quality[*key, b_route]
    expected = b_route if attempted and expanded["ok"] else "top2"
    if not isinstance(attempted, bool) or route != expected or (attempted and not first["ok"]):
        raise ValueError(f"Invalid action for {key}: {decision['policy']} / {route}")
    calls = [c for c in a if c["kind"] == "answer"] + check
    if attempted:
        # A retained on failure still incurs the B operations actually recorded.
        calls.extend(expanded["calls"])
    if route == "top2":
        calls.extend(c for c in a if c["kind"] != "answer")
    return calls


def policy_values(quality, decisions, branch, features, selfcheck, timing, key, registry):
    for route in ROUTES:
        row = quality[*key, route]
        cost = call_cost(row["calls"])
        yield {"qid": key[0], "pool_size": key[1], "method": route, "budget_percent": None,
               "final_route": route, "triggered": False, "adopted_b": False, "reason": row.get("reason"),
               "citation_reason": row.get("evidence_reason"),
               "ok": row["ok"], **branch[*key, route], **cost, **live_cost(cost),
               "nli_seconds": 0, "nli_input_tokens": 0, "nli_calls": 0,
               "live_path_seconds": row.get("seconds"), "replay_component_seconds": None}
    for policy, budget in registry:
        decision = decisions[*key, policy, budget]
        selection = decision["final_route"]
        result = quality[*key, selection]
        calls = replay_calls(quality, key, decision, selfcheck)
        fallback_uses_nli = decision.get("used_nli", False)
        uses_nli = policy not in ("constant_mean", "qwen_selfcheck") or fallback_uses_nli
        nli = features[key] if uses_nli else {}
        nli_seconds = nli.get("nli_seconds") if uses_nli else 0
        nli_tokens = nli.get("nli_input_tokens") if uses_nli else 0
        cost = call_cost(calls)
        b_route = "v2_direct_2plus1" if policy == NATIVE else "direct_2plus4"
        delta = branch[*key, b_route]["answer_f1"] - branch[*key, "top2"]["answer_f1"]
        live = timing.get((*key, policy, budget))
        yield {"qid": key[0], "pool_size": key[1], "method": policy, "budget_percent": budget,
               "final_route": selection, "triggered": decision["triggered"], "adopted_b": selection != "top2",
               "would_b_improve": delta > 0, "would_b_harm": delta < 0,
               "decision_score": decision.get("decision_score"), "reason": decision.get("reason"),
               "citation_reason": result.get("evidence_reason"),
               "ok": result["ok"], **branch[*key, selection], **cost,
               **live_cost(call_cost(live["calls"]) if live else {}),
               "nli_seconds": nli_seconds, "nli_input_tokens": nli_tokens,
               "nli_calls": int(nli_tokens > 0) if nli_tokens is not None else None,
               "live_path_seconds": live.get("seconds") if live else None,
               "replay_component_seconds": sum_observed([cost["call_seconds"], nli_seconds])}


def timing_records(raw, split, cfg):
    path = raw / "timing.jsonl"
    if not path.exists():
        return {}
    expected = {(qid, cfg["primary_size"], policy, -1 if policy == NATIVE else cfg["primary_budget_percent"])
                for qid in split["timing_qids"] for policy in cfg["timing_policies"]}
    return keyed(records(path), ("qid", "pool_size", "policy", "budget_percent"), expected)


def stats(values):
    observed = [v for v in values if v is not None]
    return {"mean": mean(observed) if observed else None, "n": len(observed)}


def summary(rows):
    per_metric = {field: stats([row[field] for row in rows]) for field in METRICS}
    for field in COST_METRICS:
        totals = [row[field] for row in rows]
        per_metric[field]["total"] = sum_observed(totals)
    for t in TIMING_METRICS:
        measured = [row[t] for row in rows if row[t] is not None]
        per_metric[t] = {**stats(measured), "p50": median(measured) if measured else None,
                         "p95": quantiles(measured, n=20, method="inclusive")[-1] if len(measured) > 1
                         else (measured[0] if measured else None)}
    gates = "would_b_improve" in rows[0]
    reasons = [row["reason"] for row in rows if row["reason"]]
    citation_reasons = [row["citation_reason"] for row in rows if row["citation_reason"]]
    return {"n": len(rows),
            "fallback_or_reason_n": sum(r not in ("frozen_score_boundary", "native_v2_boundary") for r in reasons),
            "reason_counts": dict(Counter(reasons)), "citation_reason_counts": dict(Counter(citation_reasons)),
            "failed_final_outputs": sum(not row["ok"] for row in rows),
            "failed_qwen_calls": sum(row["failed_qwen_calls"] for row in rows),
            "triggered_n": sum(row["triggered"] for row in rows) if gates else None,
            "selected_n": sum(row["adopted_b"] for row in rows) if gates else None,
            "actual_trigger_rate": mean(row["triggered"] for row in rows) if gates else None,
            "selected_improved": sum(row["adopted_b"] and row["would_b_improve"] for row in rows) if gates else None,
            "selected_tied": sum(row["adopted_b"] and not (row["would_b_improve"] or row["would_b_harm"])
                                 for row in rows) if gates else None,
            "selected_degraded": sum(row["adopted_b"] and row["would_b_harm"] for row in rows) if gates else None,
            "missed_improved": sum(not row["adopted_b"] and row["would_b_improve"] for row in rows) if gates else None,
            "metrics": per_metric}


def paired(groups, split, cfg):
    primary = set(split["primary_qids"])
    secondary = set(split["secondary_qids"])
    primary_size, primary_budget = cfg["primary_size"], cfg["primary_budget_percent"]
    count, seed = cfg["bootstrap_n"], cfg["bootstrap_seed"]
    comparisons = [
        ("primary", (primary_size, method, primary_budget), (primary_size, reference, primary_budget), primary)
        for method, reference in cfg["primary_comparisons"]
    ]
    for size in sorted([primary_size, *cfg["secondary_sizes"]]):
        comparisons += [
            ("same_question_secondary", (size, method, primary_budget), (size, reference, primary_budget), secondary)
            for method, reference in cfg["primary_comparisons"]
        ]
    comparisons += [
        ("cross_scale_secondary", (hi, method, budget), (lo, method, budget), secondary)
        for method, budget in ((PRIMARY, primary_budget), ("ridge", primary_budget), ("direct_2plus4", None), ("full", None))
        for lo, hi in ((10, 30), (30, 60))
    ]

    draws = {}
    results = []
    for scope, left, right, qids in comparisons:
        lrows = {row["qid"]: row for row in groups[left] if row["qid"] in qids}
        rrows = {row["qid"]: row for row in groups[right] if row["qid"] in qids}
        if not qids or set(lrows) != qids or set(rrows) != qids:
            raise ValueError(f"Incomplete paired comparison {scope}: {left}, {right}")
        for metric in PAIR_METRICS:
            deltas = [lrows[qid][metric] - rrows[qid][metric] for qid in sorted(qids)
                      if lrows[qid][metric] is not None and rrows[qid][metric] is not None]
            n = len(deltas)
            if n == 0:
                estimate = lo = hi = adjusted_lo = adjusted_hi = None
            elif len(set(deltas)) == 1:
                estimate = lo = hi = adjusted_lo = adjusted_hi = deltas[0]
            else:
                if n not in draws:
                    rng = Random(seed)
                    draws[n] = [rng.choices(range(n), k=n) for _ in range(count)]
                estimate = mean(deltas)
                values = [sum(deltas[i] for i in sample) / n for sample in draws[n]]
                limits = quantiles(values, n=40, method="inclusive")
                lo, hi = limits[0], limits[-1]
                adjusted_limits = quantiles(values, n=80, method="inclusive")
                adjusted_lo, adjusted_hi = adjusted_limits[0], adjusted_limits[-1]
            adjusted = scope == "primary" and metric == "answer_f1"
            results.append({"scope": scope, "left_size": left[0], "left_method": left[1],
                            "left_budget": left[2], "right_size": right[0], "right_method": right[1],
                            "right_budget": right[2], "metric": metric, "n": n, "expected_n": len(qids),
                            "difference": estimate, "ci95_low": lo, "ci95_high": hi,
                            "ci97_5_bonferroni_low": adjusted_lo if adjusted else None,
                            "ci97_5_bonferroni_high": adjusted_hi if adjusted else None})
    return results


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=HERE / "protocol.json")
    parser.add_argument("--policy-lock", type=Path)
    args = parser.parse_args()
    cfg = json.loads(args.protocol.read_text(encoding="utf-8"))
    if cfg["qa_scorer_sha256"] != SCORER_SHA256:
        raise ValueError("Protocol identifies a different evaluation script")
    registry = policy_registry(args.policy_lock or args.protocol.with_name("policy_lock.json"), args.protocol, cfg)
    split, cases, pools, quality, decisions = load_panel(args.input, args.raw, cfg, registry)
    gold = keyed(records(args.input / "evaluation_only/gold.jsonl"), ("qid",),
                 {(qid,) for qid in split["primary_qids"]})
    features = keyed(records(args.raw / "features.jsonl"), ("qid", "pool_size"), cases)
    selfcheck = keyed(records(args.raw / "selfcheck.jsonl"), ("qid", "pool_size"), cases)
    timing = timing_records(args.raw, split, cfg)
    for rows in (features, selfcheck, timing):
        validate_pool_ids(rows, pools)
    official = official_module()

    branch = {key: score_branch(official, gold[key[:1]], pools[key[:2]], row) for key, row in quality.items()}
    live_scores = {}
    for key, trial in timing.items():
        route = trial["final_route"]
        context_used = quality[*key[:2], route]["chunk_ids"]
        live_result = trial | {"route": route, "chunk_ids": context_used}
        live_scores[key] = score_branch(official, gold[key[:1]], pools[key[:2]], live_result)
    by_method = defaultdict(list)
    for key in sorted(cases):
        for row in policy_values(quality, decisions, branch, features, selfcheck, timing, key, registry):
            by_method[row["pool_size"], row["method"], row["budget_percent"]].append(row)

    summary_rows = []
    secondary = set(split["secondary_qids"])
    timed = set(split["timing_qids"])
    for (size, method, budget), rows in sorted(by_method.items(), key=lambda entry: str(entry[0])):
        subsets = [("primary" if size == cfg["primary_size"] else "same_question_secondary", rows)]
        if size == cfg["primary_size"]:
            subsets.append(("same_question_secondary", [r for r in rows if r["qid"] in secondary]))
            live_subset = [r for r in rows if r["qid"] in timed]
            if live_subset and all(r["live_path_seconds"] is not None for r in live_subset):
                if (method, budget) in registry:
                    measured = []
                    for row in live_subset:
                        key = (row["qid"], size, method, budget)
                        trial = timing[key]
                        spent = call_cost(trial["calls"])
                        measured.append(row | live_scores[key] | spent | {
                            "final_route": trial["final_route"], "triggered": trial["triggered"],
                            "adopted_b": trial["final_route"] != "top2", "ok": trial["ok"],
                            "reason": trial["reason"], "citation_reason": trial["citation_reason"],
                            "nli_input_tokens": trial["nli_input_tokens"],
                            "nli_calls": int(trial["nli_input_tokens"] > 0),
                            "replay_component_seconds": None,
                        })
                    live_subset = measured
                subsets.append(("common_live_timing", live_subset))
        for scope, selected in subsets:
            summary_rows.append({"scope": scope, "pool_size": size, "method": method, "budget_percent": budget,
                                 **summary(selected)})
    contrasts = paired(by_method, split, cfg)
    args.out.mkdir(parents=True, exist_ok=False)
    with (args.out / "per_question.jsonl").open("w", encoding="utf-8") as stream:
        for group in by_method.values():
            for row in group:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")

    flat = [{**{k: json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v
                for k, v in row.items() if k != "metrics"},
             **{f"{metric}_{field}": value for metric, stats in row["metrics"].items()
                for field, value in stats.items()}} for row in summary_rows]
    write_csv(args.out / "quality_cost.csv", flat)
    write_csv(args.out / "paired_intervals.csv", contrasts)
    live = [{"qid": qid, "pool_size": size, "policy": method, "budget_percent": budget,
             "live_path_seconds": r.get("seconds"), **call_cost(r["calls"]),
             **live_scores[qid, size, method, budget], "final_route": r["final_route"],
             "nli_seconds": r.get("nli_seconds"), "nli_input_tokens": r.get("nli_input_tokens")}
            for (qid, size, method, budget), r in sorted(timing.items())]
    if live:
        write_csv(args.out / "live_adaptive_timing.csv", live)
    run_summary = {"primary_size": split["primary_size"], "primary_n": len(split["primary_qids"]),
                   "secondary_same_qid_n_per_size": len(secondary), "bootstrap_n": cfg["bootstrap_n"],
                   "bootstrap_seed": cfg["bootstrap_seed"], "bootstrap_scope": "Fixed actions, paired resampling by qid.",
                   "time_scope": "Direct and live policy times are actual wall times. Replays sum measured components.",
                   "observed_live_policy_rows": len(live), "results": summary_rows, "paired_intervals": contrasts}
    (args.out / "summary.json").write_text(json.dumps(run_summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Verified {len(cases)} question/scale cases and evaluated {len(summary_rows)} comparisons.")


if __name__ == "__main__":
    main()

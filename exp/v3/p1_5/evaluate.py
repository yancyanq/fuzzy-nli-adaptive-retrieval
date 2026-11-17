"""Score and audit P1.5 answers locally with the locked HotpotQA evaluator."""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from statistics import mean, quantiles
import sys

from run import HERE, file_hash, read_jsonl


ROOT = HERE.parents[2]
P1 = ROOT / "exp/v3/p1/artifacts"
V2 = ROOT / "exp/v2"
FIXED = ("top2", "top4", "top6", "full")
EXPANSION = ("v2_direct_2plus1", "2plus1", "2plus2", "2plus4")


def csv_out(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_successes(raw, protocol, lengths, qids):
    expected_hashes = {name: file_hash(path) for name, path in {
        "pools": P1 / "pools.jsonl", "lengths": P1 / "length_audit.csv",
        "protocol": HERE / "protocol.json", "runner": HERE / "run.py",
        "v2_retrieval": V2 / "bm25_topk.py", "v2_prompt": V2 / "compare_models.py",
    }.items()}
    answers, diagnostics = {}, {}
    for cap, service in protocol["services"].items():
        folder = raw / cap
        identity = json.loads((folder / "identity.json").read_text())
        sizes = service["pool_sizes"]
        if (identity["sha256"] != expected_hashes or identity["cap"] != int(cap)
                or identity["sizes"] != sizes or set(identity["qid_order"]) != qids):
            raise ValueError(f"Live evidence identity mismatch: {cap}")
        qid_order = identity["qid_order"]
        rows = read_jsonl(folder / "records.jsonl")
        expected = len(qids) * len(sizes) * len(protocol["routes"])
        if json.loads((folder / "complete.json").read_text())["route_records"] != expected:
            raise ValueError(f"Incomplete route evidence: {cap}")
        bad = [row for row in rows if not row["ok"]]
        measured = read_jsonl(folder / "batches.jsonl")
        warmed = read_jsonl(folder / "warmups.jsonl")
        if any(not row["ok"] for row in warmed):
            raise ValueError("A warm-up failure requires review")
        diagnostics[cap] = {
            "successful_route_records": expected, "failed_route_records_before_recovery": len(bad),
            "http_attempts_experiment": sum(len(call["attempts"]) for row in rows for call in row["calls"]),
            "http_attempts_warmup": sum(len(call["attempts"]) for row in warmed for call in row["calls"]),
            "failed_http_or_validation_attempts": sum(
                attempt.get("http_status") != 200 for row in rows for call in row["calls"] for attempt in call["attempts"]
            ),
            "warmup_prompt_tokens": sum(call["input_tokens"] for row in warmed for call in row["calls"]),
            "warmup_output_tokens": sum(call["output_tokens"] for row in warmed for call in row["calls"]),
            "warmup_seconds": sum(row["elapsed_seconds"] for row in warmed),
            "sum_measured_batch_wall_seconds": sum(row["seconds"] for row in measured),
        }
        for row in rows:
            if not row["ok"]:
                continue
            size, qid, route = row["pool_size"], row["qid"], row["route"]
            key = size, qid, route
            if key in answers or size not in sizes or qid not in qids or row["phase"] != "experiment":
                raise ValueError(f"Unexpected duplicate/foreign record {key}")
            if qid not in qid_order[row["block"] * protocol["client_workers"]:(row["block"] + 1) * protocol["client_workers"]]:
                raise ValueError(f"Unexpected timing block: {key}")
            spec = protocol["routes"][route]
            paths = (["top2"] if spec["first_answer"] else []) + [spec["prompt_path"]]
            for path, call in zip(paths, row["calls"], strict=True):
                locked = lengths[size, qid, path]
                if (not call["ok"] or call["prompt_path"] != path or row["pool_sha256"] != locked["pool_sha256"]
                        or call["prompt_sha256"] != locked["prompt_sha256"]
                        or call["chunk_ids"] != json.loads(locked["ordered_chunk_ids"])
                        or not set(call["cited_chunk_ids"]) <= set(call["chunk_ids"])
                        or call["input_tokens"] != int(locked["input_tokens"])
                        or not 0 <= call["output_tokens"] <= protocol["max_output_tokens"]):
                    raise ValueError(f"Prompt, token or citation evidence mismatch: {key} / {path}")
            answers[key] = row
    all_sizes = {n for service in protocol["services"].values() for n in service["pool_sizes"]}
    if answers.keys() != {(n, qid, route) for n in all_sizes for qid in qids for route in protocol["routes"]}:
        raise ValueError("Incomplete or differing sample panels across the locked routes")
    return answers, diagnostics


def score_rows(official, answers, labels):
    output = {}
    for (size, qid, route), row in sorted(answers.items()):
        label = labels[qid]
        refs = {f["chunk_id"] for f in label["supporting_facts"]}
        calls = row["calls"]
        final = calls[-1]
        seen, cited = set(final["chunk_ids"]), set(final["cited_chunk_ids"])
        f1 = official.f1_score(final["answer"], label["answer"])[0]
        output[size, qid, route] = {
            "pool_size": size, "qid": qid, "route": route,
            "f1": f1, "em": int(official.exact_match_score(final["answer"], label["answer"])),
            "retrieved_support_recall": len(refs & seen) / len(refs), "both_supports_retrieved": int(refs <= seen),
            "cited_support_recall": len(refs & cited) / len(refs), "both_supports_cited": int(refs <= cited),
            "cited_support_precision": len(refs & cited) / len(cited) if cited else 0,
            "llm_calls": len(calls), "input_tokens": sum(call["input_tokens"] for call in calls),
            "output_tokens": sum(call["output_tokens"] for call in calls),
            "elapsed_seconds": row["elapsed_seconds"],
            "final_parse_ok": int(final["parse_ok"]), "invalid_final_citations": final["invalid_citations"],
            "final_hit_output_limit": int(final["finish_reason"] == "length"),
            "cpu_and_other_seconds": row["elapsed_seconds"] - sum(a["seconds"] for c in calls for a in c["attempts"]),
            "own_first_f1": official.f1_score(calls[0]["answer"], label["answer"])[0] if len(calls) == 2 else None,
        }
    return output


def summarize_route(rows, anomaly):
    sample = rows[0]
    copy = {key: mean(row[key] for row in rows) for key in (
        "f1", "em", "retrieved_support_recall", "cited_support_recall", "cited_support_precision",
        "llm_calls", "input_tokens", "output_tokens", "elapsed_seconds", "cpu_and_other_seconds",
    )}
    return {"pool_size": sample["pool_size"], "route": sample["route"], "n": len(rows), **copy,
            "both_supports_retrieved_n": sum(row["both_supports_retrieved"] for row in rows),
            "both_supports_cited_n": sum(row["both_supports_cited"] for row in rows),
            "elapsed_p50": quantiles([row["elapsed_seconds"] for row in rows], n=100, method="inclusive")[49],
            "elapsed_p95": quantiles([row["elapsed_seconds"] for row in rows], n=100, method="inclusive")[94],
            "parse_failure_n": sum(1 - row["final_parse_ok"] for row in rows),
            "invalid_final_citations_n": sum(row["invalid_final_citations"] for row in rows),
            "final_hit_output_limit_n": sum(row["final_hit_output_limit"] for row in rows),
            "f1_without_known_label_anomaly": mean(row["f1"] for row in rows if row["qid"] != anomaly)}


def pair_report(size, route, a, b, full, bootstrap):
    delta = [right["f1"] - left["f1"] for left, right in zip(a, b, strict=True)]
    oracle = [max(left["f1"], right["f1"]) for left, right in zip(a, b, strict=True)]
    counts = Counter((difference > 0) - (difference < 0) for difference in delta)
    own_oracle = [max(row["own_first_f1"], row["f1"]) for row in b if row["own_first_f1"] is not None]
    effect, low, high = bootstrap(delta)
    return {
        "pool_size": size, "route": route, "n": len(delta), "improved": counts[1], "unchanged": counts[0],
        "degraded": counts[-1], "b_minus_a_f1": effect, "b_minus_a_bootstrap_low": low, "b_minus_a_bootstrap_high": high,
        "oracle_f1": mean(oracle), "oracle_minus_a_f1": mean(oracle) - mean(row["f1"] for row in a),
        "oracle_minus_full_f1": mean(oracle) - mean(row["f1"] for row in full),
        "oracle_with_own_first_f1": mean(own_oracle) if own_oracle else None,
        "own_first_f1_diff_from_shared_count": sum(
            right["own_first_f1"] is not None and right["own_first_f1"] != left["f1"]
            for left, right in zip(a, b, strict=True)
        ),
    }


def frontier(rows, cost):
    return [x["route"] for x in rows if not any(
        y[cost] <= x[cost] and y["f1"] >= x["f1"] and (y[cost] < x[cost] or y["f1"] > x["f1"])
        for y in rows
    )]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True, help="Folder containing per-service results 8192 and 16384")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads((HERE / "protocol.json").read_text())
    labels = {row["qid"]: row for row in read_jsonl(P1 / "evaluation_only/gold.jsonl")}
    if len(labels) != 50:
        raise ValueError("Expected the frozen 50-question evaluation panel")
    with (P1 / "length_audit.csv").open(encoding="utf-8") as stream:
        lengths = {(int(r["pool_size"]), r["qid"], r["path"]): r for r in csv.DictReader(stream)}
    answers, diagnostics = read_successes(args.raw, protocol, lengths, set(labels))
    sys.path.insert(0, str(V2))
    from generate_test_v2 import load_official
    from run_pilot import paired_bootstrap_mean_ci

    scorer = V2 / "step5_v2/hotpot_evaluate_v1.py"
    if file_hash(scorer) != protocol["qa_scorer_sha256"]:
        raise ValueError("Preregistered answer scorer hash mismatch")
    scored = score_rows(load_official(scorer), answers, labels)
    qids = sorted(labels)
    routes, pairs, full_contrasts, comparisons = [], [], [], {}
    for size in sorted({key[0] for key in scored}):
        by_method = {route: [scored[size, qid, route] for qid in qids] for route in protocol["routes"]}
        scale_stats = [summarize_route(group, protocol["predeclared_sensitivity_qid"]) for group in by_method.values()]
        routes.extend(scale_stats)
        pairs.extend(pair_report(size, route, by_method["top2"], by_method[route], by_method["full"],
                                 paired_bootstrap_mean_ci) for route in EXPANSION)
        scale_index = {row["route"]: row for row in scale_stats}
        full = scale_index["full"]
        for route, group in by_method.items():
            if route == "full":
                continue
            differences = [row["f1"] - ref["f1"] for row, ref in zip(group, by_method["full"], strict=True)]
            estimate, low, high = paired_bootstrap_mean_ci(differences)
            full_contrasts.append({
                "pool_size": size, "route": route, "n": len(differences),
                "f1_minus_full": estimate, "bootstrap_95_low": low, "bootstrap_95_high": high,
                "input_token_change_fraction": scale_index[route]["input_tokens"] / full["input_tokens"] - 1,
                "latency_change_fraction": scale_index[route]["elapsed_seconds"] / full["elapsed_seconds"] - 1,
                "f1_minus_full_without_known_label_anomaly": mean(
                    delta for row, delta in zip(group, differences, strict=True)
                    if row["qid"] != protocol["predeclared_sensitivity_qid"]
                ),
            })
        best = max((row for row in scale_stats if row["route"] in FIXED), key=lambda row: row["f1"])
        comparisons[size] = {
            "highest_fixed_route": best["route"],
            "pareto_f1_vs_input_tokens": frontier(scale_stats, "input_tokens"),
            "pareto_f1_vs_elapsed": frontier(scale_stats, "elapsed_seconds"),
            "cascade_vs_direct_same_context_f1_delta": mean(
                scored[size, qid, "2plus1"]["f1"] - scored[size, qid, "v2_direct_2plus1"]["f1"] for qid in qids
            ),
            "cascade_vs_direct_same_context_answer_difference_n": sum(
                answers[size, qid, "2plus1"]["calls"][-1]["answer"]
                != answers[size, qid, "v2_direct_2plus1"]["calls"][-1]["answer"] for qid in qids
            ),
        }
    args.out.mkdir(parents=True, exist_ok=True)
    csv_out(args.out / "per_question.csv", list(scored.values()))
    csv_out(args.out / "strategy_metrics.csv", routes)
    csv_out(args.out / "paired_oracle.csv", pairs)
    csv_out(args.out / "full_contrasts.csv", full_contrasts)
    summary = {"n_per_scale_and_route": len(labels), "route_metrics": routes, "paired_oracles": pairs,
               "comparisons": comparisons, "diagnostics": diagnostics,
               "gold_sha256": file_hash(P1 / "evaluation_only/gold.jsonl"), "scorer_sha256": file_hash(scorer),
               "scored_records": len(scored), "paired_bootstrap_samples": 10000, "paired_bootstrap_seed": 42}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Scored {len(scored)} live routes on the fixed 50-question panel.")


if __name__ == "__main__":
    main()

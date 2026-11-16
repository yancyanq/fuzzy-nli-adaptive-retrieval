"""Score the formal V2 branch cache and measure warmed real execution paths."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from statistics import mean
from threading import Lock
from time import perf_counter

import analyze_pilot_signals_v2 as signals
import calibrate_gates_v2 as gates
import generate_test_v2 as gen
import run_pilot as pilot

cm = gen.cm
METHODS = ("never", "always", "nli_only", "crisp", "fuzzy", "full")
ABLATIONS = ("fuzzy_without_nli", "fuzzy_without_bridge")
NLI_DIR = Path("models/dev-deberta-b3546ea")


def branch_cache(args, questions, branches, cache_name):
    fields = ("model", "_id", "branch")
    expected = {(gen.MODEL, ex["_id"], branch) for ex in questions for branch in branches}
    records = gen.read_cache(args.out / cache_name, fields, expected)
    return records, expected


def inputs_for_nli(ex, answer):
    premise = pilot.build_premise(ex, answer["citations"], answer["paragraph_indices"])
    return {"premise": premise["premise"],
            "hypothesis": pilot.build_hypothesis(ex["question"], answer["answer"])}, premise["used_fallback"]


def score_nli(args, questions):
    answers, expected = branch_cache(args, questions, gen.BRANCHES, "answers_test_v2.jsonl")
    if answers.keys() != expected:
        raise ValueError("Answer cache is incomplete")
    path = args.out / "nli_test_v2.jsonl"
    scores, expected = branch_cache(args, questions, ("A", "B"), path.name)
    remaining = [(ex, branch) for ex in questions for branch in ("A", "B")
                 if (gen.MODEL, ex["_id"], branch) not in scores]
    if not remaining:
        return
    scorer = pilot.HFNliScorer(str(args.nli_model), args.nli_device, max_length=512, batch_size=4)
    with path.open("a", encoding="utf-8") as out:
        for start in range(0, len(remaining), 64):
            group = remaining[start:start+64]
            items, fallbacks = zip(*(inputs_for_nli(ex, answers[gen.MODEL, ex["_id"], branch])
                                     for ex, branch in group))
            for (ex, branch), fallback, result in zip(group, fallbacks, scorer.score_many(items)):
                gen.append_record(out, {**result, "model": gen.MODEL, "nli_model": result["model"],
                                        "_id": ex["_id"], "branch": branch,
                                        "nli_device": args.nli_device, "used_fallback": fallback})
    print(f"NLI cache complete: {len(expected)} branches", flush=True)


def bridge_absence(ex, indices):
    matches = signals.bridge_matches(ex["context"], indices)
    return None if matches is None else not matches


def choose_b(method, locked, qid, entailment, absent):
    if method in ABLATIONS:
        gate = locked["fuzzy"]
        if method == "fuzzy_without_nli":
            parameters = gate["parameters"]
            midpoint = (parameters["lo"] + parameters["hi"]) / 2
            entailment = 1 - midpoint
        else:
            absent = None
        return gates.should_retrieve(gate, qid, entailment, absent)
    return gates.should_retrieve(locked[method], qid, entailment, absent)


def replay(args, questions, lock, official):
    answers, expected = branch_cache(args, questions, gen.BRANCHES, "answers_test_v2.jsonl")
    evidence, _ = branch_cache(args, questions, gen.BRANCHES, "evidence_test_v2.jsonl")
    nli, expected_nli = branch_cache(args, questions, ("A", "B"), "nli_test_v2.jsonl")
    if answers.keys() != expected or evidence.keys() != expected or nli.keys() != expected_nli:
        raise ValueError("Incomplete answers, sentence evidence or NLI")

    methods = (*METHODS, "oracle", *ABLATIONS)
    totals = {name: Counter() for name in methods}
    predictions = {name: {"answer": {}, "sp": {}} for name in methods}
    rows = []
    for ex in questions:
        qid = ex["_id"]
        branch_info = {branch: answers[gen.MODEL, qid, branch] for branch in gen.BRANCHES}
        sp = {branch: evidence[gen.MODEL, qid, branch]["sp"] for branch in gen.BRANCHES}
        score = {branch: gen.scoring_row(official, ex, branch_info[branch]["answer"], sp[branch])
                 for branch in gen.BRANCHES}
        first, second = cm.retrieve_indices(ex, 2, 1)
        if (branch_info["A"]["paragraph_indices"], branch_info["B"]["paragraph_indices"],
            branch_info["full"]["paragraph_indices"]) != (first, first + second, list(range(len(ex["context"])))):
            raise ValueError(f"Retrieval mismatch on {qid}")
        nli_a = nli[gen.MODEL, qid, "A"]
        nli_b = nli[gen.MODEL, qid, "B"]
        entailment = nli_a["probs"]["entailment"]
        absent = bridge_absence(ex, first)
        delta = score["B"]["f1"] - score["A"]["f1"]
        label = cm.classify_delta(delta, 0)
        selected = {"never": "A", "always": "B", "full": "full", "oracle": "B" if delta > 0 else "A"}
        for method in ("nli_only", "crisp", "fuzzy", *ABLATIONS):
            selected[method] = "B" if choose_b(method, lock["gates"], qid, entailment, absent) else "A"
        row = {"_id": qid, "delta_f1": delta, "delta_class": label, "extra_paragraphs": len(second),
               "entailment_A": entailment, "entailment_B": nli_b["probs"]["entailment"], "bridge_absent": absent,
               "nli_truncated_A": nli_a["truncated"], "nli_truncated_B": nli_b["truncated"],
               "nli_fallback_A": nli_a["used_fallback"], "nli_fallback_B": nli_b["used_fallback"]}
        for method, branch in selected.items():
            metrics = score[branch]
            totals[method].update(metrics)
            totals[method]["selected_B"] += branch == "B"
            if branch == "B":
                totals[method]["selected_" + label] += 1
            change = cm.classify_delta(metrics["f1"] - score["A"]["f1"], 0)
            totals[method]["vs_never_" + change] += 1
            predictions[method]["answer"][qid] = branch_info[branch]["answer"]
            predictions[method]["sp"][qid] = sp[branch]
            row.update({f"{method}_branch": branch, f"{method}_f1": metrics["f1"],
                        f"{method}_em": metrics["em"], f"{method}_sp_f1": metrics["sp_f1"]})
        rows.append(row)

    out = args.out
    pred_dir = out / "predictions"
    pred_dir.mkdir(exist_ok=True)
    for method, prediction in predictions.items():
        gen.write_json(pred_dir / (method + ".json"), prediction)
    table_tmp = out / "per_question.csv.tmp"
    with table_tmp.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    table_tmp.replace(out / "per_question.csv")
    n = len(questions)
    positives = totals["always"]["selected_improved"]
    summary = {"n": n, "dev_target": lock["dev_target_count"] / lock["dev_n"],
               "official_sha256": gen.SCORER_SHA, "methods": {}, "diagnostics": {}}
    for method, counts in totals.items():
        true_positive = counts["selected_improved"]
        triggered = counts["selected_B"]
        precision = true_positive / triggered if triggered else 0.0
        recall = true_positive / positives if positives else 0.0
        summary["methods"][method] = {
            **{metric: counts[metric] / n for metric in ("f1", "em", "sp_f1")},
            "selected_B": triggered, "retrieval_rate": triggered / n,
            "selected_labels": {label: counts["selected_" + label] for label in ("improved", "tie", "degraded")},
            "changes_vs_never": {label: counts["vs_never_" + label] for label in ("improved", "tie", "degraded")},
            "gate_precision": precision, "gate_recall": recall,
            "gate_f1": 2 * precision * recall / (precision + recall) if precision + recall else 0,
        }
    for branch in gen.BRANCHES:
        branch_answers = [answers[gen.MODEL, ex["_id"], branch] for ex in questions]
        branch_evidence = [evidence[gen.MODEL, ex["_id"], branch] for ex in questions]
        calls = [call for record in branch_evidence for call in record["evidence_calls"]]
        diagnostic = {
            "answer_parse_fallback": sum(not record["parse_ok"] for record in branch_answers),
            "empty_sp": sum(not record["sp"] for record in branch_evidence),
            "selector_calls": len(calls), "selector_malformed_calls": sum(not call["parse_ok"] for call in calls),
            "selector_invalid_ids": sum(call["invalid_ids"] for call in calls),
            "selector_split_cases": sum(len(record["evidence_calls"]) > 1 for record in branch_evidence),
        }
        if branch in ("A", "B"):
            diagnostic["nli_truncation"] = sum(row[f"nli_truncated_{branch}"] for row in rows)
            diagnostic["nli_fallback"] = sum(row[f"nli_fallback_{branch}"] for row in rows)
        summary["diagnostics"][branch] = diagnostic
    summary["diagnostics"]["no_extra_paragraph"] = sum(not row["extra_paragraphs"] for row in rows)
    gen.write_json(out / "quality_summary.json", summary)
    print(f"Official scoring and replay complete for {n} questions", flush=True)


def run_live(ex, method, client, tokenizer, scorer, scorer_lock, locked):
    started = perf_counter()
    nli_tokens = 0
    triggered = method == "always"
    if method == "full":
        answer = gen.answer_request(client, ex, list(range(len(ex["context"]))))
    elif method == "always":
        first, extra = cm.retrieve_indices(ex, 2, 1)
        answer = gen.answer_request(client, ex, first + extra)
    else:
        first, _ = cm.retrieve_indices(ex, 2, 0)
        answer = gen.answer_request(client, ex, first)

    answers = [answer]
    nli_calls = int(method in ("nli_only", "crisp", "fuzzy"))
    if nli_calls:
        item, _ = inputs_for_nli(ex, answer)
        with scorer_lock:
            result = scorer.score_many([item])[0]
        nli_tokens = min(result["n_tokens"], 512)
        absent = bridge_absence(ex, first) if method != "nli_only" else None
        triggered = choose_b(method, locked, ex["_id"], result["probs"]["entailment"], absent)
        if triggered:
            # Replay the frozen retrieval entry point after deciding on the second round.
            first, extra = cm.retrieve_indices(ex, 2, 1)
            answer = gen.answer_request(client, ex, first + extra)
            answers.append(answer)
    evidence = gen.select_evidence(client, tokenizer, ex, answer)
    ended = perf_counter()
    calls = answers + evidence["evidence_calls"]
    return {"_id": ex["_id"], "method": method, "triggered": triggered,
            "elapsed_seconds": ended - started, "llm_calls": len(calls), "nli_calls": nli_calls,
            "answer_calls": len(answers), "selector_calls": len(evidence["evidence_calls"]),
            "prompt_tokens": sum(call["prompt_tokens"] for call in calls),
            "completion_tokens": sum(call["completion_tokens"] for call in calls),
            "nli_input_tokens": nli_tokens, "answer": answer["answer"], "sp": evidence["sp"]}


def latency(args, questions, lock, smoke=False):
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, local_files_only=True)
    client = cm.make_client("http://127.0.0.1:8000/v1", "VLLM_API_KEY", allow_missing_key=True)
    scorer = pilot.HFNliScorer(str(args.nli_model), args.nli_device, max_length=512, batch_size=1)
    scorer_lock = Lock()
    warm = gen.stable_sample(gen.read_json(args.tune), 8)

    def run(job):
        ex, method = job
        return run_live(ex, method, client, tokenizer, scorer, scorer_lock, lock["gates"])

    if smoke:
        sample = list(gen.parallel_results([(ex, "fuzzy") for ex in warm], run))
        print(f"Co-resident Qwen plus {args.nli_device} NLI smoke: {len(sample)} real dev paths", flush=True)
        return

    sample = gen.stable_sample(questions, 32)
    path = args.out / "latency_test_v2.jsonl"
    fields = ("nli_device", "_id", "method")
    expected = {(args.nli_device, ex["_id"], method) for ex in sample for method in METHODS}
    records = gen.read_cache(path, fields, expected)
    with path.open("a", encoding="utf-8") as stream:
        for method in METHODS:
            pending = [(ex, method) for ex in sample if (args.nli_device, ex["_id"], method) not in records]
            if not pending:
                continue
            list(gen.parallel_results([(ex, method) for ex in warm], run))
            for row in gen.parallel_results(pending, run):
                row["nli_device"] = args.nli_device
                gen.append_record(stream, row)
                records[args.nli_device, row["_id"], method] = row
            print(f"Real cost complete for {method}: {len(sample)} questions", flush=True)

    costs = {}
    for method in METHODS:
        group = [records[args.nli_device, ex["_id"], method] for ex in sample]
        times = sorted(row["elapsed_seconds"] for row in group)
        costs[method] = {
            "n": len(group), "seconds_mean": mean(times),
            "seconds_p50": gates.quantile(times, .50), "seconds_p90": gates.quantile(times, .90),
            "seconds_p95": gates.quantile(times, .95),
            **{name + "_mean": mean(row[name] for row in group) for name in (
                "llm_calls", "nli_calls", "answer_calls", "selector_calls",
                "prompt_tokens", "completion_tokens", "nli_input_tokens", "triggered",
            )},
        }
    gen.write_json(args.out / "latency_summary.json",
                   {"nli_device": args.nli_device, "concurrency": 8, "per_method_dev_warmups": 8,
                    "sample_ids": [ex["_id"] for ex in sample], "methods": costs})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("nli", "evaluate", "latency", "latency-smoke"))
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scorer", type=Path, required=True)
    parser.add_argument("--lock", type=Path, default=Path("step4_dev/gates/locked_gates.json"))
    parser.add_argument("--serve-script", type=Path, default=Path(".serve-step4.sh"))
    parser.add_argument("--tune", type=Path, default=Path("tune.json"))
    parser.add_argument("--nli-model", type=Path, default=NLI_DIR)
    parser.add_argument("--nli-device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--tokenizer", default="models/Qwen2.5-7B-Instruct")
    args = parser.parse_args()
    lock = gen.load_lock(args.lock, args.serve_script)
    if args.stage == "latency-smoke":
        latency(args, [], lock, smoke=True)
        return
    questions = gen.load_test(args.data)
    if args.stage == "nli":
        score_nli(args, questions)
    elif args.stage == "evaluate":
        replay(args, questions, lock, gen.load_official(args.scorer))
    else:
        latency(args, questions, lock)


if __name__ == "__main__":
    main()

"""Verify cached P2 relationship records using the pinned CPU DeBERTa."""

import argparse
from itertools import zip_longest
import json
import math
from pathlib import Path
import sys
from time import perf_counter

import p15_runner as p15
from verify import bundle_plan, indexed, messages, validate_relationships, validate_selfcheck


def scored(scorer, premise, hypothesis, limit, local):
    token_count = scorer._n_tokens(premise, hypothesis)
    if local and token_count > limit:
        raise ValueError("Local scoring would truncate evidence")
    start = perf_counter()
    (result,) = scorer.score_many([{"premise": premise, "hypothesis": hypothesis}])
    seconds = perf_counter() - start
    probs = result["probs"]
    if (set(probs) != {"entailment", "neutral", "contradiction"}
            or any(not math.isfinite(x) or not 0 <= x <= 1 for x in probs.values())
            or not math.isclose(sum(probs.values()), 1, abs_tol=1e-6)
            or result["n_tokens"] != token_count or (local and result["truncated"])):
        raise ValueError("Unexpected NLI probabilities or token accounting")
    return {**result, "actual_input_tokens": min(token_count, limit), "seconds": seconds}


def verify_local(requirements, refs, scorer, nli):
    limit = nli["input_tokens_max"]
    plans = [bundle_plan(relation, refs, scorer._n_tokens, limit) for relation in requirements]
    # Give every scorable relationship its first bundle before spending any
    # remaining budget on split evidence for the same relationship.
    rounds = zip_longest(*(plan["bundles"] for plan in plans))
    calls_left = nli["local_calls_max_per_qid"]
    for candidates in rounds:
        for bundle in candidates:
            if bundle is None:
                continue
            if calls_left == 0:
                bundle["status"] = "not_scored_call_limit"
                continue
            bundle["prediction"] = scored(scorer, bundle["premise"], bundle["hypothesis"], limit, local=True)
            bundle["status"] = "scored"
            calls_left -= 1
    for requirement, plan in zip(requirements, plans, strict=True):
        joint = plan["bundles"][0].get("prediction") if plan["kind"] == "joint" else None
        plan["requirement_id"] = requirement["id"]
        plan["full_claim_entailment"] = joint["probs"]["entailment"] if joint else None
        plan["diagnostic_supported"] = joint is not None and joint["probs"]["entailment"] >= nli["diagnostic_entailment_min"]
    return plans


def verify_one(row, extracted, checked, scorer, cfg, pilot, bridge_matches, gate_score, gate):
    qid = row["qid"]
    from guided import FORMAT, validate_wire, wire_messages
    guided = extracted.get("format") == FORMAT
    for task, cached in (("relations", extracted), ("selfcheck", checked)):
        if (not cached["ok"] or cached["pool_sha256"] != row["pool_sha256"]
                or cached["a_prompt_sha256"] != row["a_prompt_sha256"]
                or (cached.get("format") == FORMAT) != guided
                or cached["prompt_sha256"] != p15.digest((wire_messages if guided else messages)(row, task))):
            raise ValueError(f"Unmatched P2 Qwen record for {qid}/{task}")
    refs = indexed(row)
    rel = validate_wire(extracted["raw"], row, "relations") if guided else validate_relationships(extracted["raw"], refs)
    selfcheck = validate_wire(checked["raw"], row, "selfcheck") if guided else validate_selfcheck(checked["raw"])
    if rel != extracted["validation"] or selfcheck != checked["validation"]:
        raise ValueError(f"Qwen validation replay differs for {qid}")
    nli = cfg["nli"]
    limit = nli["input_tokens_max"]
    context = [[chunk["title"], [sent["text"] for sent in chunk["sentences"]]] for chunk in row["contexts"]]
    old = pilot.build_premise({"context": context}, row["draft_citations"], [0, 1])
    hypothesis = pilot.build_hypothesis(row["question"], row["draft_answer"])
    whole = scored(scorer, old["premise"], hypothesis, limit, local=False)
    whole.update({"premise": old["premise"], "hypothesis": hypothesis,
                  "used_retrieved_fallback": old["used_fallback"]})
    whole_r = 1 - whole["probs"]["entailment"]
    bridge = bridge_matches(context, [0, 1])
    old_gate = gate_score(gate["kind"], gate["parameters"], whole_r, None if bridge is None else not bridge)

    started = perf_counter()
    reqs = rel["record"]["requirements"] if rel["ok"] else []
    plans = verify_local(reqs, refs, scorer, nli) if reqs else []
    local_seconds = perf_counter() - started
    bundles = [bundle for plan in plans for bundle in plan["bundles"] if bundle["status"] == "scored"]
    intact_e = [plan["full_claim_entailment"] for plan in plans if plan["full_claim_entailment"] is not None]
    risk = 1 - min(intact_e) if intact_e else None
    gap = sum(not plan["diagnostic_supported"] for plan in plans) / len(plans) if plans else None
    fallback_reason = "invalid_relation_record" if not rel["ok"] else "no_intact_scorable_claim" if risk is None else None
    contradiction = max((bundle["prediction"]["probs"]["contradiction"] for bundle in bundles), default=None)
    return {
        "qid": qid, "pool_sha256": row["pool_sha256"], "a_prompt_sha256": row["a_prompt_sha256"],
        "relation_validation": rel, "local_claims": plans, "old_whole": whole, "bridge_matches": bridge,
        "signals": {"old_nli_risk": whole_r, "old_nli_bridge": old_gate, "local_r": risk, "local_g": gap,
                    "local_max_contradiction": contradiction,
                    "local_r_with_fallback": old_gate if fallback_reason else risk,
                    "local_g_with_fallback": old_gate if fallback_reason else gap,
                    "local_combined_with_fallback": old_gate if fallback_reason else (risk + gap) / 2,
                    "qwen_selfcheck_with_fallback": selfcheck.get("risk", old_gate)},
        "fallback_reason": fallback_reason, "local_nli_calls": len(bundles),
        "local_nli_input_tokens": sum(bundle["prediction"]["actual_input_tokens"] for bundle in bundles),
        "local_build_and_nli_seconds": local_seconds, "local_supported_count": sum(p["diagnostic_supported"] for p in plans),
        "ambiguity_flags": [r["uncertainty"] for r in reqs if r["uncertainty"] != "none"],
        "recorded_at_utc": p15.utc_now(),
    }


def by_id(path, panel):
    rows = [row for row in p15.read_jsonl(path) if row["ok"]]
    indexed_rows = {row["qid"]: row for row in rows}
    if len(rows) != len(indexed_rows) or indexed_rows.keys() != panel.keys():
        raise ValueError(f"Incomplete or misaligned Qwen output {path}")
    return indexed_rows


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--bundle", required=True, type=Path)
    cli.add_argument("--qwen", required=True, type=Path)
    cli.add_argument("--snapshot", required=True, type=Path)
    cli.add_argument("--out", required=True, type=Path)
    args = cli.parse_args()
    bundle = args.bundle
    cfg = json.loads((bundle / "protocol.json").read_text())
    nli = cfg["nli"]
    if p15.file_hash(args.snapshot / "model.safetensors") != nli["model_sha256"]:
        raise ValueError("DeBERTa weight SHA-256 mismatch")
    panel = {r["qid"]: r for r in p15.read_jsonl(bundle / "panel.jsonl")}
    if len(panel) != cfg["count"]:
        raise ValueError("Wrong P2 panel size")
    rel = by_id(args.qwen / "relations.jsonl", panel)
    selfcheck = by_id(args.qwen / "selfcheck.jsonl", panel)
    sys.path.insert(0, str((bundle / "v2").resolve()))
    import torch
    import run_pilot as pilot
    from analyze_pilot_signals_v2 import bridge_matches
    from calibrate_gates_v2 import gate_score

    torch.set_num_threads(nli["threads"])
    torch.set_num_interop_threads(1)
    warm_start = perf_counter()
    scorer = pilot.HFNliScorer(str(args.snapshot), nli["device"], max_length=nli["input_tokens_max"], batch_size=nli["batch_size"])
    if set(scorer.id2label.values()) != {"entailment", "neutral", "contradiction"}:
        raise ValueError("Unexpected pinned DeBERTa label order")
    load_seconds = perf_counter() - warm_start
    sanity = "The instrument manual states that the lamp is red."
    warmup = [scored(scorer, sanity, hypothesis, nli["input_tokens_max"], local=True) for hypothesis in (
        "The manual states that the lamp is red.",
        "The manual states that the lamp is not red.",
        "The lamp is made of wood.",
    )]
    gate = json.loads((bundle / "v2-gate-lock.json").read_text())["gates"]["fuzzy"]
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "warmup.json").write_text(json.dumps({"load_seconds": load_seconds,
        "smoke_expected_classes": ["entailment", "contradiction", "neutral"], "records": warmup}, indent=2) + "\n")
    destination = args.out / "nli.jsonl"
    done = {row["qid"] for row in p15.read_jsonl(destination)} if destination.exists() else set()
    with destination.open("a", encoding="utf-8") as stream:
        for qid, row in sorted(panel.items()):
            if qid in done:
                continue
            result = verify_one(row, rel[qid], selfcheck[qid], scorer, cfg, pilot, bridge_matches, gate_score, gate)
            p15.append(stream, result)
            done.add(qid)
            print(json.dumps({"task": "cpu_nli", "ok": len(done), "total": len(panel), "utc": p15.utc_now()}), flush=True)
    (args.out / "complete.json").write_text(json.dumps({"n": len(done), "finished_at_utc": p15.utc_now()}) + "\n")


if __name__ == "__main__":
    main()

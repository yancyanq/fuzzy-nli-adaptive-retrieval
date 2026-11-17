"""Score original whole-answer NLI and bridge proxy from the A-only whitelist."""

import json
import math
from pathlib import Path
import sys
from time import perf_counter

from first_round import validate_a
import p15_runner as runner

HERE = Path(__file__).resolve().parent


def main(first_round, snapshot, out):
    cfg = json.loads((HERE / "protocol.json").read_text())
    nli = cfg["nli"]
    if runner.file_hash(snapshot / "model.safetensors") != nli["model_sha256"]:
        raise ValueError("NLI weights do not match the frozen revision")
    sys.path.insert(0, str(HERE / "v2"))
    import torch
    from analyze_pilot_signals_v2 import bridge_matches
    from calibrate_gates_v2 import gate_score, should_retrieve
    from run_pilot import HFNliScorer, build_hypothesis, build_premise

    torch.set_num_threads(nli["threads"])
    torch.set_num_interop_threads(1)
    scorer = HFNliScorer(str(snapshot), "cpu", max_length=nli["input_tokens_max"], batch_size=1)
    if set(scorer.id2label.values()) != {"entailment", "neutral", "contradiction"}:
        raise ValueError("NLI label mapping is incompatible")
    gate = json.loads((HERE / "v2-gate-lock.json").read_text())["gates"]["fuzzy"]
    inputs = runner.read_jsonl(first_round)
    if len({r["qid"] for r in inputs}) != len(inputs) or len(inputs) != sum(cfg["n_by_split"].values()):
        raise ValueError("Unexpected A-only input coverage")
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / "features.tmp"
    with tmp.open("w", encoding="utf-8") as stream:
        for index, row in enumerate(inputs, 1):
            validate_a(row)
            started = perf_counter()
            context = [[chunk["title"], [s["text"] for s in chunk["sentences"]]] for chunk in row["contexts"]]
            premise = build_premise({"context": context}, row["draft_citations"], [0, 1])
            hypothesis = build_hypothesis(row["question"], row["draft_answer"])
            (result,) = scorer.score_many([{"premise": premise["premise"], "hypothesis": hypothesis}])
            probs = result["probs"]
            if (set(probs) != {"entailment", "neutral", "contradiction"}
                    or any(not math.isfinite(value) or not 0 <= value <= 1 for value in probs.values())
                    or not math.isclose(sum(probs.values()), 1, abs_tol=1e-6)):
                raise ValueError("Invalid NLI probabilities")
            entailment = probs["entailment"]
            matches = bridge_matches(context, [0, 1])
            bridge_absent = None if matches is None else not matches
            signal = {"old_nli_risk": 1 - entailment, "bridge_absent": bridge_absent}
            if list(signal) != cfg["features"]:
                raise ValueError("Online feature schema changed")
            runner.append(stream, {"qid": row["qid"], "pool_sha256": row["pool_sha256"],
                "a_prompt_sha256": row["a_prompt_sha256"], "first_round_sha256": runner.digest(row),
                "x": signal, "locked_v2_fuzzy_score": gate_score(gate["kind"], gate["parameters"], 1-entailment, bridge_absent),
                "locked_v2_fuzzy_trigger": should_retrieve(gate, row["qid"], entailment, bridge_absent),
                "nli": result, "nli_input_tokens": min(nli["input_tokens_max"], result["n_tokens"]),
                "retrieved_premise_fallback": premise["used_fallback"], "seconds": perf_counter() - started})
            if index % 25 == 0 or index == len(inputs):
                print(json.dumps({"cpu_scored": index, "n": len(inputs), "recorded_at_utc": runner.utc_now()}), flush=True)
    tmp.replace(out / "features.jsonl")
    (out / "complete.json").write_text(json.dumps({"n": len(inputs), "first_round_sha256": runner.file_hash(first_round),
                                                  "finished_at_utc": runner.utc_now()}) + "\n")


if __name__ == "__main__":
    main(*(Path(arg) for arg in sys.argv[1:]))

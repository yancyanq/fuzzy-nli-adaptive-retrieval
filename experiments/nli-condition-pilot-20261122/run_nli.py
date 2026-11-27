"""Score the frozen P3 pilot inputs using the project's original DeBERTa scorer."""
import argparse
import hashlib
import json
from pathlib import Path
from time import perf_counter

import torch
from run_pilot import HFNliScorer, build_hypothesis, build_premise

WEIGHTS_SHA256 = "c03cd208bf920b4fbbb182a0535859a566e8acc3477d2b536bf87b769978524b"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(args):
    first_round = Path("first_round.jsonl")
    cohort = json.loads(Path("cohort.json").read_text())
    claims_by_qid = json.loads(Path("claims.json").read_text())
    rows = [json.loads(line) for line in first_round.read_text().splitlines()]
    if [row["qid"] for row in rows] != cohort["qid"] or set(claims_by_qid) != set(cohort["qid"]):
        raise ValueError("Frozen cohort and claims differ")
    if sha256(first_round) != cohort["input_sha256"] or sha256(Path("claims.json")) != args.claims_sha256:
        raise ValueError("Frozen inputs changed")
    if sha256(args.snapshot / "model.safetensors") != WEIGHTS_SHA256:
        raise ValueError("DeBERTa weights changed")

    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    model = HFNliScorer(str(args.snapshot), "cpu", max_length=512, batch_size=1)
    started = perf_counter()
    with args.out.open("x", encoding="utf-8") as output:
        for index, row in enumerate(rows):
            if set(row) != {"qid", "pool_sha256", "a_prompt_sha256", "question", "draft_answer", "draft_citations", "contexts"}:
                raise ValueError("Unexpected inputs to NLI")
            contexts = [[c["title"], [s["text"] for s in c["sentences"]]] for c in row["contexts"]]
            premise = build_premise({"context": contexts}, row["draft_citations"], [0, 1])
            claims = claims_by_qid[row["qid"]]
            groups = [("old", [build_hypothesis(row["question"], row["draft_answer"])])]
            if claims:
                if len(claims) != 2 or any(not isinstance(c, str) or not c.strip() for c in claims):
                    raise ValueError("Each covered question needs two frozen claims")
                groups.extend((("joint", [" ".join(claims)]), ("conditions", claims)))
            order = index % len(groups)
            results = {}
            for name, hypotheses in groups[order:] + groups[:order]:
                start = perf_counter()
                scores = model.score_many([{"premise": premise["premise"], "hypothesis": h} for h in hypotheses])
                seconds = perf_counter() - start
                results[name] = {
                    "risk": 1 - min(score["probs"]["entailment"] for score in scores),
                    "seconds": seconds, "nli_input_tokens": sum(min(512, score["n_tokens"]) for score in scores),
                    "scores": scores,
                }
            json.dump({"qid": row["qid"], "pool_sha256": row["pool_sha256"],
                       "a_prompt_sha256": row["a_prompt_sha256"], "premise_titles": premise["titles"],
                       "used_premise_fallback": premise["used_fallback"],
                       "used_whole_fallback": not claims, "methods": results}, output, ensure_ascii=False)
            output.write("\n")
            output.flush()
            print(f"completed {index+1}/{len(rows)} ({perf_counter()-started:.1f}s)", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--claims-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    run(parser.parse_args())

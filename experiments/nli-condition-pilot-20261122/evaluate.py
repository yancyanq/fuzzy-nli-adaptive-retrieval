"""Join locally scored P3 A/B labels after the CPU-only pilot has completed."""
import argparse
import hashlib
import json
from pathlib import Path
from statistics import mean, median


HERE = Path(__file__).resolve().parent
P3 = HERE.parents[1] / "exp" / "v3" / "p3"
METHODS = ("old", "joint", "conditions")


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def index(path):
    items = rows(path)
    lookup = {r["qid"]: r for r in items}
    if len(lookup) != len(items):
        raise ValueError(f"Repeated question in {path}")
    return lookup


def tie(qid):
    return hashlib.sha256(f"42:{qid}".encode()).hexdigest()


def main(run_dir):
    cohort = json.loads((HERE / "cohort.json").read_text())
    nli = index(run_dir / "nli.jsonl")
    archived = index(P3 / "remote-evidence" / "features" / "features.jsonl")
    labels = index(P3 / "analysis" / "offline_labels.jsonl")
    if set(nli) != set(cohort["qid"]):
        raise ValueError("A scored route is missing")
    budget = cohort["retrieval_budget"]
    items = []
    for qid in cohort["qid"]:
        raw, old, label = nli[qid], archived[qid], labels[qid]
        for key in ("pool_sha256", "a_prompt_sha256"):
            if not raw[key] == old[key] == label[key]:
                raise ValueError(f"Input identity mismatch for {qid}")
        if label["split"] != "validation":
            raise ValueError("Non-development label in pilot")
        scores = raw["methods"]
        for method in METHODS:
            if method not in scores and not raw["used_whole_fallback"]:
                raise ValueError(f"Missing score for {qid}, {method}")
        items.append({"qid": qid, "a_f1": label["a_f1"], "b_f1": label["b_f1"],
                      "delta": label["delta_f1"], "fallback": raw["used_whole_fallback"],
                      "archived_diff": abs(old["x"]["old_nli_risk"] - scores["old"]["risk"]),
                      "results": {method: scores.get(method, scores["old"]) for method in METHODS}})

    pos = [r for r in items if r["delta"] > 0]
    neg = [r for r in items if r["delta"] <= 0]
    base = mean(r["a_f1"] for r in items)
    summary = {"n": len(items), "budget": budget, "positive": len(pos), "tied": sum(r["delta"] == 0 for r in items),
               "worsened": sum(r["delta"] < 0 for r in items), "all_a_f1": base,
               "all_b_f1": mean(r["b_f1"] for r in items),
               "archived_baseline_max_score_delta": max(r["archived_diff"] for r in items),
               "condition_coverage": sum(not r["fallback"] for r in items), "methods": {}}
    if summary["archived_baseline_max_score_delta"] > 1e-4:
        raise ValueError("Rerun of the original scorer deviates from the archived baseline")

    for method in METHODS:
        def risk(row):
            return row["results"][method]["risk"]

        chosen = sorted(items, key=lambda r: (-risk(r), tie(r["qid"]), r["qid"]))[:budget]
        chosen_ids = {r["qid"] for r in chosen}
        for row in items:
            row.setdefault("selected", {})[method] = row["qid"] in chosen_ids
        summary["methods"][method] = {
            "f1": base + sum(r["delta"] for r in chosen) / len(items),
            "auroc": mean(1. if risk(a) > risk(b) else .5 if risk(a) == risk(b) else 0. for a in pos for b in neg),
            "improved_selected": sum(r["delta"] > 0 for r in chosen),
            "tied_selected": sum(r["delta"] == 0 for r in chosen),
            "worsened_selected": sum(r["delta"] < 0 for r in chosen),
            "chosen_ids": [r["qid"] for r in chosen],
            "truncated_calls": sum(score["truncated"] for r in items for score in r["results"][method]["scores"]),
            "nli_calls": sum(len(r["results"][method]["scores"]) for r in items),
            "mean_nli_seconds": mean(r["results"][method]["seconds"] for r in items),
            "median_nli_seconds": median(r["results"][method]["seconds"] for r in items),
            "mean_nli_tokens": mean(r["results"][method]["nli_input_tokens"] for r in items),
        }

    generation = run_dir / "generation.jsonl"
    if generation.exists():
        generated = index(generation)
        claims = json.loads((run_dir / "claims.json").read_text())
        if set(generated) != set(nli) or set(claims) != set(nli) or any(
            generated[qid]["claims"] != claims[qid]
            or bool(claims[qid]) == nli[qid]["used_whole_fallback"]
            for qid in nli
        ):
            raise ValueError("Generation evidence differs from scored inputs")
        summary["generation"] = {
            "requests": sum(r["requests"] for r in generated.values()),
            "success": sum(bool(r["claims"]) for r in generated.values()),
            "abstentions": sum(r["reason"] == "abstention" for r in generated.values()),
            "mean_prompt_tokens_all_cases": mean(r["prompt_tokens"] for r in generated.values()),
            "mean_output_tokens_all_cases": mean(r["output_tokens"] for r in generated.values()),
            "mean_request_seconds_all_cases": mean(r["seconds"] for r in generated.values()),
            "parallel_workers": 4,
        }

    result = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    (run_dir / "summary.json").write_text(result)
    (run_dir / "scored.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in items))
    print(result, end="")


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--run-dir", type=Path, default=HERE)
    main(cli.parse_args().run_dir)

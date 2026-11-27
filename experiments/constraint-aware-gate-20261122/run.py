"""Fit course-project gates on P3 100 and replay fixed-budget decisions."""
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
from statistics import mean
import sys
from time import perf_counter

import numpy as np

from constraints import compute


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
P3 = ROOT / "exp/v3/p3"
P5 = ROOT / "exp/v3/p5"
sys.path.insert(0, str(P5))
from policy import score_policy


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path):
    with path.open(encoding="utf-8") as stream:
        yield from map(json.loads, stream)


def index(items, *keys):
    lookup = {}
    for item in items:
        key = tuple(item[k] for k in keys)
        if len(keys) == 1:
            key = key[0]
        if key in lookup:
            raise ValueError(f"Duplicate record: {key}")
        lookup[key] = item
    return lookup


@dataclass(frozen=True)
class Case:
    qid: str
    risk: float
    bridge: bool | None
    gap: float
    type_name: str | None
    type_mismatch: bool
    missing: tuple[str, ...]
    a_f1: float
    b_f1: float
    a_tokens: int
    b_tokens: int
    scoring_seconds: float

    @property
    def gain(self):
        return self.b_f1 - self.a_f1


def make_case(qid, question, draft, contexts, risk, bridge, pair_f1, pair_tokens):
    started = perf_counter()
    text = " ".join(c["title"] + " " + " ".join(s["text"] for s in c["sentences"]) for c in contexts)
    signals = compute(question, draft, text)
    return Case(qid, risk, bridge, signals.gap, signals.answer_type, bool(signals.type_mismatch),
                signals.missing, *pair_f1, *pair_tokens, perf_counter() - started)


def development(qids):
    qids = set(qids)
    first = index((r for r in rows(P3 / "remote-evidence/qwen/first_round.jsonl") if r["qid"] in qids), "qid")
    features = index((r for r in rows(P3 / "remote-evidence/features/features.jsonl") if r["qid"] in qids), "qid")
    pairs = index((r for r in rows(P3 / "remote-evidence/qwen/pairs.jsonl") if r["qid"] in qids), "qid")
    labels = index((r for r in rows(P3 / "analysis/offline_labels.jsonl") if r["qid"] in qids), "qid")
    cases = {}
    for qid, draft in first.items():
        old = features[qid]
        a, b = pairs[qid]["calls"]
        label = labels[qid]
        if not draft["pool_sha256"] == old["pool_sha256"] == label["pool_sha256"] == pairs[qid]["pool_sha256"]:
            raise ValueError(f"P3 pool identity differs for {qid}")
        if not draft["a_prompt_sha256"] == a["prompt_sha256"] == label["a_prompt_sha256"] or b["prompt_sha256"] != label["b_prompt_sha256"]:
            raise ValueError(f"P3 prompt identity differs for {qid}")
        signals = old["x"]
        cases[qid] = make_case(qid, draft["question"], draft["draft_answer"], draft["contexts"],
                               signals["old_nli_risk"], signals["bridge_absent"],
                               (label["a_f1"], label["b_f1"]),
                               (a["input_tokens"], a["input_tokens"] + b["input_tokens"]))
    if set(cases) != qids:
        raise ValueError("Missing P3 input")
    return cases


def exploratory():
    ids = set(load(P5 / "input/split.json")["primary_qids"])
    source = P5 / "remote-evidence/live"
    fixed_routes = {"top2", "direct_2plus4", "v2_direct_2plus1"}
    raw = index((r for r in rows(source / "quality.jsonl") if r["pool_size"] == 30 and r["route"] in fixed_routes), "qid", "route")
    metrics = index((r for r in rows(P5 / "analysis/per_question.jsonl") if r["pool_size"] == 30
                     and r["method"] in fixed_routes), "qid", "method")
    features = index((r for r in rows(source / "features.jsonl") if r["pool_size"] == 30), "qid")
    cases = []
    for r in rows(P5 / "input/pools.jsonl"):
        if r["pool_size"] != 30:
            continue
        qid = r["qid"]
        a, b = raw[qid, "top2"], raw[qid, "direct_2plus4"]
        old = features[qid]
        if not a["pool_sha256"] == b["pool_sha256"] == old["pool_sha256"] == r["pool_sha256"]:
            raise ValueError(f"P5 pool identity differs for {qid}")
        contexts = [r["input"]["contexts"][i] for i in a["paragraph_indices"]]
        am, bm = metrics[qid, "top2"], metrics[qid, "direct_2plus4"]
        valid_b = a["ok"] and b["ok"]
        select_b_tokens = a["calls"][0]["input_tokens"] + bm["input_tokens"] if a["ok"] else am["input_tokens"]
        if a["ok"] and not b["ok"]:
            select_b_tokens += am["input_tokens"] - a["calls"][0]["input_tokens"]
        cases.append(make_case(qid, r["input"]["question"], a["answer"], contexts, old["risk"], old["bridge"],
                               (am["answer_f1"], bm["answer_f1"] if valid_b else am["answer_f1"]),
                               (am["input_tokens"], select_b_tokens)))
    if len(cases) != len(ids) or {c.qid for c in cases} != ids:
        raise ValueError("Missing P5 input")
    direct = {"f1": mean(metrics[q, "v2_direct_2plus1"]["answer_f1"] for q in ids),
              "avg_qwen_input_tokens": mean(metrics[q, "v2_direct_2plus1"]["input_tokens"] for q in ids)}
    return cases, direct


def design(cases, fuzzy, enriched, cfg):
    vectors = []
    for c in cases:
        vector = [c.risk if c.risk is not None else 0.5, 0.5 if c.bridge is None else float(c.bridge)]
        if enriched:
            vector.append(c.gap)
        vectors.append(vector)
    x = np.asarray(vectors, dtype=float)
    if not fuzzy:
        return np.column_stack((np.ones(len(cases)), x))
    high = 1 / (1 + np.exp(-(x - cfg["fuzzy_membership_center"]) / cfg["fuzzy_membership_width"]))
    weights = np.column_stack([np.prod(np.where(bits, high, 1 - high), axis=1)
                               for bits in product((False, True), repeat=x.shape[1])])
    if not np.allclose(weights.sum(axis=1), 1.0):
        raise ValueError("Sugeno rule weights must sum to one")
    return weights


def fit(x, y, alpha, fuzzy):
    penalty = np.eye(x.shape[1])
    if fuzzy:
        target_mean = y.mean()
        return np.linalg.solve(x.T @ x + len(y) * alpha * penalty, x.T @ (y - target_mean)) + target_mean
    penalty[0, 0] = 0.
    return np.linalg.solve(x.T @ x + len(y) * alpha * penalty, x.T @ y)


def by_hash(qid, namespace):
    return sha256(f"{namespace}:{qid}".encode()).hexdigest()


def train(cases, cfg):
    labels = np.array([c.gain for c in cases], dtype=float)
    folds = np.arange(len(cases)) % cfg["fit_folds"]
    models = {}
    for fuzzy, enriched in product((True, False), repeat=2):
        model_name = ("sugeno" if fuzzy else "linear") + ("_constraints" if enriched else "_old")
        x = design(cases, fuzzy, enriched, cfg)
        results = []
        for alpha in cfg["alphas"]:
            scores = np.empty(len(cases))
            for fold in range(cfg["fit_folds"]):
                test = folds == fold
                scores[test] = x[test] @ fit(x[~test], labels[~test], alpha, fuzzy)
            results.append({"alpha": alpha, "oof_mse": float(np.mean((scores - labels) ** 2))})
        best = min(results, key=lambda r: (r["oof_mse"], -r["alpha"]))
        weights = fit(x, labels, best["alpha"], fuzzy)
        models[model_name] = {"fuzzy": fuzzy, "enriched": enriched, "weights": weights.tolist(),
                              "alpha": best["alpha"], "regularization_search": results}
    return models


def evaluate(cases, models, cfg, p4_model):
    scores = {name: design(cases, m["fuzzy"], m["enriched"], cfg) @ np.asarray(m["weights"])
              for name, m in models.items()}
    scores["nli_only"] = [c.risk for c in cases]
    scores["p4_sugeno_archived"] = [score_policy(p4_model, c.risk, c.bridge, None) for c in cases]
    budget = len(cases) * cfg["budget_percent"] // 100
    eligible = [i for i, c in enumerate(cases) if c.risk is not None]
    selections, results = {}, {}
    for name, values in scores.items():
        order = sorted(eligible, key=lambda i: (-values[i], by_hash(cases[i].qid, cfg["tie_seed"]), cases[i].qid))
        chosen = set(order[:budget])
        selections[name] = chosen
        results[name] = {"f1": mean(c.b_f1 if i in chosen else c.a_f1 for i, c in enumerate(cases)),
                         "selected_improve": sum(cases[i].gain > 0 for i in chosen),
                         "selected_tie": sum(cases[i].gain == 0 for i in chosen),
                         "selected_worsen": sum(cases[i].gain < 0 for i in chosen),
                         "avg_qwen_input_tokens": mean(c.b_tokens if i in chosen else c.a_tokens for i, c in enumerate(cases))}
    details = [{"qid": c.qid, "risk": c.risk, "bridge": c.bridge, "constraint_gap": c.gap,
                "type": c.type_name, "type_mismatch": c.type_mismatch, "missing": c.missing, "a_f1": c.a_f1,
                "b_f1": c.b_f1, "selected": {name: i in chosen for name, chosen in selections.items()},
                "scores": {name: float(v[i]) if v[i] is not None else None for name, v in scores.items()}}
               for i, c in enumerate(cases)]
    summary = {"n": len(cases), "budget": budget, "better_if_b": sum(c.gain > 0 for c in cases),
               "first_only_f1": mean(c.a_f1 for c in cases), "all_b_f1": mean(c.b_f1 for c in cases),
               "signal_counts": {"type": dict(Counter(c.type_name for c in cases if c.type_name)),
                                 "type_mismatch": sum(c.type_mismatch for c in cases),
                                 "missing": sum(bool(c.missing) for c in cases), "gap": sum(c.gap > 0 for c in cases)},
               "mean_constraint_feature_ms": mean(c.scoring_seconds for c in cases) * 1000,
               "methods": results}
    return summary, details


def main():
    cfg = load(HERE / "protocol.json")
    split = load(P3 / "input/cohorts.json")["qids"]
    prior = set(load(HERE.parent / "nli-condition-pilot-20261122/cohort.json")["qid"])
    check = sorted(set(split["validation"]) - prior)
    dev = development(split["train"] + split["validation"])
    if len(check) != 20 or len(split["train"]) != 100 or not prior <= set(split["validation"]):
        raise ValueError("Unexpected pilot split")
    train_ids = sorted(split["train"], key=lambda qid: by_hash(qid, "constraint-aware-fit"))
    models = train([dev[q] for q in train_ids], cfg)
    p4 = load(P5 / "policy_lock.json")["models"]["full_sugeno_seed42"]
    primary, primary_details = evaluate([dev[q] for q in check], models, cfg, p4)
    p5_cases, direct = exploratory()
    p5, p5_details = evaluate(p5_cases, models, cfg, p4)
    p5["fixed_direct_2plus1"] = direct
    report = {"protocol_sha256": sha256((HERE / "protocol.json").read_bytes()).hexdigest(),
              "signal_code_sha256": sha256((HERE / "constraints.py").read_bytes()).hexdigest(),
              "fit_qids": train_ids, "primary_qids": check, "models": models, "development_check": primary,
              "p5_posthoc_replay": p5}
    (HERE / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    (HERE / "cases.jsonl").write_text("".join(json.dumps({"split": group, **r}, ensure_ascii=False) + "\n"
                                              for group, block in (("dev", primary_details), ("p5", p5_details))
                                              for r in block))
    print(json.dumps({"development_check": primary, "p5_posthoc_replay": p5}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

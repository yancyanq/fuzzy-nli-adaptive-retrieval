"""Fixed policy scores and a per-question decision boundary."""

import hashlib
import math


def key(score, qid, seed):
    return -score, hashlib.sha256(f"{seed}:{qid}".encode()).hexdigest(), qid


def score_policy(model, risk, bridge, selfcheck):
    kind = model["kind"]
    p = model.get("parameters")
    if kind == "constant":
        return p
    if kind == "selfcheck":
        return selfcheck
    if risk is None:
        return None
    if kind == "nli_only" or bridge is None:
        return risk
    if kind == "linear":
        return max(-1., min(1., p[0] + p[1]*risk + p[2]*bridge))
    if kind == "sugeno":
        h_r = 1 / (1 + math.exp(-(risk-p["center_r"]) / p["width_r"]))
        h_g = 1 / (1 + math.exp(-(bridge-p["center_bridge"]) / p["width_bridge"]))
        return (1-h_r)*(1-h_g)*p["LL"] + (1-h_r)*h_g*p["LH"] + h_r*(1-h_g)*p["HL"] + h_r*h_g*p["HH"]
    if kind == "weighted":
        return (risk + bridge)/2
    if kind == "crisp":
        high = float(risk >= (p["lo"] + p["hi"])/2)
    elif kind == "fixed_fuzzy":
        high = max(0., min(1., (risk-p["lo"]) / (p["hi"]-p["lo"])))
    else:
        raise ValueError(f"Unrecognized scorer {kind}")
    return (1-p["bridge_weight"])*high + p["bridge_weight"]*bridge


def decide(locked, method, budget, qid, risk, bridge, selfcheck):
    model = locked["models"][method]
    if (model["kind"] not in {"constant", "selfcheck", "nli_only"} and bridge is None and risk is not None):
        if method == "v2_native":
            score = risk
        else:
            score = risk
            method = "nli_only"
    else:
        score = score_policy(model, risk, bridge, selfcheck)
    if score is None:
        return False, None, "unavailable_retain_a"
    seed = locked["tie_seed"]
    order = key(score, qid, seed)
    if method == "v2_native":
        limit = tuple(locked["historical_v2_boundary"])
        return (order[0], -risk, order[1], qid) <= limit, score, "native_v2_boundary"
    yes = order <= tuple(locked["boundaries"][method][str(budget)])
    return yes, score, "frozen_score_boundary"

"""Frozen Sugeno rule scoring shared by calibration and fixed-boundary inference."""
from hashlib import sha256
from itertools import product
import json
from math import exp, prod
from pathlib import Path

from dates import compute


def features(pool, answer):
    first = [pool["input"]["contexts"][i] for i in answer["paragraph_indices"]]
    text = " ".join(c["title"] + " " + " ".join(s["text"] for s in c["sentences"]) for c in first)
    return compute(pool["input"]["question"], answer["answer"], text)


def grade(rule, x):
    high = [1 / (1 + exp(-(value - rule["center"]) / rule["width"])) for value in x]
    membership = [prod(p if bit else 1 - p for bit, p in zip(bits, high))
                  for bits in product((False, True), repeat=len(high))]
    return sum(c * w for c, w in zip(rule["weights"], membership))


def ranks(pool, answer, nli, model):
    if nli["risk"] is None or not answer["ok"]:
        return dict.fromkeys(model["rules"])
    x = [nli["risk"], 0.5 if nli["bridge"] is None else float(nli["bridge"])]
    signal = features(pool, answer)
    qid = pool["qid"]
    hashed = sha256(f'{model["tie_seed"]}:{qid}'.encode()).hexdigest()
    return {name: (-grade(rule, x + ([signal.gap] if name == "repaired" else [])), hashed, qid)
            for name, rule in model["rules"].items()}


def triggered(rank, boundary):
    return rank is not None and boundary is not None and rank <= tuple(boundary)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

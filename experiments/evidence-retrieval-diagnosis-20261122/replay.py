"""Test four same-size follow-up retrieval strategies without generating new answers."""
from collections import Counter
import html
import json
from pathlib import Path
import re
import sys
import unicodedata

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
EXP = PROJECT / "exp"
P3 = EXP / "v3/p3"
TEST = HERE.parent / "constraint-gate-calibrated-20261122/test"
sys.path.insert(0, str(EXP / "v2"))
import compare_models as cm


def rows(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def by_id(path):
    return {r["qid"]: r for r in rows(path)}


def normalize(text):
    text = unicodedata.normalize("NFKC", html.unescape(text)).casefold()
    return " ".join(re.findall(r"[^\W_]+", text))


def mention_scores(question, contexts, first, rest):
    question = f" {normalize(question)} "
    source = [[f" {normalize(sentence)} " for sentence in contexts[i][1]] for i in first]
    values = {}
    for target in rest:
        title = re.sub(r"\s+\([^()]+\)\s*$", "", contexts[target][0])
        key = normalize(title)
        if not key or (len(key.split()) == 1 and len(key) < 6):
            continue
        phrase = f" {key} "
        found = [(a, s) for a, part in enumerate(source) for s, line in enumerate(part) if phrase in line]
        if found:
            values[target] = (phrase not in question, len({a for a, _ in found}),
                              -min(a for a, _ in found), -min(s for _, s in found))
    return values


def proposed(question, contexts, first, original):
    documents = [cm.para_text(title, sentences) for title, sentences in contexts]
    rest = [i for i in range(len(contexts)) if i not in first]
    scores = cm.BM25Okapi([cm.tok(documents[i]) for i in rest])
    raw = scores.get_scores(cm.tok(question))
    qr = sorted(rest, key=lambda j: (-raw[rest.index(j)], j))
    title, body = contexts[first[0]]
    expanded = scores.get_scores(cm.tok(question + " " + title + " " + (body[0] if body else "")))
    er = sorted(rest, key=lambda j: (-expanded[rest.index(j)], j))
    if er[:4] != original:
        raise ValueError("Original retrieval does not reproduce")
    qrank = {item: i for i, item in enumerate(qr)}
    erank = {item: i for i, item in enumerate(er)}
    mentions = mention_scores(question, contexts, first, rest)
    fused = sorted(rest, key=lambda i: (-(1 / (10 + qrank[i]) + 1 / (10 + erank[i])), i))
    connected = sorted(mentions, key=lambda i: (mentions[i], -qrank[i], -erank[i], -i), reverse=True)

    def fill(prioritized, remainder):
        return list(dict.fromkeys(prioritized + remainder))[:4]

    return {"existing": original, "question_only": qr[:4], "rank_fusion": fused[:4],
            "bridge_titles": fill(connected[:2], fused)}


def panel(pools, gold, first_records, second_records, routing=None):
    result = []
    for q, row in pools.items():
        src = row["input"]
        chunks = src["contexts"]
        ex = {"question": src["question"], "context": [[p["title"], [s["text"] for s in p["sentences"]]] for p in chunks]}
        first, b = cm.retrieve_indices(ex, 2, 4)
        a_record = first_records[q]
        if [chunks[i]["chunk_id"] for i in first] != a_record["chunk_ids"]:
            raise ValueError(f"Archived A path differs for {q}")
        if q in second_records and [chunks[i]["chunk_id"] for i in first + b] != second_records[q]["chunk_ids"]:
            raise ValueError(f"Archived B path differs for {q}")
        want = {p["chunk_id"] for p in gold[q]["supporting_facts"]}
        pool_ids = {p["chunk_id"] for p in chunks}
        if not want or not want <= pool_ids:
            raise ValueError("Bad reference pool")
        scores = {}
        for method, extra in {"first_two": [], **proposed(ex["question"], ex["context"], first, b)}.items():
            if method != "first_two" and (len(extra) != 4 or len(set(first + extra)) != 6):
                raise ValueError("Different comparison budget")
            ids = [chunks[i]["chunk_id"] for i in first + extra]
            k = sum(x in want for x in ids)
            scores[method] = {"hits": k, "total": len(want), "complete": k == len(want), "chunk_ids": ids}
        result.append({"qid": q, "methods": scores, "previously_triggered": routing is not None and q in routing})
    return result


def summarize(records, use_gate=False):
    n = len(records)
    out = {}
    for method in records[0]["methods"]:
        vals = [r["methods"][method if not use_gate or r["previously_triggered"] else "first_two"] for r in records]
        out[method] = {"complete_cases": sum(v["complete"] for v in vals),
                       "mean_support_paragraph_recall": sum(v["hits"] / v["total"] for v in vals) / n}
    return out


def main():
    qids = set(read(P3 / "input/cohorts.json")["qids"]["train"])
    train_pools = {r["qid"]: r for r in rows(P3 / "input/pools.jsonl") if r["qid"] in qids}
    pairs = by_id(P3 / "remote-evidence/qwen/pairs.jsonl")
    train_gold = by_id(P3 / "input/evaluation_only/gold.jsonl")
    train = panel(train_pools, train_gold, {q: pairs[q]["calls"][0] for q in qids},
                  {q: pairs[q]["calls"][1] for q in qids})
    train_results = summarize(train)
    choices = ("question_only", "rank_fusion", "bridge_titles")
    chosen = max(choices, key=lambda name: (train_results[name]["complete_cases"],
                                           train_results[name]["mean_support_paragraph_recall"]))
    test = panel(by_id(TEST / "pools.jsonl"), by_id(TEST / "evaluation_gold.jsonl"), by_id(TEST / "a.jsonl"),
                 by_id(TEST / "b.jsonl"), set(read(TEST / "plan.json")["routes"]["repaired"]))
    forced = summarize(test)
    fixed = summarize(test, use_gate=True)
    assert fixed["existing"]["complete_cases"] == 18
    switch = Counter((r["methods"]["existing"]["complete"], r["methods"][chosen]["complete"]) for r in test)
    report = {"scope": "Retrieval-only retrospective on archived pools. No model generation, answer evaluation, or token inference.",
              "n_previously_used_training_cases": len(train), "n_existing_test_cases": len(test),
              "training_all_follow_up": train_results, "chosen_variant_from_training": chosen,
              "test_all_follow_up": forced, "test_fixed_prior_eight_triggers": fixed,
              "test_all_follow_up_chosen_vs_existing": {"gains": switch[False, True],
                                                       "losses": switch[True, False]}}
    (HERE / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    (HERE / "test_cases.jsonl").write_text("".join(json.dumps(row) + "\n" for row in test))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

"""Shared prompt definitions used for pre-fit length audit and for P5 inference."""


def example_from_pool(row):
    payload = row["input"]
    return {"_id": row["qid"], "question": payload["question"],
            "context": [[c["title"], [s["text"] for s in c["sentences"]]] for c in payload["contexts"]]}


def route_indices(v2, ex, route):
    if route == "no_context":
        return []
    if route == "full":
        return list(range(len(ex["context"])))
    if route in {"top2", "top3", "top6"}:
        return v2.retrieve_indices(ex, int(route[-1]), 0)[0]
    size = {"v2_direct_2plus1": 1, "direct_2plus4": 4}[route]
    first, extra = v2.retrieve_indices(ex, 2, size)
    return first + extra


def answer_messages(v2, ex, indices, route):
    if route == "no_context":
        return [{"role": "system", "content": "Answer the question with a short span (a name, number, yes/no, or a few words). Output one line in the format ANSWER: <answer>."},
                {"role": "user", "content": ex["question"]}]
    return v2.build_messages(ex, indices)

"""Project an A result onto the whitelist consumed by the online feature worker."""


def project_a(row, first, parse_response):
    call_context = first["chunk_ids"]
    if not first["ok"] or first["prompt_path"] != "top2" or len(set(call_context)) != 2:
        raise ValueError("Expected a successful top-2 result")
    source = {chunk["chunk_id"]: chunk for chunk in row["input"]["contexts"]}
    parsed = parse_response(first["raw"])
    citations = [idx for idx in parsed["citations"] if 1 <= idx <= len(call_context)]
    if parsed["answer"] != first["answer"] or sorted({call_context[idx - 1] for idx in citations}) != first["cited_chunk_ids"]:
        raise ValueError("Cached first answer or citations do not match their raw response")
    return {
        "qid": row["qid"], "pool_sha256": row["pool_sha256"],
        "a_prompt_sha256": first["prompt_sha256"], "question": row["input"]["question"],
        "draft_answer": first["answer"], "draft_citations": citations,
        "contexts": [source[chunk_id] for chunk_id in call_context],
    }


def validate_a(row):
    if set(row) != {"qid", "pool_sha256", "a_prompt_sha256", "question", "draft_answer", "draft_citations", "contexts"}:
        raise ValueError("Unexpected online first-round field")
    if len(row["contexts"]) != 2 or len({chunk["chunk_id"] for chunk in row["contexts"]}) != 2:
        raise ValueError("Online features must receive two distinct first-round paragraphs")
    for chunk in row["contexts"]:
        if set(chunk) != {"chunk_id", "title", "sentences"}:
            raise ValueError("Unexpected online paragraph field")
        for index, sentence in enumerate(chunk["sentences"]):
            if set(sentence) != {"sentence_id", "text"} or sentence["sentence_id"] != f"{chunk['chunk_id']}:{index}":
                raise ValueError("Unexpected online sentence field or ID")

"""Build and audit P1 development pools from the pinned HotpotQA train split."""

import argparse
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
import hashlib
from itertools import combinations
import json
from pathlib import Path
import re
import unicodedata

from pyarrow.parquet import ParquetFile
from rank_bm25 import BM25Okapi


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
WORD = re.compile(r"[^\W_]+", re.UNICODE)
LITERAL_ANSWER_EXCLUSIONS = {"", "yes", "no", "noanswer", "no answer"}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_rows(path, rows):
    with path.open("wb") as stream:
        for row in rows:
            stream.write(canonical(row) + b"\n")


def normalized(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def words(text):
    return WORD.findall(normalized(text))


def lexical(text):
    return " ".join(words(text))


@lru_cache(maxsize=8192)
def normalized_sentences(sentences):
    return frozenset(phrase for sentence in sentences if (phrase := lexical(sentence)))


@dataclass(frozen=True)
class Chunk:
    title: str
    sentences: tuple[str, ...]
    chunk_id: str

    @classmethod
    def from_text(cls, title, sentences):
        return cls(title, tuple(sentences), digest([title, sentences]))

    @property
    def body(self):
        return " ".join(self.sentences)

    def as_online(self):
        return {
            "chunk_id": self.chunk_id, "title": self.title,
            "sentences": [{"sentence_id": f"{self.chunk_id}:{i}", "text": text}
                          for i, text in enumerate(self.sentences)],
        }


@lru_cache(maxsize=8192)
def fingerprints(chunk, shingle_size, min_sentence_words):
    tokens = words(chunk.body)
    shingles = frozenset(zip(*(tokens[i:] for i in range(shingle_size))))
    sentences = [words(sentence) for sentence in chunk.sentences]
    long_sentences = frozenset(tuple(tokens) for tokens in sentences if len(tokens) >= min_sentence_words)
    return normalized(chunk.title), normalized(chunk.body), shingles, long_sentences


def duplicate(left, right, rules):
    args = (rules["word_shingles"], rules["minimum_shared_sentence_words"])
    title_a, body_a, grams_a, sentences_a = fingerprints(left, *args)
    title_b, body_b, grams_b, sentences_b = fingerprints(right, *args)
    if title_a == title_b or body_a == body_b or not sentences_a.isdisjoint(sentences_b):
        return True
    intersection = len(grams_a & grams_b)
    if not intersection:
        return False
    smaller = min(len(grams_a), len(grams_b))
    union = len(grams_a) + len(grams_b) - intersection
    return (intersection / union >= rules["jaccard"]
            or (smaller >= rules["minimum_containment_shingles"]
                and intersection / smaller >= rules["containment"]))


def eligible_development(pilot, config):
    selected, skipped = [], []
    for item in pilot:
        chunks = [Chunk.from_text(title, sentences) for title, sentences in item["context"]]
        reason = None
        if item["type"] != "bridge" or len(chunks) != 10:
            reason = "not_bridge_with_ten_original_paragraphs"
        elif any(duplicate(a, b, config["near_duplicate"]) for a, b in combinations(chunks, 2)):
            reason = "base_duplicate"
        if reason:
            skipped.append({"qid": item["_id"], "original_paragraphs": len(chunks), "reason": reason})
            continue
        selected.append((item, chunks))
        if len(selected) == config["dev_n"]:
            return selected, skipped
    raise ValueError("Insufficient eligible historical pilot questions")


def train_donors(shards, validation_ids, config):
    train_ids = [qid for path in shards for qid in ParquetFile(path).read(columns=["id"])["id"].to_pylist()]
    if len(train_ids) != len(set(train_ids)) or set(train_ids) & validation_ids:
        raise ValueError("Train question IDs must be unique and disjoint from upstream validation")
    sample = sorted(train_ids, key=lambda qid: digest(["donor-rows", config["donor_sample_seed"], qid]))
    sample = set(sample[:config["donor_sample_rows"]])
    passages = {}
    for path in shards:
        # The source projection deliberately omits donor questions and both label fields.
        for batch in ParquetFile(path).iter_batches(batch_size=1024, columns=["id", "context"]):
            ids = batch.column(0).to_pylist()
            keep = [i for i, qid in enumerate(ids) if qid in sample]
            if not keep:
                continue
            for row in batch.take(keep).to_pylist():
                context = row["context"]
                passages[row["id"]] = list(zip(context["title"], context["sentences"], strict=True))
    if passages.keys() != sample:
        raise ValueError("Failed to recover all sampled donor rows")
    unique = {}
    for qid in sorted(passages):
        for index, (title, sentences) in enumerate(passages[qid]):
            body = normalized(" ".join(sentences))
            if normalized(title) and body:
                key = (normalized(title), body)
                if key not in unique:
                    unique[key] = (Chunk.from_text(title, sentences), qid, index)
    donors = sorted(unique.values(), key=lambda item: item[0].chunk_id)
    return donors, {
        "train_question_count": len(train_ids), "upstream_validation_qid_overlap": 0,
        "sampled_source_qids": len(sample), "sampled_source_qids_sha256": digest(sorted(sample)),
        "donor_count_after_exact_title_body_pair_dedup": len(donors),
        "donor_index_sha256": digest([[chunk.chunk_id, qid, index] for chunk, qid, index in donors]),
    }


def expand_pool(qid, question, base, donors, bm25, tokenize, config):
    scores = bm25.get_scores(tokenize(question))
    hard_order = sorted(range(len(donors)), key=lambda i: -scores[i])
    random_order = sorted(range(len(donors)), key=lambda i: digest([
        "random-donor", config["random_donor_seed"], qid, donors[i][0].chunk_id,
    ]))
    ordered = {"bm25": iter(hard_order), "random": iter(random_order)}
    chunks = list(base)
    origins = [{"chunk_id": chunk.chunk_id, "mode": "original",
                "source_qid": qid, "paragraph_index": i} for i, chunk in enumerate(base)]
    original_sentences = frozenset().union(*(normalized_sentences(chunk.sentences) for chunk in base))
    for mode in ("bm25", "random") * ((max(config["sizes"]) - len(base)) // 2):
        for donor_index in ordered[mode]:
            chunk, donor_qid, paragraph_index = donors[donor_index]
            if (config["reject_normalized_original_sentence_copies_in_supplements"]
                    and not original_sentences.isdisjoint(normalized_sentences(chunk.sentences))):
                continue
            if any(duplicate(chunk, existing, config["near_duplicate"]) for existing in chunks):
                continue
            chunks.append(chunk)
            origins.append({"chunk_id": chunk.chunk_id, "mode": mode,
                            "source_qid": donor_qid, "paragraph_index": paragraph_index})
            break
        else:
            raise ValueError(f"Insufficient eligible {mode} donors for {qid}")
    return chunks, origins


def audit_labels(item, base, added, origins):
    by_title = {chunk.title: chunk for chunk in base}
    support = []
    gold_sentences = set()
    for title, index in item["supporting_facts"]:
        if title not in by_title or not 0 <= index < len(by_title[title].sentences):
            raise ValueError(f"Unresolvable original gold sentence: {item['_id']} / {title} / {index}")
        chunk = by_title[title]
        sentence = lexical(chunk.sentences[index])
        if sentence:
            gold_sentences.add(sentence)
        support.append({"chunk_id": chunk.chunk_id, "sentence_id": f"{chunk.chunk_id}:{index}",
                        "title": title, "source_sentence_index": index})
    if not support:
        raise ValueError(f"No original support: {item['_id']}")
    label = {"qid": item["_id"], "answer": item["answer"], "supporting_facts": support}
    literal = lexical(item["answer"])
    matching = []
    for chunk, origin in zip(added, origins, strict=True):
        candidates = [(None, chunk.title), *enumerate(chunk.sentences)]
        clues = []
        for index, text in candidates:
            phrase = lexical(text)
            repeated_gold = index is not None and phrase in gold_sentences
            answer_hit = (literal not in LITERAL_ANSWER_EXCLUSIONS and f" {literal} " in f" {phrase} ")
            if repeated_gold or answer_hit:
                clues.append({"sentence_index": index, "text": text, "answer_phrase_hit": answer_hit,
                              "exact_gold_sentence_copy": repeated_gold})
        if clues:
            matching.append({"qid": item["_id"], "question": item["question"], "answer": item["answer"],
                             "chunk_id": chunk.chunk_id, "title": chunk.title, "mode": origin["mode"],
                             "matched_text": clues})
    return label, matching


def split_plan(development, validation, history, config):
    old = {role: set(ids) for role, ids in history["historical_ids_by_split"].items()}
    excluded = set.union(*old.values()) | set(history["additional_upstream_ids_in_scanned_artifacts"])
    tune = sorted(old["tune"], key=lambda qid: digest(["gate-split", config["split_seed"], qid]))
    heldout_bridge = {row["id"] for row in validation if row["type"] == "bridge"} - excluded
    if (not set(development) <= old["pilot"] or len(tune) != 500 or set(development) & set(tune)
            or (set(development) | set(tune)) & heldout_bridge):
        raise ValueError("Invalid P1 split isolation")
    return {
        "group_key": "qid", "all_sizes_and_order_variants_share_qid_split": True,
        "development": {"source": "V2 pilot; reused for engineering only", "qids": development},
        "conditional_gate_train": {"source": "V2 tune", "qids": tune[:400], "smoke_qids": tune[:100]},
        "conditional_gate_validation": {"source": "V2 tune", "qids": tune[400:], "smoke_qids": tune[400:450]},
        "final": {"status": "undrawn_pending_team_history_and_pre-score_size_lock", "planning_n": 300,
                  "bridge_qid_count_outside_audited_history": len(heldout_bridge), "qid_manifest": None},
        "historical_usage": {"repo_relative_manifest": "exp/v3/p0/manifest.json", "pilot": "development",
                             "tune": "historical tuning", "formal": "historical evaluation only"},
        "unresolvable_upstream_support": history["invalid_gold_sentence_references_also_in_upstream"],
    }


def build(args):
    config = read_json(HERE / "config.json")
    history_path = HERE.parent / "p0/manifest.json"
    history = read_json(history_path)
    pilot_path = REPO / history["input_splits"]["pilot"]["path"]
    shards = [args.train_dir / name for name in config["train_sha256"]]
    inputs = {path: config["train_sha256"][path.name] for path in shards}
    inputs[args.validation] = config["validation_sha256"]
    inputs[pilot_path] = history["input_splits"]["pilot"]["sha256"]
    for path, expected in inputs.items():
        if file_hash(path) != expected:
            raise ValueError(f"Input SHA-256 mismatch: {path}")

    # V2's tokenizer and paragraph renderers are reused in the donor BM25 index.
    import sys
    sys.path.insert(0, str(REPO / "exp/v2"))
    from bm25_topk import para_text, tok

    validation = ParquetFile(args.validation).read(columns=["id", "type"]).to_pylist()
    validation_ids = {row["id"] for row in validation}
    donors, corpus = train_donors(shards, validation_ids, config)
    selected, skipped = eligible_development(read_json(pilot_path), config)
    bm25 = BM25Okapi([tok(para_text(chunk.title, chunk.sentences)) for chunk, _, _ in donors])
    pools, labels, review, provenance, positions = [], [], [], [], []
    for item, base in selected:
        qid = item["_id"]
        chunks, origins = expand_pool(qid, item["question"], base, donors, bm25, tok, config)
        provenance.append({"qid": qid, "selection_order": origins})
        label, review_rows = audit_labels(item, base, chunks[len(base):], origins[len(base):])
        labels.append(label)
        review.extend(review_rows)
        earlier_ids = []
        for size in config["sizes"]:
            n_extra = (size - len(base)) // 2
            counts = Counter(row["mode"] for row in origins[:size])
            if counts != Counter(original=10, bm25=n_extra, random=n_extra):
                raise ValueError(f"Unexpected construction counts for {qid} / {size}")
            ordered = sorted(chunks[:size], key=lambda chunk: digest([
                "presentation", config["presentation_seed"], qid, chunk.chunk_id,
            ]))
            order_ids = [chunk.chunk_id for chunk in ordered]
            if len(set(order_ids)) != size or [x for x in order_ids if x in earlier_ids] != earlier_ids:
                raise ValueError(f"Broken nested pool for {qid} / {size}")
            earlier_ids = order_ids
            payload = {"question": item["question"], "contexts": [chunk.as_online() for chunk in ordered]}
            pools.append({"qid": qid, "pool_size": size, "pool_sha256": digest(payload), "input": payload})
            for chunk_id in sorted({row["chunk_id"] for row in label["supporting_facts"]}):
                positions.append({"qid": qid, "pool_size": size, "chunk_id": chunk_id,
                                  "position_1_based": order_ids.index(chunk_id) + 1})

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "evaluation_only").mkdir(exist_ok=True)
    outputs = {
        "pools.jsonl": pools, "provenance.jsonl": provenance,
        "evaluation_only/gold.jsonl": labels, "evaluation_only/phrase_review.jsonl": review,
        "evaluation_only/evidence_positions.jsonl": positions,
    }
    for name, rows in outputs.items():
        write_rows(args.out / name, rows)
    write_json(args.out / "split_plan.json", split_plan([item["_id"] for item, _ in selected],
                                                       validation, history, config))
    write_json(args.out / "pool_manifest.json", {
        "status": "p1_development_data_only",
        "config_sha256": file_hash(HERE / "config.json"),
        "builder_sha256": file_hash(Path(__file__)),
        "v2_bm25_source_sha256": file_hash(REPO / "exp/v2/bm25_topk.py"),
        "historical_manifest_sha256": file_hash(history_path),
        "inputs_sha256": {
            **{f"train/{path.name}": inputs[path] for path in shards},
            "validation/0000.parquet": inputs[args.validation],
            "exp/step1/pilot.json": inputs[pilot_path],
        },
        "dataset": corpus,
        "n_questions": len(selected), "n_ordered_pools": len(pools),
        "skipped_archived_pilot_rows": skipped,
        "gold_sentence_count": sum(len(row["supporting_facts"]) for row in labels),
        "evidence_position_rows": len(positions),
        "additional_phrase_or_quote_review_rows": len(review),
        "files_sha256": {name: file_hash(args.out / name) for name in (*outputs, "split_plan.json")},
    })
    print(f"Built {len(pools)} pools. Flagged {len(review)} supplemental paragraphs for offline phrase review.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    build(parser.parse_args())


if __name__ == "__main__":
    main()

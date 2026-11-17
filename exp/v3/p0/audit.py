"""Recheck P0 inputs and tokenize archived prompts without model inference."""

import argparse
from collections import Counter
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import re
from statistics import mean
import sys


REPO = Path(__file__).resolve().parents[3]
QWEN_REVISION = "a09a35458c702b33eeacc393d103063234e8bc28"
VALIDATION_SOURCE = (
    "https://huggingface.co/datasets/hotpotqa/hotpot_qa/resolve/"
    "refs%2Fconvert%2Fparquet/distractor/validation/0000.parquet"
)
LIMITS = (4096, 8192, 16384)
HISTORICAL_ID = re.compile(rb"(?<![a-f0-9])[a-f0-9]{24}(?![a-f0-9])")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_preflight_script(path):
    spec = importlib.util.spec_from_file_location("archive_preflight", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def audit_splits(paths, parquet, preflight, other_history):
    splits = {name: read_json(path) for name, path in paths.items()}
    ids = {}
    summaries = {}
    invalid_support = []
    for name, items in splits.items():
        ids[name] = {item["_id"] for item in items}
        assert len(items) == len(ids[name]) == {"pilot": 100, "tune": 500, "formal": 1000}[name]
        assert all(item["type"] == "bridge" for item in items)
        for item in items:
            for title, index in item["supporting_facts"]:
                lengths = [len(sentences) for candidate, sentences in item["context"] if candidate == title]
                if not any(0 <= index < length for length in lengths):
                    invalid_support.append({"split": name, "qid": item["_id"], "title": title,
                                            "sentence_index": index, "matching_paragraph_lengths": lengths})
        summaries[name] = {
            "path": paths[name].relative_to(REPO).as_posix(),
            "sha256": sha256(paths[name]),
            "n": len(items),
            "paragraph_counts": dict(sorted(Counter(len(item["context"]) for item in items).items())),
        }
    historical = set.union(*ids.values())
    assert len(historical) == 1600
    assert sha256(paths["tune"]) == sha256(REPO / "exp/step1/tune.json")

    from pyarrow.parquet import read_table

    upstream = read_table(parquet, columns=["id", "type", "question", "supporting_facts"]).to_pylist()
    assert len({row["id"] for row in upstream}) == len(upstream) == 7405
    bridge = {row["id"]: row for row in upstream if row["type"] == "bridge"}
    assert len(bridge) == 5918
    for items in splits.values():
        for item in items:
            original = bridge[item["_id"]]
            assert original["question"] == item["question"]
            support = original["supporting_facts"]
            assert list(zip(support["title"], support["sent_id"])) == list(map(tuple, item["supporting_facts"]))
    # Scan artifact text only for exact IDs from the upstream data. Synthetic fixtures
    # and incidental hex values cannot expand the exclusion list.
    scanned = [
        path for folder in (REPO / "exp", preflight, *other_history) for path in folder.rglob("*")
        if path.is_file() and path.suffix in {".json", ".jsonl", ".csv", ".log", ".md", ".ipynb"}
        and not path.is_relative_to(REPO / "exp/v3")
    ]
    scanned_ids = {identifier.decode() for path in scanned for identifier in HISTORICAL_ID.findall(path.read_bytes())}
    upstream_ids = {row["id"] for row in upstream}
    additional = (scanned_ids & upstream_ids) - historical
    return splits, {
        "input_splits": summaries,
        "invalid_gold_sentence_references_also_in_upstream": invalid_support,
        "archive_scan_files": len(scanned),
        "additional_upstream_ids_in_scanned_artifacts": sorted(additional),
        "historical_ids_by_split": {name: sorted(values) for name, values in ids.items()},
        "upstream": {
            "source": VALIDATION_SOURCE,
            "sha256": sha256(parquet),
            "validation": len(upstream),
            "bridge": len(bridge),
            "bridge_outside_documented_and_scanned_history": len(bridge.keys() - historical - additional),
        },
    }


def prototype_pools(example, donors, ordering):
    original = example["context"]
    original_titles = {title.casefold().strip() for title, _ in original}
    eligible = [row for row in donors if row[0].casefold().strip() not in original_titles]
    seed = int(hashlib.sha256(("v3-preflight-42:" + example["_id"]).encode()).hexdigest()[:16], 16)
    rng = random.Random(seed)
    subset = rng.sample(eligible, min(500, len(eligible)))
    rank = ordering([title + " " + " ".join(sentences) for title, sentences in subset], example["question"])
    hard = [subset[i] for i in rank[:25]]
    random_extra = rng.sample([subset[i] for i in rank[25:]], 25)
    extras = [row for pair in zip(hard, random_extra) for row in pair]
    return {size: original + extras[:size - 10] for size in (10, 30, 60)}


def length_row(scope, qid, pool, strategy, input_tokens, reserve, archived_input=None, actual_size=None):
    total = input_tokens + reserve
    return dict(
        scope=scope, qid=qid, pool_paragraphs=pool, actual_pool_paragraphs=pool if actual_size is None else actual_size,
        strategy=strategy,
        input_tokens=input_tokens, reserved_output_tokens=reserve, total_tokens=total,
        archived_input_tokens=archived_input,
        **{f"fits_{limit}": int(total <= limit) for limit in LIMITS},
    )


def summarize_lengths(rows):
    groups = {}
    for row in rows:
        key = (row["scope"], row["pool_paragraphs"], row["strategy"])
        groups.setdefault(key, []).append(row)
    return [
        {
            "scope": scope, "pool_paragraphs": pool, "strategy": strategy, "n": len(group),
            "input_min": min(row["input_tokens"] for row in group),
            "input_max": max(row["input_tokens"] for row in group),
            "total_max": max(row["total_tokens"] for row in group),
            **{f"fits_{limit}": sum(row[f"fits_{limit}"] for row in group) for limit in LIMITS},
        }
        for (scope, pool, strategy), group in sorted(groups.items())
    ]


def audit_length(splits, preflight, tokenizer, compare, archive_script):
    def count(messages):
        return len(tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True))

    formal = REPO / "exp/v2/step5_v2"
    examples = {item["_id"]: item for item in splits["formal"]}
    rows = []
    for old in read_jsonl(formal / "answers_test_v2.jsonl"):
        example = examples[old["_id"]]
        indices = old["paragraph_indices"]
        a, extra = compare.retrieve_indices(example, 2, 1)
        assert indices == {"A": a, "B": a + extra, "full": list(range(len(example["context"])))}[old["branch"]]
        length = count(compare.build_messages(example, indices))
        rows.append(length_row("v2_formal", old["_id"], len(example["context"]), old["branch"],
                               length, 128, old["prompt_tokens"]))
    assert len(rows) == len({(row["qid"], row["strategy"]) for row in rows}) == 3000
    formal_matches = sum(row["input_tokens"] == row["archived_input_tokens"] for row in rows)
    assert formal_matches == len(rows)

    donor_path = REPO / "exp/step1/tune.json"
    archived = read_json(preflight / "v3_expanded_preflight.json")
    assert archived["donor_sha256"] == sha256(donor_path)
    assert archived["pilot_sha256"] == sha256(REPO / "exp/step1/pilot.json")
    donors = {}
    for example in read_json(donor_path):
        for title, sentences in example["context"]:
            donors.setdefault((title.casefold().strip(), " ".join(sentences).strip()), [title, sentences])
    assert len(donors) == archived["donor_unique"]
    short = {row["id"]: row for row in read_json(preflight / "v3_qwen_10q_pilot.json")
             if row["strategy"] == "full30"}
    repeated_titles = Counter()
    pool_sizes = {size: Counter() for size in (10, 30, 60)}
    for example in splits["pilot"][:50]:
        for size, pool in prototype_pools(example, list(donors.values()), archive_script.ordering).items():
            pool_sizes[size][len(pool)] += 1
            titles = {title.casefold().strip() for title, _ in pool}
            repeated_titles[size] += len(titles) < len(pool)
            prototype = {"_id": example["_id"], "question": example["question"], "context": pool}
            order = list(range(len(pool)))
            a, extra = compare.retrieve_indices(prototype, 2, 1)
            for strategy, indices in (("A", a), ("B", a + extra), ("full", order)):
                length = count(compare.build_messages(prototype, indices))
                rows.append(length_row("v3_archived_pool_v2_prompt", example["_id"], size, strategy, length, 128,
                                       actual_size=len(pool)))
            if size == 30 and example["_id"] in short:
                passages = "\n".join(f"[{i}] {title}: " + " ".join(sentences)
                                     for i, (title, sentences) in enumerate(pool))
                prompt = ("Answer the question using only the provided evidence. Return a short answer only. "
                          f"If unsupported, say unknown.\nEvidence:\n{passages}\nQuestion: {example['question']}\nAnswer:")
                length = count([{"role": "user", "content": prompt}])
                old = short[example["_id"]]
                assert length == old["input_tokens"]
                rows.append(length_row("v3_notebook_short_prompt", example["_id"], size, "full", length, 32,
                                       old["input_tokens"], len(pool)))
    return rows, {
        "v2_formal_token_counts_matched": formal_matches,
        "notebook_full30_token_counts_matched": len(short),
        "prototype_pools_with_repeated_normalized_titles": dict(repeated_titles),
        "prototype_actual_pool_sizes": pool_sizes,
        "prototype_donor_count": len(donors),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--other-history", action="append", type=Path, default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(REPO / "exp/v2"))
    import compare_models as compare
    from transformers import AutoTokenizer, __version__ as transformers_version
    from tokenizers import __version__ as tokenizers_version

    paths = {"pilot": REPO / "exp/step1/pilot.json",
             "tune": REPO / "exp/v2/tune.json", "formal": REPO / "exp/v2/test.json"}
    splits, manifest = audit_splits(paths, args.validation, args.preflight, args.other_history)
    tokenizer = AutoTokenizer.from_pretrained(str(args.tokenizer), local_files_only=True)
    archive_script = load_preflight_script(args.preflight / "kaggle_preflight.py")
    rows, verification = audit_length(splits, args.preflight, tokenizer, compare, archive_script)
    qa = read_json(args.preflight / "v3_qwen_10q_pilot.json")
    kaggle = {}
    for strategy in sorted({row["strategy"] for row in qa}):
        group = [row for row in qa if row["strategy"] == strategy]
        ok = [row for row in group if row["status"] == "ok"]
        kaggle[strategy] = {"n": len(group), "ok": len(ok), "seconds_sum": sum(row["seconds"] for row in ok),
                            "seconds_mean": mean(row["seconds"] for row in ok)}
    manifest.update({
        "status": "offline_audit_only",
        "heldout_v3_ids_selected": False,
        "qwen_revision": QWEN_REVISION,
        "tokenizer_versions": {"transformers": transformers_version, "tokenizers": tokenizers_version},
        "tokenizer_files": {name: sha256(args.tokenizer / name) for name in ("tokenizer.json", "tokenizer_config.json")},
        "preflight_inputs_sha256": {
            name: sha256(args.preflight / name)
            for name in ("kaggle_preflight.py", "v3_expanded_preflight.json", "v3_qwen_10q_pilot.json")
        },
        "verification": verification,
        "length_summary": summarize_lengths(rows),
        "historical_kaggle_short_prompt_runtime": kaggle,
    })
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "length_audit.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Audited {len(rows)} lengths and {sum(len(items) for items in splits.values())} historical question IDs.")


if __name__ == "__main__":
    main()

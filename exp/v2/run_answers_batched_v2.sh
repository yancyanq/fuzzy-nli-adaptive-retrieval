#!/usr/bin/env bash
# Run from ~/nlp with the matching eight-sequence Qwen service.
set -euo pipefail
export PYTHONPATH="$PWD"
dev=step4_dev
python=.venv_step6a/bin/python
workers=8
mkdir -p "$dev/batches" "$dev/answers"
exec 8>"$dev/batches/write.lock"
flock -n 8
trap 'status=$?; printf "%s\n" "$status" > "$dev/answers.exit"; exit "$status"' EXIT

"$python" - "$workers" <<'PY'
import json
import sys
from pathlib import Path

questions = json.loads(Path("tune.json").read_text(encoding="utf-8"))
assert len(questions) == len({q["_id"] for q in questions}) == 500
workers = int(sys.argv[1])
for index in range(workers):
    shard = Path(f"step4_dev/batches/{index}/tune.json")
    expected = json.dumps(questions[index::workers], ensure_ascii=False)
    shard.parent.mkdir(exist_ok=True)
    if shard.exists() and shard.read_text(encoding="utf-8") != expected:
        raise ValueError(f"Shard changed: {shard}")
    shard.write_text(expected, encoding="utf-8")
PY

pids=()
for ((index=0; index<workers; index++)); do
    shard="$dev/batches/$index"
    "$python" -u "$dev/run_pilot.py" \
        --data "$shard/tune.json" --n 500 --preset custom --base-url http://127.0.0.1:8000/v1 \
        --model Qwen/Qwen2.5-7B-Instruct --k 2 --m 1 --temperature 0 --max-tokens 128 \
        --tie-eps 0 --timeout 120 --skip-nli --audit-n 0 --out "$shard" \
        --cache "$shard/answers.jsonl" >>"$shard/run.log" 2>&1 &
    pids+=("$!")
done
failed=0
for pid in "${pids[@]}"; do
    if ! wait "$pid"; then failed=1; fi
done

"$python" - "$workers" <<'PY'
import json
import sys
from datetime import datetime
from pathlib import Path

root = Path("step4_dev")
questions = json.loads(Path("tune.json").read_text(encoding="utf-8"))
workers = int(sys.argv[1])
valid = {}
for index in range(workers):
    shard = root / "batches" / str(index) / "answers.jsonl"
    if not shard.is_file():
        continue
    records = shard.read_text(encoding="utf-8").splitlines(True)
    ids = {q["_id"] for q in questions[index::workers]}
    retained = []
    for line in records:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = row["_id"], row["branch"]
        if key[0] not in ids or key[1] not in ("A", "B") or key in valid:
            raise ValueError(f"Unexpected or duplicate shard record {key}")
        if (row["model"], row["k"], row["m"]) != ("Qwen/Qwen2.5-7B-Instruct", 2, 1):
            raise ValueError(f"Unexpected model or retrieval parameters for {key}")
        if not row.get("error") and row["content"].strip():
            valid[key] = line.rstrip() + "\n"
            retained.append(valid[key])
    if len(retained) != len(records):
        backup = shard.with_name(f"answers_before_retry_{datetime.now():%Y%m%d_%H%M%S_%f}.jsonl")
        with backup.open("x", encoding="utf-8") as stream:
            stream.writelines(records)
        tmp = shard.with_suffix(".clean.tmp")
        tmp.write_text("".join(retained), encoding="utf-8")
        tmp.replace(shard)

merged = root / "answers" / "answers_v2_dev.jsonl"
tmp = merged.with_suffix(".merge.tmp")
with tmp.open("w", encoding="utf-8") as stream:
    for question in questions:
        for branch in ("A", "B"):
            stream.write(valid.get((question["_id"], branch), ""))
tmp.replace(merged)
print(f"Merged {len(valid)}/1000 validated branches")
sys.exit(0 if len(valid) == 1000 else 1)
PY
exit "$failed"

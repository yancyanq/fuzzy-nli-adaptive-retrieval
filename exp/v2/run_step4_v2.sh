#!/usr/bin/env bash
# Run from ~/nlp on the experiment host after starting run_answers.sh in tmux.
set -euo pipefail
export PYTHONPATH="$PWD"
dev=step4_dev
service=nlp6a-vllm
model_dir=models/dev-deberta-b3546ea
python=.venv_step6a/bin/python
cache="$dev/answers/answers_v2_dev.jsonl"

exec 9>"$dev/finish.lock"
flock -n 9
restore_needed=0
finish() {
    status=$?
    trap - EXIT
    if ((restore_needed)); then
        if ! tmux has-session -t "$service" 2>/dev/null; then
            serve_script=.serve-step6a.sh
            if [ -f .serve-step4.sh ]; then serve_script=.serve-step4.sh; fi
            tmux new-session -d -s "$service" \
                "cd \"\$HOME/nlp\" && bash $serve_script >>step4_dev/vllm_restart.log 2>&1" || status=1
        fi
        ready=0
        for _ in $(seq 1 100); do
            if curl --max-time 3 -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
                ready=1
                break
            fi
            sleep 5
        done
        if ((ready == 0)); then
            printf 'Qwen health check failed after restart\n' >&2
            status=1
        fi
    fi
    printf '%s\n' "$status" > "$dev/finish.exit"
    exit "$status"
}
trap finish EXIT

(cd "$model_dir" && sha256sum -c nli.sha256)
printf 'Waiting for paired generation at %s\n' "$(date -Is)"
while tmux has-session -t nlp-v2-tune 2>/dev/null; do
    sleep 15
done

complete_answers() {
    "$python" - "$cache" <<'PY'
import json
import sys
from datetime import datetime
from pathlib import Path

cache = Path(sys.argv[1])
questions = json.loads(Path("tune.json").read_text(encoding="utf-8"))
expected = {(question["_id"], branch) for question in questions for branch in ("A", "B")}
if not cache.is_file():
    print("No answer cache yet")
    sys.exit(1)
source = cache.read_text(encoding="utf-8")
good = {}
errors = 0
for line in source.splitlines():
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        errors += 1
        continue
    key = (row.get("_id"), row.get("branch"))
    if key not in expected or (row.get("model"), row.get("k"), row.get("m")) != ("Qwen/Qwen2.5-7B-Instruct", 2, 1):
        raise ValueError("Unexpected cache identity")
    if row.get("error") or not row.get("content", "").strip():
        errors += 1
        continue
    if key in good:
        raise ValueError("Duplicate successful answer in the tune cache")
    good[key] = line
print(f"Successful answer branches: {len(good)}/{len(expected)}, failed or incomplete records: {errors}")
if errors:
    backup = cache.with_name(f"answers_before_retry_{datetime.now():%Y%m%d_%H%M%S_%f}.jsonl")
    with backup.open("x", encoding="utf-8") as stream:
        stream.write(source)
    valid_only = cache.with_suffix(".validated.tmp")
    valid_only.write_text("".join(line + "\n" for line in good.values()), encoding="utf-8")
    valid_only.replace(cache)
sys.exit(0 if good.keys() == expected else 1)
PY
}

if ! complete_answers || [ "$(cat "$dev/answers.exit" 2>/dev/null || true)" != 0 ]; then
    printf 'Resuming the original answer command at %s\n' "$(date -Is)"
    bash "$dev/run_answers.sh"
    complete_answers
fi
printf 'Paired answers validated at %s\n' "$(date -Is)"

tmux has-session -t "$service"
restore_needed=1
tmux send-keys -t "$service" C-c
for _ in $(seq 1 60); do
    if ! tmux has-session -t "$service" 2>/dev/null; then
        break
    fi
    sleep 2
done
if tmux has-session -t "$service" 2>/dev/null; then
    printf 'Qwen session did not exit after SIGINT\n' >&2
    exit 1
fi
nvidia-smi --query-gpu=memory.free --format=csv,noheader
printf 'Starting real CUDA NLI at %s\n' "$(date -Is)"
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 "$python" -u "$dev/run_pilot.py" \
    --data tune.json --n 500 --preset custom --base-url http://127.0.0.1:8000/v1 \
    --model Qwen/Qwen2.5-7B-Instruct --k 2 --m 1 --temperature 0 --max-tokens 128 --tie-eps 0 \
    --nli-only --no-cache --answer-cache "$cache" --audit-n 0 \
    --nli-model "$model_dir" --nli-backend hf --nli-device cuda --nli-batch-size 4 --nli-max-length 512 \
    --out "$dev/nli" > "$dev/nli.log" 2>&1

"$python" "$dev/calibrate_gates_v2.py" --tune tune.json \
    --branches "$dev/nli/branches.jsonl" --out "$dev/gates" \
    --serve-script "$(if [ -f .serve-step4.sh ]; then printf '%s' .serve-step4.sh; else printf '%s' .serve-step6a.sh; fi)"
printf 'Calibrated and locked gates at %s\n' "$(date -Is)"

#!/usr/bin/env bash
# Run from ~/nlp in tmux on the experiment host.
set -euo pipefail
export PYTHONPATH="$PWD" PYTHONDONTWRITEBYTECODE=1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=4 MKL_NUM_THREADS=4
out=step5_v2
nli_dir=models/dev-deberta-b3546ea
qwen_dir=models/Qwen2.5-7B-Instruct
service=nlp6a-vllm
python=.venv_step6a/bin/python
common=(--data "$out/test.json" --out "$out" --scorer "$out/hotpot_evaluate_v1.py" --tokenizer "$qwen_dir")
generate=("$python" -u step4_dev/generate_test_v2.py)
evaluate=("$python" -u step4_dev/evaluate_test_v2.py)

exec 9>"$out/run.lock"
flock -n 9
restore_needed=0
ready() {
    curl --max-time 3 -fsS http://127.0.0.1:8000/health >/dev/null 2>&1
}
restore_qwen() {
    if ! tmux has-session -t "=$service" 2>/dev/null; then
        tmux new-session -d -s "$service" "cd \"\$HOME/nlp\" && bash .serve-step4.sh >>step5_v2/vllm_restart.log 2>&1" || return 1
    fi
    for _ in $(seq 1 110); do
        if ready; then return 0; fi
        sleep 4
    done
    printf 'Qwen health check failed after restart\n' >&2
    return 1
}
finish() {
    status=$?
    trap - EXIT
    if ((restore_needed)); then restore_qwen || status=1; fi
    printf '%s\n' "$status" > "$out/finish.exit"
    printf 'Step 5 worker exited with status %s at %s\n' "$status" "$(TZ=Asia/Shanghai date -Is)"
    exit "$status"
}
trap finish EXIT
rm -f "$out/finish.exit"
sha256sum -c "$out/inputs.sha256"
(cd "$nli_dir" && sha256sum -c nli.sha256)
tmux has-session -t "=$service"
ready

if [[ ! -s "$out/latency_device.txt" ]]; then
    printf 'Starting dev evidence and execution-path smoke at %s\n' "$(TZ=Asia/Shanghai date -Is)"
    "${generate[@]}" smoke "${common[@]}" >"$out/dev_selector_smoke.log" 2>&1
    if "${evaluate[@]}" latency-smoke "${common[@]}" --nli-device cuda >"$out/dev_latency_cuda.log" 2>&1; then
        device=cuda
    else
        "${evaluate[@]}" latency-smoke "${common[@]}" --nli-device cpu >"$out/dev_latency_cpu.log" 2>&1
        device=cpu
    fi
    printf '%s\n' "$device" >"$out/latency_device.tmp"
    mv "$out/latency_device.tmp" "$out/latency_device.txt"
fi
device=$(cat "$out/latency_device.txt")
[[ "$device" = cuda || "$device" = cpu ]]
printf 'Starting held-out generation at %s; real-path NLI device %s\n' "$(TZ=Asia/Shanghai date -Is)" "$device"
"${generate[@]}" generate "${common[@]}"
echo "Generation complete at $(TZ=Asia/Shanghai date -Is)"

if [[ ! -s "$out/nli_test_v2.jsonl" || $(wc -l < "$out/nli_test_v2.jsonl") -ne 2000 ]]; then
    service_pane=$(tmux list-panes -t "$service:" -F '#{pane_id}')
    if [[ ! "$service_pane" =~ ^%[0-9]+$ ]]; then
        printf 'Expected exactly one Qwen service pane\n' >&2
        exit 1
    fi
    restore_needed=1
    tmux send-keys -t "$service_pane" C-c
    for _ in $(seq 1 60); do
        if ! tmux has-session -t "=$service" 2>/dev/null; then break; fi
        sleep 2
    done
    if tmux has-session -t "=$service" 2>/dev/null; then
        printf 'Qwen session did not exit after SIGINT\n' >&2
        exit 1
    fi
    printf 'Starting cached-answer CUDA NLI at %s\n' "$(TZ=Asia/Shanghai date -Is)"
    "${evaluate[@]}" nli "${common[@]}" --nli-device cuda >"$out/nli.log" 2>&1
    restore_qwen
    restore_needed=0
fi

"${evaluate[@]}" evaluate "${common[@]}"
"${evaluate[@]}" latency "${common[@]}" --nli-device "$device" >>"$out/latency.log" 2>&1
sha256sum "$out"/{answers_test_v2.jsonl,evidence_test_v2.jsonl,nli_test_v2.jsonl,per_question.csv,quality_summary.json,latency_test_v2.jsonl,latency_summary.json,dev_selector_smoke.json,latency_device.txt} \
    "$out"/predictions/*.json > "$out/results.sha256"

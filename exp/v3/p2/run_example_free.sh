#!/usr/bin/env bash
set -euo pipefail
base="$HOME/group13-v3-p2"
cd "$base"
exec 9>"$PWD/example-free/lock"
flock -n 9

service=group13-p2-example-free-serve
stop_service() {
  if tmux has-session -t "=$service" 2>/dev/null; then
    local pane
    pane=$(tmux list-panes -t "=$service" -F '#{pane_id}')
    if [[ "$pane" =~ ^%[0-9]+$ ]]; then tmux send-keys -t "$pane" C-c; fi
  fi
}
cleanup() {
  local rc=$?
  stop_service || true
  printf 'Example-free selfcheck ended %s status=%s\n' "$(date -Is)" "$rc"
  printf '%s\n' "$rc" >example-free/status
}
trap cleanup EXIT

deadline=$((SECONDS + 2400))
until test -s guided/status; do
  if (( SECONDS >= deadline )); then exit 1; fi
  sleep 5
done
sleep 20
test -z "$(ss -ltnH 'sport = :18082')"
export PYTHONPATH="$HOME/group13-v3-p0/packages"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
printf 'Starting example-free selfcheck at %s\n' "$(date -Is)"
tmux new-session -d -s "$service" "bash '$base/serve.sh' 8192 4 >'$base/example-free/serve.log' 2>&1"
python3 -B example-free/bundle/run_qwen.py --bundle example-free/bundle \
  --tokenizer "$HOME/group13-v3-p0/models/Qwen2.5-7B-Instruct" --out example-free/live-qwen \
  --example-free-selfcheck >example-free/qwen.log 2>&1
stop_service
for i in {1..60}; do
  used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | tr -d ' ')
  if test "$used" -lt 512 && test -z "$(ss -ltnH 'sport = :18082')"; then break; fi
  sleep 1
done
test "$used" -lt 512
test -z "$(ss -ltnH 'sport = :18082')"
nvidia-smi --query-gpu=timestamp,name,memory.used,memory.total,utilization.gpu --format=csv >example-free/gpu-after.csv

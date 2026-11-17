#!/usr/bin/env bash
set -euo pipefail
base="$HOME/group13-v3-p2"
cd "$base"
exec 9>"$PWD/guided/lock"
flock -n 9
stop_guided() {
  if tmux has-session -t '=group13-p2-guided-serve' 2>/dev/null; then
    local pane
    pane=$(tmux list-panes -t '=group13-p2-guided-serve' -F '#{pane_id}')
    if [[ "$pane" =~ ^%[0-9]+$ ]]; then tmux send-keys -t "$pane" C-c || true; fi
  fi
}
cleanup() {
  rc=$?
  stop_guided
  printf '%s\n' "$rc" >guided/status
  printf 'Guided stage ended %s status=%s\n' "$(date -Is)" "$rc"
  exit "$rc"
}
trap cleanup EXIT
deadline=$((SECONDS + 3600))
until test -s logs/nli.status; do
  if test -s logs/qwen.status && test "$(cat logs/qwen.status)" != 0; then exit 1; fi
  if (( SECONDS >= deadline )); then exit 1; fi
  sleep 5
done
test "$(cat logs/nli.status)" = 0
test -z "$(ss -ltnH 'sport = :18082')"
export PYTHONPATH="$HOME/group13-v3-p0/packages"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
printf 'Starting guided rerun at %s\n' "$(date -Is)"
tmux new-session -d -s group13-p2-guided-serve "bash '$base/serve.sh' 8192 4 >'$base/guided/serve.log' 2>&1"
python3 -B guided/bundle/run_qwen.py --bundle guided/bundle --tokenizer "$HOME/group13-v3-p0/models/Qwen2.5-7B-Instruct" \
  --out guided/live-qwen --guided-only >guided/qwen.log 2>&1
stop_guided
for i in {1..60}; do
  used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | tr -d ' ')
  if test "$used" -lt 512 && test -z "$(ss -ltnH 'sport = :18082')"; then break; fi
  sleep 1
done
test "$used" -lt 512
test -z "$(ss -ltnH 'sport = :18082')"
python3 -B guided/bundle/run_nli.py --bundle guided/bundle --qwen guided/live-qwen --snapshot models/deberta-b3546ea \
  --out guided/live-nli >guided/nli.log 2>&1

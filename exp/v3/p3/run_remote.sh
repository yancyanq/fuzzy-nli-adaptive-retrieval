#!/usr/bin/env bash
set -euo pipefail
base="$HOME/group13-v3-p3"
cd "$base"
exec 9>"$PWD/run.lock"
flock -n 9
service=group13-p3-serve
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
  printf 'P3 end %s status=%s\n' "$(date -Is)" "$rc"
  printf '%s\n' "$rc" >status
}
trap cleanup EXIT
test ! -s status
(cd bundle && sha256sum -c bundle.sha256)
test -z "$(ss -ltnH 'sport = :18082')"
export PYTHONPATH="$HOME/group13-v3-p0/packages"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
printf 'P3 start %s\n' "$(date -Is)"
tmux new-session -d -s "$service" "bash '$base/bundle/serve.sh' 8192 4 >'$base/serve.log' 2>&1"
python3 -B bundle/run_smoke.py qwen >qwen.log 2>&1
stop_service
for i in {1..60}; do
  used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | tr -d ' ')
  if test "$used" -lt 512 && test -z "$(ss -ltnH 'sport = :18082')"; then break; fi
  sleep 1
done
test "$used" -lt 512
test -z "$(ss -ltnH 'sport = :18082')"
nvidia-smi --query-gpu=timestamp,name,memory.used,memory.total,utilization.gpu --format=csv >gpu-after.csv
python3 -B bundle/features.py qwen/first_round.jsonl "$HOME/group13-v3-p2/models/deberta-b3546ea" features >features.log 2>&1

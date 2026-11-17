#!/usr/bin/env bash
set -euo pipefail
p15_dir="$HOME/group13-v3-p15"
cd "$p15_dir"
until test -s status; do sleep 2; done
if test "$(cat status)" = 0; then exit; fi
test -s results/8192/complete.json
test ! -e results/16384/complete.json
grep -Fq 'can' driver.log
grep -Fq "find pane: =group13-p15-serve-8192" driver.log
python3 -c 'import json; assert json.load(open("results/8192/complete.json"))["route_records"] == 800'
exec 9>"$p15_dir/run.lock"
flock -w 10 9
mv status status-primary-handoff
printf 'Opening 16384 handoff at %s, preserving original 8192 run.\n' "$(date -Is)"
stop_service() {
  local session="$1"
  if tmux has-session -t "=$session" 2>/dev/null; then
    local pane
    pane=$(tmux list-panes -t "=$session" -F '#{pane_id}')
    [[ "$pane" =~ ^%[0-9]+$ ]]
    tmux send-keys -t "$pane" C-c
  fi
}
sampler=
cleanup() {
  rc=$?
  if test -n "$sampler"; then kill "$sampler" 2>/dev/null || true; wait "$sampler" 2>/dev/null || true; fi
  stop_service group13-p15-serve-16384 || true
  printf '%s\n' "$rc" >status
  printf '16384 handoff finished %s with %s\n' "$(date -Is)" "$rc"
  exit "$rc"
}
trap cleanup EXIT
stop_service group13-p15-serve-8192
for retry in {1..60}; do
  used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | tr -d ' ')
  if test "$used" -lt 512 && test -z "$(ss -ltnH 'sport = :18081')"; then break; fi
  sleep 1
done
test "$used" -lt 512
test -z "$(ss -ltnH 'sport = :18081')"
nvidia-smi --query-gpu=timestamp,index,memory.used,memory.total,utilization.gpu --format=csv -l 2 >results/gpu-samples-16384.csv &
sampler=$!
tmux new-session -d -s group13-p15-serve-16384 "bash '$p15_dir/serve.sh' 16384 6 >'$p15_dir/serve-16384.log' 2>&1"
export PYTHONPATH="$HOME/group13-v3-p0/packages"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
python3 -B bundle/run.py --v2 bundle/v2 --pools bundle/pools.jsonl --lengths bundle/length_audit.csv \
  --cap 16384 --out results/16384 >results/16384-run.log 2>&1

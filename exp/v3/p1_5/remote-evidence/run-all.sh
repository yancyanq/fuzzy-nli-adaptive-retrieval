#!/usr/bin/env bash
set -euo pipefail
p15_dir="$HOME/group13-v3-p15"
cd "$p15_dir"
exec 9>"$p15_dir/run.lock"
flock -n 9
export PYTHONPATH="$HOME/group13-v3-p0/packages"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
mkdir -p results
nvidia-smi --query-gpu=timestamp,index,memory.used,memory.total,utilization.gpu --format=csv -l 2 >results/gpu-samples.csv &
sampler=$!
cleanup() {
  rc=$?
  kill "$sampler" 2>/dev/null || true
  wait "$sampler" 2>/dev/null || true
  for cap in 8192 16384; do
    if tmux has-session -t "=group13-p15-serve-$cap" 2>/dev/null; then
      tmux send-keys -t "=group13-p15-serve-$cap" C-c || true
    fi
  done
  printf '%s\n' "$rc" >status
  printf 'Experiment driver finished %s with %s\n' "$(date -Is)" "$rc"
  exit "$rc"
}
trap cleanup EXIT
run_cap() {
  local cap="$1"
  printf 'Starting %s at %s\n' "$cap" "$(date -Is)"
  python3 -B bundle/run.py --v2 bundle/v2 --pools bundle/pools.jsonl --lengths bundle/length_audit.csv \
    --cap "$cap" --out "results/$cap" >"results/$cap-run.log" 2>&1
  printf 'Completed %s at %s\n' "$cap" "$(date -Is)"
}
run_cap 8192
tmux send-keys -t '=group13-p15-serve-8192' C-c
for retry in {1..60}; do
  used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | tr -d ' ')
  if test "$used" -lt 512 && test -z "$(ss -ltnH 'sport = :18081')"; then break; fi
  sleep 1
done
test "$used" -lt 512
test -z "$(ss -ltnH 'sport = :18081')"
tmux new-session -d -s group13-p15-serve-16384 "bash '$p15_dir/serve.sh' 16384 6 >'$p15_dir/serve-16384.log' 2>&1"
run_cap 16384

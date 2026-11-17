#!/usr/bin/env bash
set -euo pipefail
base="$HOME/group13-v3-p5"
cd "$base"
exec 9>"$PWD/final.lock"
flock -n 9
if test -s status; then
  if test "$(cat status)" = 0; then exit 0; fi
  mv status "status-prior-$(date +%s)"
fi
service=group13-p5-final-serve
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
  printf 'P5 end %s status=%s\n' "$(date -Is)" "$rc"
  printf '%s\n' "$rc" >status
}
trap cleanup EXIT
wait_release() {
  local used
  for i in {1..90}; do
    used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | tr -d ' ')
    if test "$used" -lt 512 && test -z "$(ss -ltnH 'sport = :18082')"; then return; fi
    sleep 1
  done
  return 1
}
start_service() {
  local cap=$1 offload=$2
  wait_release
  tmux new-session -d -s "$service" "bash '$base/final-bundle/serve.sh' $cap $offload >>'$base/serve-$cap.log' 2>&1"
}
test "$(cat calibration/status)" = 0
(cd final-bundle && sha256sum -c bundle.sha256)
export PYTHONPATH="$HOME/group13-v3-p0/packages"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
tok="$HOME/group13-v3-p0/models/Qwen2.5-7B-Instruct"
nli="$HOME/group13-v3-p2/models/deberta-b3546ea"
warm="$PWD/calibration/bundle/pools.jsonl"
run() {
  PYTHONPATH="$PYTHONPATH" python3 -B final-bundle/run_final.py --tokenizer "$tok" --snapshot "$nli" --out live "$@"
}
printf 'P5 start %s\n' "$(date -Is)"
if ! test -e live/p5.primary_done; then
  mkdir -p live
  start_service 8192 4
  run --stage quality --sizes 30 --warm-pools "$warm" >>quality-30.log 2>&1
  run --stage quality --sizes 10 >>quality-10.log 2>&1
  run --stage timing --sizes 30 >>timing.log 2>&1
  stop_service
  wait_release
  touch live/p5.primary_done
fi
if ! test -e live/p5.secondary_done; then
  start_service 16384 6
  run --stage quality --sizes 60 --warm-pools "$warm" >>quality-60.log 2>&1
  stop_service
  wait_release
  touch live/p5.secondary_done
fi
nvidia-smi --query-gpu=timestamp,name,memory.used,memory.total,utilization.gpu --format=csv >gpu-after.csv
run --stage features --sizes 30 10 60 >>features.log 2>&1

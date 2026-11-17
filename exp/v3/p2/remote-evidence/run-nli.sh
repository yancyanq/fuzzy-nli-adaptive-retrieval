#!/usr/bin/env bash
set -euo pipefail
cd "$HOME/group13-v3-p2"
exec 9>"$PWD/nli.lock"
flock -n 9
trap 'rc=$?; printf "%s\n" "$rc" >logs/nli.status; exit "$rc"' EXIT
deadline=$((SECONDS+3600))
until test -s logs/qwen.status && test -s logs/nli-download.status; do
  if (( SECONDS > deadline )); then exit 1; fi
  sleep 5
done
test "$(cat logs/qwen.status)" = 0
test "$(cat logs/nli-download.status)" = 0
for i in {1..60}; do
  used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | tr -d ' ')
  if test "$used" -lt 512 && test -z "$(ss -ltnH 'sport = :18082')"; then break; fi
  sleep 1
done
test "$used" -lt 512
test -z "$(ss -ltnH 'sport = :18082')"
export PYTHONPATH="$HOME/group13-v3-p0/packages"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
printf 'Starting CPU NLI P2 at %s\n' "$(date -Is)"
python3 -B bundle/run_nli.py --bundle bundle --qwen live-qwen --snapshot models/deberta-b3546ea --out live-nli
printf 'Finished CPU NLI P2 at %s\n' "$(date -Is)"

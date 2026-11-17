#!/usr/bin/env bash
set -euo pipefail
cd "$HOME/group13-v3-p0"
trap 'rc=$?; printf "%s\n" "$rc" >logs/capacity-offload6.status; exit "$rc"' EXIT
PYTHONPATH="$PWD/packages" python3 -B run_capacity.py --model "$PWD/models/Qwen2.5-7B-Instruct" \
  --cases capacity-cases.json --port 18080 --out live-offload6 --caps 16384 --cpu-offload 6

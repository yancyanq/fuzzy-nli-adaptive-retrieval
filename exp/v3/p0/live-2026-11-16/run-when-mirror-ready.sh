#!/usr/bin/env bash
set -euo pipefail
cd "$HOME/group13-v3-p0"
trap 'rc=$?; printf "%s\n" "$rc" >logs/capacity-mirror.status; exit "$rc"' EXIT
deadline=$((SECONDS + 3600))
until test -s logs/env-mirror.status && test -s logs/model.status; do
  if test -s logs/env-mirror.status && test "$(cat logs/env-mirror.status)" != 0; then exit 1; fi
  if test -s logs/model.status && test "$(cat logs/model.status)" != 0; then exit 1; fi
  if (( SECONDS >= deadline )); then printf '%s\n' 'Preparation exceeded 3600-second wait'; exit 1; fi
  sleep 10
done
test "$(cat logs/env-mirror.status)" = 0
test "$(cat logs/model.status)" = 0
mkdir -p live-primary
(cd models/Qwen2.5-7B-Instruct && sha256sum -c weights.sha256 >../../live-primary/verified-weights.txt)
python3 -m pip list --path "$PWD/packages" --disable-pip-version-check --format=freeze >live-primary/installed-packages.txt
sha256sum run_capacity.py probe_vllm.py capacity-cases.json >live-primary/probe-inputs.sha256
PYTHONPATH="$PWD/packages" python3 -B run_capacity.py --model "$PWD/models/Qwen2.5-7B-Instruct" \
  --cases capacity-cases.json --port 18080 --out live-primary

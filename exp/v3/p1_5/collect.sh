#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" != 3 ]]; then
  printf 'Usage: bash %s CONTROL_SOCKET SSH_TARGET OUTPUT_DIR\n' "$0" >&2
  exit 2
fi
socket="$1"
target="$2"
output="$3"

scratch=$(mktemp -d)
trap 'rm -f "$scratch/evidence.tar.gz"; rmdir "$scratch"' EXIT
ssh -T -S "$socket" -o BatchMode=yes -o ProxyCommand=/usr/bin/false "$target" 'bash -s' +  >"$scratch/evidence.tar.gz" <<'P15_COLLECT'
set -euo pipefail
cd "$HOME/group13-v3-p15"
test "$(cat status)" = 0
test -s results/8192/complete.json
test -s results/16384/complete.json
for i in {1..30}; do
  used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | tr -d ' ')
  if test "$used" -lt 512 && test -z "$(ss -ltnH 'sport = :18081')"; then break; fi
  sleep 1
done
nvidia-smi --query-gpu=timestamp,name,memory.used,memory.total,utilization.gpu --format=csv >gpu-after.csv
mapfile -t result_files < <(find results -type f | LC_ALL=C sort)
files=("${result_files[@]}" bundle/inputs.sha256 driver.log status run-all.sh serve.sh serve-8192.log serve-16384.log gpu-after.csv)
for name in handoff-resume.sh handoff.log status-primary-handoff; do
  if test -f "$name"; then files+=("$name"); fi
done
sha256sum "${files[@]}" >evidence.sha256
tar -czf - "${files[@]}" evidence.sha256
P15_COLLECT
mkdir -p "$output"
tar -xzf "$scratch/evidence.tar.gz" -C "$output"
(cd "$output" && shasum -a 256 -c evidence.sha256)

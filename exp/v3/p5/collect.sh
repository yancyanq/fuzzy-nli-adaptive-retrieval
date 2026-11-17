#!/usr/bin/env bash
set -euo pipefail
project=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$project"
stage=$(mktemp -d /private/tmp/group13-p5-results.XXXXXXXX)
trap 'rm -rf "$stage"' EXIT
ssh -T -S "$1" -o BatchMode=yes -o ProxyCommand=/usr/bin/false ubuntu@43.166.23.177 'bash -s' >"$stage/return.tar.gz" <<'P5_RESULTS'
set -euo pipefail
cd "$HOME/group13-v3-p5"
until test -s status; do sleep 30; done
if test "$(cat status)" != 0; then
  for f in driver.log quality-30.log quality-10.log timing.log quality-60.log features.log; do
    if test -s "$f"; then tail -n 14 "$f" >&2; fi
  done
  exit 1
fi
files=(status driver.log quality-30.log quality-10.log quality-60.log timing.log features.log serve-{8192,16384}.log gpu-after.csv final-bundle/bundle.sha256)
shopt -s nullglob
files+=(status-prior-*)
files+=(driver-prior-*)
{ printf '%s\0' "${files[@]}"; find live -type f -print0; } | sort -z | xargs -0 sha256sum >evidence.sha256
tar -czf - "${files[@]}" live evidence.sha256
P5_RESULTS
mkdir "$stage/evidence"
tar -xzf "$stage/return.tar.gz" -C "$stage/evidence"
(cd "$stage/evidence" && shasum -a 256 -c evidence.sha256)
cmp exp/v3/p5/live_bundle.sha256 "$stage/evidence/final-bundle/bundle.sha256"
test ! -e exp/v3/p5/remote-evidence
mv "$stage/evidence" exp/v3/p5/remote-evidence
python3.13 -B exp/v3/p5/evaluate.py --input exp/v3/p5/input --raw exp/v3/p5/remote-evidence/live --out exp/v3/p5/analysis
mkdir -p exp/v3/p5/evaluation_only
python3.13 -B exp/v3/p5/review.py --input exp/v3/p5/input --raw exp/v3/p5/remote-evidence/live --out exp/v3/p5/blind-review --mapping exp/v3/p5/evaluation_only/review_method_key.jsonl

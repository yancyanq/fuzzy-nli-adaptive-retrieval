#!/usr/bin/env bash
set -euo pipefail
base="$HOME/group13-v3-p4"
cd "$base"
exec 9>"$PWD/run.lock"
flock -n 9
trap 'rc=$?; printf "P4 end %s status=%s\n" "$(date -Is)" "$rc"; printf "%s\n" "$rc" >status' EXIT
test ! -e status
(cd bundle && sha256sum -c bundle.sha256)
export CUDA_VISIBLE_DEVICES="" OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export PYTHONPATH="$HOME/group13-v3-p0/packages"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
v2="$HOME/group13-v3-p3/bundle/v2"
gate="$HOME/group13-v3-p3/bundle/v2-gate-lock.json"
nvidia-smi --query-gpu=timestamp,name,memory.used,memory.total,utilization.gpu --format=csv >gpu-before.csv
printf 'P4 CPU start %s\n' "$(date -Is)"
python3 -B bundle/train.py --input bundle/input --v2 "$v2" --v2-gate "$gate" --out output >train.log 2>&1
python3 -B bundle/train.py --input bundle/input --v2 "$v2" --v2-gate "$gate" --out replay >replay.log 2>&1
diff -qr --exclude=runtime.json output replay >reproducibility.txt
printf 'All artifacts except measured runtime matched byte-for-byte.\n' >>reproducibility.txt
nvidia-smi --query-gpu=timestamp,name,memory.used,memory.total,utilization.gpu --format=csv >gpu-after.csv

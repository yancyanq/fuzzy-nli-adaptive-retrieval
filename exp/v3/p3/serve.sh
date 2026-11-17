#!/usr/bin/env bash
set -euo pipefail
base="$HOME/group13-v3-p0"
cd "$HOME/group13-v3-p3"
export PYTHONPATH="$base/packages"
export VLLM_USE_V1=0 VLLM_ATTENTION_BACKEND=XFORMERS VLLM_NO_USAGE_STATS=1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
exec python3 -m vllm.entrypoints.openai.api_server --model "$base/models/Qwen2.5-7B-Instruct" \
  --served-model-name Qwen/Qwen2.5-7B-Instruct --host 127.0.0.1 --port 18082 --max-logprobs 5 \
  --load-format safetensors --dtype half --max-model-len "$1" --max-num-seqs 8 \
  --cpu-offload-gb "$2" --enforce-eager --disable-log-requests

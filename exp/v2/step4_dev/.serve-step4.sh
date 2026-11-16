#!/usr/bin/env bash
set -euo pipefail
cd "$HOME/nlp"
test "$(cat logs/install.status)" = 0
model_dir="$PWD/models/Qwen2.5-7B-Instruct"
for ((try=0; try<360; try++)); do
  missing=0
  for shard in 00001 00002 00003 00004; do
    if test -f "$model_dir/model-$shard-of-00004.safetensors"; then continue; fi
    missing=1
    case "$shard" in
      00001|00004) stage=model_ranges ;;
      *) stage=model_download ;;
    esac
    if test -f "logs/$stage.status"; then
      printf 'Missing shard %s after %s completed\n' "$shard" "$stage" >&2
      exit 1
    fi
  done
  if test "$missing" = 0; then break; fi
  if test "$try" = 0; then printf 'Waiting for verified model files\n'; fi
  sleep 5
done
(
  cd "$model_dir"
  sha256sum -c <<'CHECKSUMS'
a1333e6293854747c481288ea83b348226af178dd565c49b6f9495ba1966aba7  model-00001-of-00004.safetensors
f5d25a2772cb825164a2a2c0fb6d51a87e282abf21e4dd75bc5cfb3cd0ea6185  model-00002-of-00004.safetensors
8efdec4c1bc12317ae1a38dc42b595ce777738a64deea3fcb8a0a91381bcdfd5  model-00003-of-00004.safetensors
1a72d403cdf0c1ec3cb7f289f17b394a01e64394c2e9b3c0f94dbce3faf879bd  model-00004-of-00004.safetensors
CHECKSUMS
)
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 VLLM_NO_USAGE_STATS=1
export VLLM_USE_V1=0 VLLM_ATTENTION_BACKEND=XFORMERS
exec .venv_step6a/bin/vllm serve "$model_dir" \
  --served-model-name Qwen/Qwen2.5-7B-Instruct \
  --host 127.0.0.1 --port 8000 --max-logprobs 5 --load-format safetensors \
  --dtype half --max-model-len 4096 --max-num-seqs 8 --cpu-offload-gb 4 --enforce-eager

#!/usr/bin/env bash
set -euo pipefail
base="$HOME/group13-v3-p2"
cd "$base/models/deberta-b3546ea"
trap 'rc=$?; printf "%s\n" "$rc" >"$base/logs/nli-download.status"; exit "$rc"' EXIT
src='https://huggingface.co/MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli/resolve/b3546ea6b0346eb6f8d5d68b13c7dc6d0376b3d7'
for f in config.json added_tokens.json special_tokens_map.json spm.model tokenizer.json tokenizer_config.json; do
  curl -fLsS --connect-timeout 12 --max-time 160 --retry 3 -o "$f.part" "$src/$f"
  mv "$f.part" "$f"
done
hash=c03cd208bf920b4fbbb182a0535859a566e8acc3477d2b536bf87b769978524b
if ! test -f model.safetensors || ! printf '%s  model.safetensors\n' "$hash" | sha256sum -c -; then
  curl -fLsS --connect-timeout 12 --speed-limit 16384 --speed-time 90 --retry 3 --retry-all-errors \
    -C - -o model.safetensors.part "$src/model.safetensors?download=true"
  printf '%s  model.safetensors.part\n' "$hash" | sha256sum -c -
  mv model.safetensors.part model.safetensors
fi
sha256sum config.json added_tokens.json special_tokens_map.json spm.model tokenizer.json tokenizer_config.json model.safetensors >snapshot.sha256
printf 'Pinned NLI snapshot verified at %s\n' "$(date -Is)"

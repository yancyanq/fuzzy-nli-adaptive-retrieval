#!/usr/bin/env bash
set -euo pipefail
p0_dir="$HOME/group13-v3-p0"
cd "$p0_dir/models/Qwen2.5-7B-Instruct"
trap 'rc=$?; printf "%s\n" "$rc" >"$p0_dir/logs/model.status"; exit "$rc"' EXIT
revision=a09a35458c702b33eeacc393d103063234e8bc28
base="https://huggingface.co/Qwen/Qwen2.5-7B-Instruct/resolve/$revision"
cat >weights.sha256 <<'WEIGHT_HASHES'
a1333e6293854747c481288ea83b348226af178dd565c49b6f9495ba1966aba7  model-00001-of-00004.safetensors
f5d25a2772cb825164a2a2c0fb6d51a87e282abf21e4dd75bc5cfb3cd0ea6185  model-00002-of-00004.safetensors
8efdec4c1bc12317ae1a38dc42b595ce777738a64deea3fcb8a0a91381bcdfd5  model-00003-of-00004.safetensors
1a72d403cdf0c1ec3cb7f289f17b394a01e64394c2e9b3c0f94dbce3faf879bd  model-00004-of-00004.safetensors
WEIGHT_HASHES
for asset in config.json generation_config.json model.safetensors.index.json tokenizer.json tokenizer_config.json vocab.json merges.txt; do
  curl -fLsS --connect-timeout 12 --max-time 100 --retry 3 -o "$asset.part" "$base/$asset"
  mv "$asset.part" "$asset"
done
sha256sum -c <<'TOKENIZER_HASHES'
c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539  tokenizer.json
5b5d4f65d0acd3b2d56a35b56d374a36cbc1c8fa5cf3b3febbbfabf22f359583  tokenizer_config.json
TOKENIZER_HASHES
download() {
  local checksum="$1" file="$2"
  if test -f "$file" && printf '%s  %s\n' "$checksum" "$file" | sha256sum -c -; then return; fi
  printf '%s starting %s\n' "$(date -Is)" "$file"
  curl -fLsS --connect-timeout 12 --speed-limit 16384 --speed-time 90 \
    --retry 3 --retry-all-errors -C - -o "$file.part" "$base/$file?download=true"
  printf '%s  %s\n' "$checksum" "$file.part" | sha256sum -c -
  mv "$file.part" "$file"
  printf '%s finished %s\n' "$(date -Is)" "$file"
}
pids=()
while read -r checksum file; do
  download "$checksum" "$file" >"$p0_dir/logs/$file.log" 2>&1 &
  pids+=("$!")
done <weights.sha256
failed=0
for pid in "${pids[@]}"; do wait "$pid" || failed=1; done
test "$failed" -eq 0
sha256sum -c weights.sha256
sha256sum config.json generation_config.json model.safetensors.index.json tokenizer.json tokenizer_config.json vocab.json merges.txt

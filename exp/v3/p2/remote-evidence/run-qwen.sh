#!/usr/bin/env bash
set -euo pipefail
cd "$HOME/group13-v3-p2"
exec 9>"$PWD/qwen.lock"
flock -n 9
cleanup() {
  rc=$?
  if tmux has-session -t '=group13-p2-serve' 2>/dev/null; then
    pane=$(tmux list-panes -t '=group13-p2-serve' -F '#{pane_id}')
    if [[ "$pane" =~ ^%[0-9]+$ ]]; then tmux send-keys -t "$pane" C-c || true; fi
  fi
  printf '%s\n' "$rc" >logs/qwen.status
  exit "$rc"
}
trap cleanup EXIT
export PYTHONPATH="$HOME/group13-v3-p0/packages"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
printf 'Starting Qwen P2 at %s\n' "$(date -Is)"
python3 -B bundle/run_qwen.py --bundle bundle --tokenizer "$HOME/group13-v3-p0/models/Qwen2.5-7B-Instruct" --out live-qwen
printf 'Finished Qwen P2 at %s\n' "$(date -Is)"

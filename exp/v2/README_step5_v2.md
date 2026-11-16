# V2 步骤 5 正式评估

正式样本使用项目根目录已有的 `test.json`。CUDA NLI 和 Qwen vLLM 使用步骤 4 同一检查点。以下命令在租用 GPU 服务器的 `~/nlp` 下运行，服务监听 `127.0.0.1:8000`。如服务配置了鉴权，在运行任务的 shell 中通过 `VLLM_API_KEY` 环境变量提供；当前锁定服务监听 loopback 且无需鉴权。

- 将 `generate_test_v2.py` 和 `evaluate_test_v2.py` 放在服务器的 `~/nlp/step4_dev/`，与已有的 `run_pilot.py`、`calibrate_gates_v2.py` 和 `analyze_pilot_signals_v2.py` 同目录。
- 将 `run_step5_v2.sh` 放在 `~/nlp`。将 `test.json`、`step5_v2/hotpot_evaluate_v1.py` 和 `step5_v2/inputs.sha256` 放到 `~/nlp/step5_v2/`。`inputs.sha256` 的路径以服务器的 `~/nlp` 为基准。
- 使用步骤 4 的 `.venv_step6a`、`.serve-step4.sh`、`nlp6a-vllm` tmux 会话、`step4_dev/gates/locked_gates.json` 和本地模型目录。开发集验证另外读取 `tune.json` 与 `step4_dev/nli/branches.jsonl`。

```bash
cd ~/nlp
sha256sum -c step5_v2/inputs.sha256
tmux new-session -d -s nlp-v2-test 'cd "$HOME/nlp" && bash run_step5_v2.sh >> step5_v2/run.log 2>&1'
tail -f step5_v2/run.log
```

任务先运行开发集引用和真实路径检查。通过后生成 A、B 和 Full-context。QA 回答和引用分别逐条写入专用缓存，随后运行 CUDA NLI、官方评分、离线策略回放和真实路径测量。失败后先查 `step5_v2/run.log`、`dev_selector_smoke.log`、`dev_latency_cuda.log`、`nli.log` 或 `latency.log`。确认远端没有既有任务后，使用同一条 tmux 启动命令续跑，不删除已核验的结果缓存。

- `finish.exit` 为 `0` 且 `sha256sum -c step5_v2/results.sha256` 通过时，运行完成。
- `quality_summary.json` 提供答案 F1、EM、Supp-F1、触发率、逐题变化与选题精确率／召回率／F1。逐题指标和九种策略的官方预测见 `per_question.csv` 和 `predictions/`。
- `latency_summary.json` 提供六种真实策略在同一 32 题上的时延均值、P50/P90/P95，LLM 分列输入与输出 token，NLI 输入 token 另列。各方法用 8 个 dev 请求预热并以并发 8 测量。Oracle 的质量来自缓存选优。
- `dev_selector_smoke.json` 与 `dev_latency_*.log` 用于验证管线。论文正式结果基于 1,000 题的独立样本。

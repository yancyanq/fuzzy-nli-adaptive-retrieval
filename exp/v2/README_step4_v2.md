# V2 步骤 4

步骤 4 使用已锁定的 500 题 `tune.json`。Qwen2.5-7B-Instruct 在相同 prompt 和解码设置下为每题生成 A/B，分别用首轮两个段落和追加检索后的段落给出带引用的答案。DeBERTa 以原有 premise/hypothesis 格式给两支评分。

本次租用 GPU 的工作目录是 `~/nlp`。会话 `nlp-v2-tune` 用 `step4_dev/run_answers.sh` 运行八个 ID 分片，各分片落盘后按 tune 清单顺序合并到 `step4_dev/answers/answers_v2_dev.jsonl`。起初串行生成的记录归档在 `step4_dev/serial`。会话 `nlp-v2-finish` 运行 `step4_dev/run_step4_v2.sh`，待生成结束后检查 1,000 条分支记录，对不完整的生成进行一次补跑，给完整缓存打 NLI 分，最后校准并锁定门控。NLI 独占 GPU 期间会临时暂停 Qwen，结束后用同一服务脚本恢复。

```bash
cd ~/nlp
find step4_dev/batches -name answers.jsonl -exec wc -l {} +
tail -n 12 step4_dev/finish.log
```

续跑答题时仍用 `step4_dev/run_answers.sh`，由它为每个分片维持单一写入进程。

从仓库根目录进入 `exp/v2` 后，在独立输出目录复算门控校准。

```bash
python calibrate_gates_v2.py --tune tune.json --branches step4_dev/nli/branches.jsonl --serve-script step4_dev/.serve-step4.sh --out ../../runs/v2_gates
```

校准脚本只读取缓存。Fuzzy 和同输入硬规则使用 A 支 entailment 与首轮段落完整标题匹配得到的桥接信号，两者均在 dev 选 100 题。每种门控从同一候选参数网格中选择配对 F1 增益最大的设置。校准细则及同分处理规则见实验日志。

- `locked_gates.json` 记录门控参数、逐题应用的决策边界和对应的脚本与数据哈希。
- `dev_summary.json` 记录 dev 上的 F1、EM、实际再检索率和选题类别数。
- `dev_selection.csv` 记录逐题输入和各门控的选择。

正式评估通过 `calibrate_gates_v2.should_retrieve` 对每题应用固定门控。正式 test 报告实测再检索率。

合成数据测试可用 `python -m unittest -v test_calibrate_gates_v2` 运行。

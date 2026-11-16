# Fuzzy-NLI 自适应检索问答

BNBU/UIC NLP 课程项目。在 HotpotQA distractor 的 bridge 题上，系统先用 BM25 检索两个段落并带引用作答，再用 NLI 和桥接实体信号决定是否追加检索一次。我们在 500 道开发题上锁定门控，在 1,000 道独立测试题上比较各策略。

**[实验过程手册](exp/v2/step6_v2/NLP_V2_Experiment_Process_Handbook.md) · [完整实验结论](exp/v2/step6_v2/NLP_V2_Experiment_Conclusions.md) · [实验进度](PROGRESS.md)**

## 正式实验结果

| 策略 | 答案 F1 | 再检索率 |
| --- | ---: | ---: |
| Never（仅首轮） | 50.85% | 0% |
| Crisp（同输入硬规则） | 54.36% | 20.9% |
| Fuzzy（模糊门控） | 54.42% | 23.0% |
| Always（每题追加） | 57.66% | 100% |
| Full-context（直接提供全部候选段落） | 64.27% | 0% |

- **选择性补检索提高了首轮基线的答案质量。** Fuzzy 相对 Never 提高 **3.576 个 F1 百分点**，95% 配对区间为 [2.265, 4.914]。
- **模糊规则的独立优势尚未确立。** Fuzzy 相对同输入 Crisp 的差值是 **+0.064 个 F1 百分点**，95% 配对区间 [−0.365, +0.517] 跨零。两者在正式集上的实际再检索率分别为 23.0% 和 20.9%。
- **再检索率和端到端成本需要分别衡量。** 在共用的 32 题计时样本上，Fuzzy 的平均延迟为 23.36 秒，Always 为 19.13 秒。Full-context 的答案 F1 最高，平均 LLM 输入为 1,916.75 tokens。 [结果总表与测量口径](docs/RESULTS.md)

## 实验材料

- [实验方案、过程手册、结果册和结论册的 Word／Markdown 对照](docs/DOCUMENTS.md)
- [正式实验脚本、逐题缓存和复现说明](exp/v2/README.md) · [实验日志](exp/EXPERIMENT_LOG.md)
- [下载完整实验材料 ZIP（公开版）](sources/NLP_Experiment_Materials_V2_Complete_Public.zip)

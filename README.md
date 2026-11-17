# Fuzzy-NLI 自适应检索问答

BNBU/UIC NLP 课程项目。两次实验都在 HotpotQA distractor 的 bridge 题上研究何时值得再检索一次。

| 实验 | 评估范围 | 实验入口 |
| --- | --- | --- |
| **V2 · 固定候选池** | 500 题校准，1,000 题独立正式评估。比较固定参数的 Fuzzy、同输入 Crisp 及其他基线。 | [实验索引](INDEX.md) · [结果总表](docs/RESULTS.md) · [文档与手册](docs/DOCUMENTS.md) |
| **V3.1 · 扩展候选池** | 10／30／60 段候选池的策略预检、关系级 NLI 诊断、100／50 题试训与 300 题封存评估。 | [V3.1 首页](exp/v3/README.md) · [阶段结果](exp/v3/RESULTS.md) · [实验过程与复现](exp/v3/RUNBOOK.md) |

## V2 正式评估

Fuzzy 的答案 F1 为 **54.42%**，再检索率为 **23.0%**。相对 Never 提高 **3.576 个百分点**，95% 配对区间为 [2.265, 4.914]。相对同输入 Crisp 的差值为 **+0.064 个百分点**，95% 区间 [−0.365, +0.517] 跨零。Full-context 的答案 F1 最高，为 **64.27%**。 [V2 结果与成本口径](docs/RESULTS.md)

[实验过程手册](exp/v2/step6_v2/NLP_V2_Experiment_Process_Handbook.md) · [完整结论](exp/v2/step6_v2/NLP_V2_Experiment_Conclusions.md) · [V2 进度](PROGRESS.md) · [V2 日志](exp/EXPERIMENT_LOG.md) · [V2 完整材料 ZIP](sources/NLP_Experiment_Materials_V2_Complete_Public.zip)

## V3.1 扩展候选池

P2 的关系抽取结构通过率为 **48/50（96%）**，人工复核的关系忠实率为 **26/56（46.43%）**，低于 90% 的阶段门槛；P3 因此采用原查询与整题 NLI 路线。P4 的完整 Sugeno 与线性收益回归在四档补查预算下选中同一批题。P5 在 300 道封存题、30 段、20% 补查预算下完成正式比较：完整 Sugeno 的答案 F1 为 **44.64%**，固定 Fuzzy 为 **43.64%**，线性收益回归为 **44.64%**；Sugeno 相对固定 Fuzzy 为 **+1.00 个百分点**，95% 配对区间 [−1.33, +3.33]。60 题引用充分性盲审尚未回收。 [P2 核验](exp/v3/p2/REPORT.md) · [P4 验证报告](exp/v3/p4/validation_report.md) · [P5 正式报告](exp/v3/p5/REPORT.md)

[实验方案](exp/v3/protocol/README.md) · [阶段参数](exp/v3/PARAMETERS.md) · [V3.1 日志](exp/EXPERIMENT_LOG.md) · [V3.1 完整材料 ZIP](sources/NLP_Experiment_Materials_V3_1_Public.zip)

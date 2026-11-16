# Fuzzy-NLI 自适应检索问答

*A Fuzzy-NLI-based QA Chatbot System with Adaptive Retrieval* 是 BNBU/UIC NLP 课程项目。我们用 HotpotQA distractor 的 bridge 题研究何时值得再检索一次。分支 A 用 BM25 检索到的前两个段落作答，分支 B 在 A 的基础上补一个段落后作答。正式实验用 NLI 和桥接实体信号决定是否再检索，并比较同输入的 Fuzzy 与 Crisp 门控。

**[最新进度](PROGRESS.md) · [完整实验日志](exp/EXPERIMENT_LOG.md) · [结果总表](docs/RESULTS.md) · [V2 正式实验材料](exp/v2/README.md)**

## 实验进度

| 阶段 | 状态与结论 | 入口 |
| --- | --- | --- |
| 数据与原始 pilot | 100 / 500 / 1,000 题分别用于 pilot、dev、正式测试。100 题 pilot 判定 **GO** | [早期实验索引](INDEX.md) |
| Logprob 排查 | DeepSeek 温度 0 的信号退化，Qwen vLLM 非退化检查 **PASS**。V2 正式门控锁定 NLI 和桥接信号 | [Step 6a 实测](exp/EXPERIMENT_LOG.md?plain=1#L326) · [门控锁定](exp/EXPERIMENT_LOG.md?plain=1#L482) |
| V2 §7.3 补充 pilot | NLI 和 NLI＋桥接各选 20 题，各选中 6 道改善题 | [补充分析](exp/EXPERIMENT_LOG.md?plain=1#L415) |
| V2 步骤 4 门控校准 | 在 500 题 dev 上按共同 20% 目标校准并冻结门控 | [门控锁文件](exp/v2/step4_dev/gates/locked_gates.json) |
| V2 步骤 5 正式评估 | 1,000 题质量评估及独立计时已完成。Fuzzy 答案 F1 为 0.54424354，再检索率为 23.0% | [正式日志](exp/EXPERIMENT_LOG.md?plain=1#L573) · [质量汇总](exp/v2/step5_v2/quality_summary.json) |
| V2 步骤 6 统计与论文材料 | Fuzzy − Crisp 为 +0.064 个 F1 百分点，95% 配对区间 [−0.365, +0.517]，跨零。结果册、错误分析和复现清单已归档 | [统计日志](exp/EXPERIMENT_LOG.md?plain=1#L611) · [正式报告](exp/v2/step6_v2/Experiment_Report.md) |

## 阅读与复现

| 材料 | 入口 |
| --- | --- |
| 实验方案 | [原始 V2 PDF](docs/Experiment_Protocol_v2.pdf) · [原始 V2 DOCX](docs/Experiment_Protocol_v2.docx) · [填入 §11 结果的副本](exp/v2/step6_v2/Experiment_Protocol_v2_Section11_Filled.docx) |
| 正式结果与论文 | [中文 §11 结果册](exp/v2/step6_v2/NLP_V2_Section11_Results_Booklet.docx) · [英文论文段落预览](exp/v2/step6_v2/Methodology_and_Experimental_Results.pdf) · [质量–成本图](exp/v2/step6_v2/quality_cost.pdf) |
| 逐题输出与复现 | [正式逐题结果](exp/v2/step5_v2/per_question.csv) · [配对区间 CSV](exp/v2/step6_v2/paired_bootstrap.csv) · [可复现性清单](exp/v2/step6_v2/Reproducibility_Checklist.md) |
| 文件与协作 | [实验索引](INDEX.md) · [文件清单](docs/INVENTORY.md) · [运行环境](docs/ENVIRONMENT.md) · [缺口清单](docs/GAPS.md) · [同步方式](docs/WORKFLOW.md) |

`exp/step*/` 归档早期实验，`exp/v2/` 归档正式阶段脚本和结果。`docs/` 提供方案及实验导航，`reports/` 保留 Step 6a 实测前的阶段报告，`sources/` 保留交接快照。名称含 `mock` 的输出及 `testdata/` 中的输入是测试数据。进度页和实验日志展示版保留条目顺序，隐藏执行日期、时刻及时区。

数据来源及授权见 [第三方材料](docs/THIRD_PARTY.md)。

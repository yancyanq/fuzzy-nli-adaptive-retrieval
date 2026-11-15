# Fuzzy-NLI 自适应检索问答

*A Fuzzy-NLI-based QA Chatbot System with Adaptive Retrieval* 是 BNBU/UIC NLP 课程项目。我们在 HotpotQA distractor 的 bridge 题上研究一个问题：什么时候值得再检索一次？

分支 A 用 BM25 检索到的前两个段落作答。分支 B 用规则改写查询，从未使用的段落里再补一个段落后作答。作答模型给出答案和引用，NLI 检查引用证据是否支持答案。正式比较将在相同输入与相同目标再检索率下，评估模糊门控和硬规则的答案质量、再检索率和成本。

## 实验进度

**[查看最新进度](PROGRESS.md)** · **[阅读完整实验日志](exp/EXPERIMENT_LOG.md)**

截至 **2026-11-15 15:21（北京时间）**，已完成 100 题 pilot 和 Step 6a 非退化检查。当前在准备按 V2 §7.3 比较 NLI 与桥接实体信号的选题能力。

| 阶段 | 当前状态 | 记录 |
| --- | --- | --- |
| Step 1–4 数据、检索与预注册 | 切分完成，选定 BM25 `k=2`、`m=1`，已登记 pilot 的 GO 判定规则 | [实验索引](INDEX.md) |
| Step 5 Pilot | **GO**。分支 A / B / Oracle 的 F1 为 0.628 / 0.752 / 0.765 | [真实 pilot](exp/EXPERIMENT_LOG.md#L146) |
| Step 5b DeepSeek logprob | 温度 0 下选中 token 的 logprob 与 top‑k margin 退化 | [排查结果](exp/EXPERIMENT_LOG.md#L218) |
| Step 6a 本地 vLLM | 前 30 道 tune 题的非退化检查 **PASS**。是否将不确定性纳入正式门控待定 | [实测记录](exp/EXPERIMENT_LOG.md#L326) |
| V2 §7.3 Pilot 信号对照 | 两份真实逐题导出已归档。桥接信号、对照方式和预算已有候选设置及理由，等待确认，信号对照尚未运行 | [候选设置](exp/EXPERIMENT_LOG.md#L362) · [比较理由](exp/EXPERIMENT_LOG.md#L371) |

进度页按时间倒序索引日志。完整日志保留实验设置、真实结果、决定及其记录时间。阶段报告为 Step 6a 实测前的快照，实测数据见本次产物。 [Step 6a 实测摘要](exp/step6a/step6a_check/logprob_check.json)

## 从哪里开始

| 想了解什么 | 入口 |
| --- | --- |
| 实验设计与规则 | [实验方案 v2 PDF](docs/Experiment_Protocol_v2.pdf) · [可编辑 DOCX](docs/Experiment_Protocol_v2.docx) |
| 复现某一步 | [实验索引](INDEX.md)含脚本、命令和输出 · [运行环境](docs/ENVIRONMENT.md) |
| 追溯论文数字 | [结果总表](docs/RESULTS.md) |
| 找数据、脚本或报告 | [逐文件清单](docs/INVENTORY.md) · [阶段报告 PDF](reports/Interim_Experiment_Report_2026-11-15.pdf) · [DOCX](reports/Interim_Experiment_Report_2026-11-15.docx) |
| 接下一步或归档结果 | [缺口清单](docs/GAPS.md) · [提交与同步方式](docs/WORKFLOW.md) |

## 目录

```text
exp/       权威日志、切分数据、各步脚本、测试、已归档实验输出
docs/      实验方案、逐文件清单、结果、缺口、运行与协作说明
reports/   阶段报告 PDF 和 DOCX
sources/   原始交接 ZIP、旧日志和交付时的材料快照
tools/     更新进度索引的工具
```

真实的 Step 5 逐题文件在 [step5_pilot](exp/step5/step5_pilot)，真实的 Step 6a 输出在 [step6a_check](exp/step6a/step6a_check)。含 `mock` 的目录是测试输出，`testdata/` 是测试输入。

## 本地快速验证

在仓库根目录，用独立 Python 环境运行。以下检查只用标准库、指定 pip 依赖和本地 mock 服务。

```bash
python -m pip install openai==1.76.2 rank-bm25==0.2.2
python exp/step5/test_step5.py
python exp/step5/test_analyze_signals.py
python exp/step5b/test_step5b.py
python exp/step6a/test_step6a.py
```

运行真实实验前按[运行环境](docs/ENVIRONMENT.md)准备数据、模型、凭据和缓存。把临时结果写入 `runs/`，复核后再放到对应步骤的归档目录。项目访问由仓库所有者管理。

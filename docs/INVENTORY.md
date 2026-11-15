# 文件清单与归档位置

下表覆盖原始 ZIP 的每个文件和工作区额外出现的相关文件，包括 Step 6a 实测产物、Step 5 逐题导出和方案 DOCX。路径以整理包根目录为准。表里的「ZIP 同路径」表示该项沿用 ZIP 内部路径，「工作区同名副本」表示整理前位于工作区根目录的文件与 ZIP 条目逐字节相同，包内共用一个活动路径。

## 目录结构与理由

```text
fuzzy-nli-adaptive-retrieval/
├── README.md                        GitHub 项目首页
├── PROGRESS.md                      权威日志的时间索引
├── INDEX.md                         中文入口与复现命令
├── exp/
│   ├── EXPERIMENT_LOG.md            工作区记录的展示版本权威日志
│   ├── step1/                       pilot、tune 数据
│   ├── step2/                       BM25 脚本与两组实际输出
│   ├── step3/                       作答试跑脚本、README 与两个 mock 输出目录
│   ├── step5/                       pilot、人工审核、信号诊断与探测脚本
│   ├── step5b/                      top_logprobs 重跑脚本、说明与测试
│   └── step6a/                      vLLM 检查脚本、说明、测试与实际输出
├── docs/                            实验方案 PDF / DOCX 与整理生成的文档
├── reports/                         实测前的阶段报告 PDF 与 DOCX
├── sources/                         原始交接 ZIP 和历史快照
└── tools/                           生成进度页的脚本
```

`exp/step3`、`exp/step5`、`exp/step5b`、`exp/step6a` 的相对关系由脚本和测试使用，保留目录名以免改写导入。pilot 和 tune 统一归入 Step 1，体现二者的切分来源，运行时用 `--data` 指向。Step 4 的预注册决定在[日志中](../exp/EXPERIMENT_LOG.md?plain=1#L75)可查。探测脚本按用途列到 Step 5b，物理文件沿用 ZIP 的 Step 5 路径，便于对照旧交接。Step 2 的产物与生成脚本相邻；Step 6a 归档的真实结果位于 `step6a_check/`，与判定脚本相邻，便于离线回算；两类历史 mock 输出保留在名称含 `mock` 的目录中，测试输入留在 `testdata/`。命令把新产物写在另建的 `runs/`，便于保留历史证据。原始交接材料可从 `sources/` 的 ZIP 下载。

## Step 1–2 数据和召回

| 步骤 | 包内文件 | 类型 | 来源与用途 |
| --- | --- | --- | --- |
| 1 | `exp/step1/pilot.json` | 数据 | ZIP 的 `exp/step2/pilot.json`；bridge pilot，供 Step 2–5b 使用 |
| 1 | `exp/step1/tune.json` | 数据 | 工作区 `tune.json`；独立 tune，供 Step 6a 选首段及后续调参 |
| 2 | `exp/step2/bm25_topk.py` | 脚本 | ZIP 同路径，工作区同名副本；BM25 两轮召回与 gold 段落比较 |
| 2 | `exp/step2/step2_results/per_question.csv` | 输出 | ZIP 同路径；m=1 的逐题 × k 指标，目录名是脚本默认名 |
| 2 | `exp/step2/step2_results/summary.json` | 输出 | ZIP 同路径；m=1 按 k 的汇总 |
| 2 | `exp/step2/step2_m2/per_question.csv` | 输出 | ZIP 同路径；m=2 的逐题 × k 指标 |
| 2 | `exp/step2/step2_m2/summary.json` | 输出 | ZIP 同路径；m=2 按 k 的汇总 |

## Step 3 作答试跑与 mock

| 包内文件 | 类型 | 来源与用途 |
| --- | --- | --- |
| `exp/step3/compare_models.py` | 脚本 | ZIP 同路径，工作区同名副本；作答、评估、缓存和共享检索/API 函数 |
| `exp/step3/README_step3.md` | README | ZIP 同路径，工作区同名副本；安装、三类端点用法与输出说明 |
| `exp/step3/test_mock_server.py` | 测试 | ZIP 同路径；OpenAI 兼容的本地 mock HTTP 服务，也支持 Step 5b/6a 的假响应模式 |
| `exp/step3/step3_mock/branches.jsonl` | mock 测试数据 / 输出 | ZIP 同路径；logprob 支持路径的假分支记录 |
| `exp/step3/step3_mock/per_question.csv` | mock 测试数据 / 输出 | ZIP 同路径；logprob 支持路径的假逐题指标 |
| `exp/step3/step3_mock/summary.json` | mock 测试数据 / 输出 | ZIP 同路径；logprob 支持路径的假汇总 |
| `exp/step3/step3_mock/cache.jsonl` | mock 测试数据 / 输出 | ZIP 同路径；logprob 支持路径的假 API 缓存 |
| `exp/step3/step3_mock_nolp/branches.jsonl` | mock 测试数据 / 输出 | ZIP 同路径；logprob 不支持时回退路径的假分支记录 |
| `exp/step3/step3_mock_nolp/per_question.csv` | mock 测试数据 / 输出 | ZIP 同路径；回退路径的假逐题指标 |
| `exp/step3/step3_mock_nolp/summary.json` | mock 测试数据 / 输出 | ZIP 同路径；回退路径的假汇总 |
| `exp/step3/step3_mock_nolp/cache.jsonl` | mock 测试数据 / 输出 | ZIP 同路径；回退路径的假 API 缓存 |

## Step 4–6a 预注册、Pilot 与 logprob

| 步骤 | 包内文件 | 类型 | 来源与用途 |
| --- | --- | --- | --- |
| 4 | [Step 4 预注册条目](../exp/EXPERIMENT_LOG.md?plain=1#L75) | 文档 | 九条批准参数，包含 GO 阈值、NLI 和人工审核；整份日志见下节 |
| 5 | `exp/step5/run_pilot.py` | 脚本 | ZIP 同路径，工作区同名副本；A/B、NLI、GO 判定与抽样 |
| 5 | `exp/step5/test_step5.py` | 测试 | ZIP 同路径；评分、标签、bootstrap、缓存、GO 判定和 mock 端到端 |
| 5 | `exp/step5/README_step5.md` | README | ZIP 同路径，工作区同名副本；分两阶段复用作答缓存并跑 NLI |
| 5 | `exp/step5/audit_helper.py` | 脚本 | ZIP 同路径，工作区同名副本；合并抽样与 NLI 前提，生成人工填表 |
| 5 | `exp/step5/step5_pilot/per_question.csv` | 输出 | 工作区同名文件，真实逐题得分、增益类别、NLI 与证据字段，见[导出确认](../exp/EXPERIMENT_LOG.md?plain=1#L356) |
| 5 | `exp/step5/step5_pilot/branches.jsonl` | 输出 | 工作区同名文件，真实 A/B 分支记录，见[导出确认](../exp/EXPERIMENT_LOG.md?plain=1#L356) |
| 5 | `exp/step5/audit_review_yangqs.csv` | 输出 | ZIP 同路径；YangQS 的真实人工审核副本，保留标签和备注 |
| 5 | `exp/step5/analyze_signals.py` | 脚本 | ZIP 同路径，工作区同名副本；离线比较首轮信号、计算 AUC 和 bootstrap CI |
| 5 | `exp/step5/test_analyze_signals.py` | 测试 | ZIP 同路径；合成数据检查 AUC 方向和读写 |
| 5 | `exp/step5/testdata/mini_pilot.json` | mock 测试数据 | ZIP 同路径；取自真实 pilot 的输入子集，提供给 mock 测试。测试生成的答案、NLI 分数与指标均是测试值。Step 5 测试代码另临时构造一条长段落题 |
| 5b 探测 | `exp/step5/probe_logprobs.py` | 脚本 | ZIP 同路径，工作区同名副本；短提示与两种温度下检查候选和选中 token |
| 5b | `exp/step5b/rerun_toplogprobs.py` | 脚本 | ZIP 同路径，工作区同名副本；重跑 A/B、独立缓存、同题 AUC 与答案一致性 |
| 5b | `exp/step5b/test_step5b.py` | 测试 | ZIP 同路径；margin、熵、缓存隔离、合成样本和 mock 端到端 |
| 5b | `exp/step5b/README_step5b.md` | README | ZIP 同路径，工作区同名副本；重跑和离线回算说明 |
| 6a | `exp/step6a/check_logprobs.py` | 脚本 | ZIP 同路径，工作区同名副本；检查选中 logprob、替代值、逐题离散程度、完整性 |
| 6a | `exp/step6a/test_step6a.py` | 测试 | ZIP 同路径；合成题和 mock PASS/FAIL、阈值边界、缓存隔离 |
| 6a | `exp/step6a/README_step6a.md` | README | ZIP 同路径，工作区同名副本；vLLM 客户端、默认阈值、输出和 mock 说明 |
| 6a | `exp/step6a/step6a_check/logprob_check.json` | 输出 | 工作区 `step6a_check/logprob_check.json`；真实推理结果、判定与逐题明细 |
| 6a | `exp/step6a/step6a_check/logprob_check_tokens.csv` | 输出 | 工作区 `step6a_check/logprob_check_tokens.csv`；真实逐 token 数据和答案范围标记 |
| 6a | `exp/step6a/step6a_check/cache_logprob_check.jsonl` | 输出 | 工作区 `step6a_check/cache_logprob_check.jsonl`；真实响应的精简缓存，可离线复核 |

## 跨步骤材料

| 包内文件 | 类型 | 来源与用途 |
| --- | --- | --- |
| `exp/EXPERIMENT_LOG.md` | 文档 | 工作区原始日志的展示版本，保留实验内容和条目顺序 |
| `sources/EXPERIMENT_LOG.handoff.md` | 文档 | 原 ZIP 交接日志的展示版本，保留至 Step 6a 检查准备条目 |
| `sources/nlp_exp_handoff.zip` | 源归档 | 工作区原 ZIP 原样保留，供核对原路径与来源 |
| `docs/Experiment_Protocol_v2.pdf` | 文档 | ZIP 根目录的方案 v2；研究问题、计划、正式结果留白 |
| `docs/Experiment_Protocol_v2.docx` | 文档 | 整理期间出现在工作区的同名可编辑方案文件，保留原件 |
| `reports/Interim_Experiment_Report_2026-11-15.docx` | 文档 | 工作区同名文件；可编辑阶段报告 |
| `reports/Interim_Experiment_Report_2026-11-15.pdf` | 文档 | 工作区同名文件；便于阅读和分享的阶段报告；两版均记录到 Step 6a 实测前，最新结论见权威日志 |
| `sources/NLP_Experiment_Materials_2026-11-15.zip` | 源归档 | 前次交付快照，保留当时状态以便重现交付包 |
| `README.md` | 文档 | 仓库入口，介绍实验设计、阶段状态、导航和本地验证 |
| `PROGRESS.md` | 文档 | 从实验日志生成，按记录倒序定位实际条目 |
| `tools/sync_progress.py` | 脚本 | 生成除去时间戳的日志和进度页，保留条目顺序 |
| `.gitignore` | 版本配置 | 排除工作缓存、临时结果和常见本地凭据文件 |
| `docs/WORKFLOW.md` | 文档 | 实验记录、产物归档与进度同步方式 |
| `INDEX.md` | 文档 | 本次生成；按步骤导航、提供命令与关键结果 |
| `docs/INVENTORY.md` | 文档 | 本次生成；文件映射和整理理由 |
| `docs/RESULTS.md` | 文档 | 本次生成；逐条溯源的结果总表 |
| `docs/GAPS.md` | 文档 | 本次生成；标明需要补交的证据与统计 |
| `docs/ENVIRONMENT.md` | 文档 | 本次生成；依赖、环境变量、输出边界和测试实测 |

## 疑似重复与保留决定

- 工作区根目录有 12 个与 ZIP 字节一致的同名项，分别是 `bm25_topk.py`、`compare_models.py`、`README_step3.md`、`run_pilot.py`、`README_step5.md`、`audit_helper.py`、`analyze_signals.py`、`probe_logprobs.py`、`rerun_toplogprobs.py`、`README_step5b.md`、`check_logprobs.py`、`README_step6a.md`。每项在整理包有一个活动路径和一个原 ZIP 成员，工作区原文件仍在原位。如果组内要留平铺的 Windows 分发版本，这组文件可单独保留。
- 交接快照便于核对最初的报告范围，工作区原始日志还包含 Step 6a 实测和后续 V2 决定。
- Step 2 两份 `per_question.csv` 文件大小相同，但 SHA-256 不同，对应 m=1 与 m=2，两份都保留。两个 Step 3 mock 目录的文件名相同，但覆盖不同的功能路径，同样保留。
- `mini_pilot.json` 的题目可与完整 pilot 匹配，但测试代码直接读取该路径，随包保留。PDF/DOCX 阶段报告在阅读与编辑上用途不同，两版均保留。方案 v2 同时保留归档 PDF 和后到 DOCX，便于阅读和编辑。方案 PDF 和阶段报告 PDF 属于不同文档。

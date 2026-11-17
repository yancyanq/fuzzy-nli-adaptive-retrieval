# Group 13 V3.1 · P0 源码与实验归档审计

审计基线为提交 `11e6af5f0af455919eec64032e27389aeba47e36`。V2 正式结果在 `a6d4da5d1db4a4fa206a1f437e0c2bcd4b0b5d9d` 归档入库，随后增补手册。原正式运行本身没有可追溯的 Git commit，按原始输入哈希、权重哈希和配置锁识别。工作区顶层的同名副本用于核对历史用题，本次复算以仓库内归档为准。

## 入口与复用范围

| 环节 | V2 实际入口与证据 | V3.1 迁移点 |
|---|---|---|
| 协议、参数与结果 | [V2 协议](../../../docs/Experiment_Protocol_v2.md)、[实验日志](../../EXPERIMENT_LOG.md)、[参数册](../../v2/step6_v2/NLP_V2_Experiment_Parameters.md)、[正式结果](../../v2/step5_v2/quality_summary.json)、[复现清单](../../v2/step6_v2/Reproducibility_Checklist.md) | V2 分数作为历史参照，新池上的 V2 对照需同环境重测。 |
| 数据 | [pilot](../../step1/pilot.json)、[tune](../../v2/tune.json)、[formal](../../v2/test.json)；[数据审计](data_audit.md) | 保留标题和零起始句索引。线上仅传问题、资料及定位 ID。 |
| BM25、查询及答题 | [bm25_topk.py](../../v2/bm25_topk.py)、[compare_models.py](../../v2/compare_models.py) 中 `retrieve_indices`、`build_messages`、`parse_response`、`map_citations` | `rank_bm25==0.2.2`。先在全候选池排 top-2。V2 追加分支用问题、首段标题和首句重写，在未读材料中重新排序追加一段。 |
| 句级引用 | [generate_test_v2.py](../../v2/generate_test_v2.py) 中 `answer_request`、`sentence_candidates`、`selector_messages`、`select_evidence` | V2 作答返回段落编号，另一次选择器调用从这些段落选原文句，再映射回编号。选择器现有长度上限随旧 4096 配置写死，迁移到更长配置时需核对分束和调用成本。 |
| NLI 与门控 | [run_pilot.py](../../v2/run_pilot.py) 中 `build_premise`、`build_hypothesis`、`HFNliScorer`；[evaluate_test_v2.py](../../v2/evaluate_test_v2.py) 中 `inputs_for_nli`、`score_nli`、`run_live`；[calibrate_gates_v2.py](../../v2/calibrate_gates_v2.py) 和[门控锁](../../v2/step4_dev/gates/locked_gates.json) | V2 把草稿和问题拼成单条陈述，按引用段落构造前提，必要时回退检索段落。NLI 上限独立为 512 tokens。V2 模糊门控是用开发集校准参数的规则基线。 |
| 官方评分和统计 | [hotpot_evaluate_v1.py](../../v2/step5_v2/hotpot_evaluate_v1.py)、[evaluate_test_v2.py](../../v2/evaluate_test_v2.py) 的 `replay`、[analyze_step6_v2.py](../../v2/analyze_step6_v2.py) | 复用官方答案 EM/F1、支持句 F1 及题级配对口径。评分器上游 commit `fa3a36370899e1d85822de61e58c85ea19993154`，文件 SHA-256 `d35fc91a6db21d791dbdda11daf3856e9359f5701d54e3eefba20d88fecc02c0`。 |
| 缓存与服务 | [generate_test_v2.py](../../v2/generate_test_v2.py) 的 `read_cache`、`generate`，[批量开发脚本](../../v2/run_answers_batched_v2.sh)、[正式流程](../../v2/run_step5_v2.sh)、[服务启动](../../v2/step4_dev/.serve-step4.sh) | V2 答案／证据键使用模型、题号、分支。V3 需要加入材料池、顺序、提示词、revision、检索／核验版本，避免同题不同规模串缓存。 |

## 固定身份与归档验证

- Qwen `Qwen/Qwen2.5-7B-Instruct@a09a35458c702b33eeacc393d103063234e8bc28`，V2 原始 FP16、温度 0、回答和选句各预留 128 输出 tokens。四个模型分片哈希在启动脚本。本轮使用该 revision 的两份 tokenizer 文件进行离线计数，权重运行证据来自 V2 与 Kaggle 归档。
- DeBERTa `MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli@b3546ea6b0346eb6f8d5d68b13c7dc6d0376b3d7`。当时离线 NLI 使用 CUDA、batch 4，实时路径使用 CPU、4 线程；权重身份见门控锁。
- 重新通过 **23 项**复现身份、**12 项**开发归档、**27 项**正式归档的 SHA-256 校验。逐题核对正式 A、B、Full 的 **3000 条**检索索引和提示词 token，与历史服务记录完全一致。用缓存重跑正式评分，质量汇总、逐题表和 9 份预测逐字节一致。另复算 V3 Kaggle 的 10 条全文提示词 token，与 Notebook 导出一致。

## 失败探测与比较边界

- DeepSeek 温度 0 下的 chosen logprob 和 top-k margin 曾退化。固定 Qwen/vLLM 的 30 道 dev Step 6a 探测通过了接口辨别力检查，V2 正式门控最终使用 NLI 与桥接标题信号。见[实验日志](../../EXPERIMENT_LOG.md)及 [Step 6a 记录](../../step6a/step6a_check/logprob_check.json)。
- 当时 Qwen 与 CUDA DeBERTa 在同一张 T4 共驻发生 OOM，实时路径改用 CPU NLI。正式回放曾遇到 SSH 中断、tmux 服务切换失败、NLI 缓存字段覆盖答题模型身份。保留的原始／修复缓存表明最后一项修的是元数据，概率值沿用。另有少量选择器格式错误和 NLI 截断。见[实验日志恢复段落](../../EXPERIMENT_LOG.md#executed-verify-completed-v2-generation-and-repair-the-launch-wrapper)。
- V2 正式 1000 题答案 F1 为 Never 50.85、Crisp 54.36、Fuzzy 54.42、Always 57.66、A/B Oracle 60.61、Full 64.27（百分制）。两条原始分支的 Oracle 是该归档的事后上界。V2 `run_live` 中 Always 直接用合并段落作答一次；自适应路径触发后会额外调用第二次生成。运行成本需保留这项差异。
- Kaggle 交接记录包含输出类型错误后的修正、十题短答案和 CPU NLI 冒烟。V3.1 文档也提到早期转述的 `UNKNOWN`／回退问题，本地审计未定位到该探测的可复算逐题原件，保留为文档记录。Kaggle `2+N` 为先扩检索再调用一次生成，适用于历史长度和单次生成耗时参考。

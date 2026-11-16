# NLP 课程项目实验索引

项目为 *A Fuzzy-NLI-based QA Chatbot System with Adaptive Retrieval*。在 HotpotQA distractor 的 bridge 题上，分支 A 使用 BM25 第一轮证据，分支 B 在相同基础上加入规则改写后检出的证据。作答模型输出答案和引用，NLI 检查引用证据对答案的支撑，V2 已完成补充 pilot、dev 校准、独立测试和配对统计。早期 Step 4–6a 与 Protocol V2 的步骤 4–6 使用不同的编号。

本索引的数字来自[实验日志](exp/EXPERIMENT_LOG.md)。以下命令按整理后的目录给出，从包根目录运行，`runs/` 用于新运行。日志与 README 保留历史路径。云 API、真实 NLI 和 vLLM 命令用于复现相应环节，执行条件见[运行环境](docs/ENVIRONMENT.md)。

## Step 1 数据切分

从 `hotpotqa/hotpot_qa` 的 distractor validation 筛选 bridge，seed 42 打乱并顺序切分，输出官方 HotpotQA JSON。**脚本和历史命令**记录中未给出，随包未收到切分脚本。**输出** `exp/step1/pilot.json`、`exp/step1/tune.json` 已收录，正式 `test.json` 已归档在 `exp/v2/test.json`。**关键结果** validation 7,405 题、bridge 5,918 题，pilot / tune / test 为 100 / 500 / 1,000 题，日志记录 1,600 个唯一 ID。原样保留不足 10 个上下文段落的题目。**日志** [选源](exp/EXPERIMENT_LOG.md?plain=1#L6)、[切分](exp/EXPERIMENT_LOG.md?plain=1#L13)、[tune 核验](exp/EXPERIMENT_LOG.md?plain=1#L289)。

## Step 2 BM25 召回

在每题自带段落池做 BM25 第一轮 top-k，再用问题拼接首位段落的标题及首句，从未使用段落中补 top-m。**脚本** `exp/step2/bm25_topk.py`。**命令** `python exp/step2/bm25_topk.py --data exp/step1/pilot.json --ks 2 3 4 --m 1 --out runs/step2_m1`，将 `--m 1 --out runs/step2_m1` 换为 `--m 2 --out runs/step2_m2` 可复跑另一组。**输出** 各有 `summary.json`、`per_question.csv`；已收录于 `exp/step2/step2_results/`（m=1）与 `exp/step2/step2_m2/`（m=2）。**关键结果** 选 k=2、m=1；此设置下支持段落平均召回从 .635 到 .785，两个支持段落均召回的比例从 .310 到 .590，30% 的题在第二轮补到支持段落。**日志** [验证](exp/EXPERIMENT_LOG.md?plain=1#L25)、[YangQS 复核](exp/EXPERIMENT_LOG.md?plain=1#L38)、[参数决定](exp/EXPERIMENT_LOG.md?plain=1#L45)。

## Step 3 作答模型试跑

对 pilot 前 30 题比较同一模型的 A/B 答案，记录 EM、F1、首轮及补检索后的变化、调用信息。**脚本** `exp/step3/compare_models.py`，说明见 `exp/step3/README_step3.md`。**命令** `python exp/step3/compare_models.py --data exp/step1/pilot.json --preset deepseek --n 30 --out runs/step3_deepseek`。**输出** `summary.json`、`per_question.csv`、`branches.jsonl`、`cache.jsonl`，真实文件待补。**关键结果** deepseek-chat 的 EM A/B 分别为 0.433/0.600，F1 A/B/Oracle 为 0.565/0.733/0.767，平均 ΔF1 +0.169；改善/持平/退化为 7/22/1。日志中的真实执行条目只有 deepseek-chat，GPT-4o-mini 实测记录中未给出。**日志** [算力方案](exp/EXPERIMENT_LOG.md?plain=1#L51)、[准备](exp/EXPERIMENT_LOG.md?plain=1#L57)、[执行](exp/EXPERIMENT_LOG.md?plain=1#L66)。

## Step 4 预注册

在 100 题 pilot 前锁定九项规则。**脚本、命令与独立输出**记录中未给出，批准记录见日志，后续由 `exp/step5/run_pilot.py` 实施。**规则** ε=0，正例为 F1_B>F1_A，Oracle 在平局选 A；GO 要求 Oracle−A 点估计 ≥0.05 且配对 bootstrap 95% CI 下界 >0，改善占比 ≥10%，退化数 ≤改善数的一半；若失败，改写规则最多修订一次。还锁定本地 DeBERTa NLI 与引用拼接和假设构造，最大输入 512 tokens，以及约 20 条的定性审核计划。**日志** [预注册决定](exp/EXPERIMENT_LOG.md?plain=1#L75)、[实现口径](exp/EXPERIMENT_LOG.md?plain=1#L134)。

## Step 5 Pilot、人工审核与信号诊断

先生成或复用 A/B 答案，再用本地 DeBERTa 做 NLI，用引用段落组成前提、固定模板组成假设；随后整理人工审核并离线分析首轮信号。**脚本** `exp/step5/run_pilot.py`、`audit_helper.py`、`analyze_signals.py`。**命令** `python exp/step5/run_pilot.py --data exp/step1/pilot.json --preset deepseek --n 100 --answer-cache runs/step3_deepseek/cache.jsonl --out runs/step5_pilot --skip-nli`；再执行 `python exp/step5/run_pilot.py --data exp/step1/pilot.json --preset deepseek --n 100 --out runs/step5_pilot --nli-only --nli-backend hf --nli-device auto`；审核和诊断分别用 `python exp/step5/audit_helper.py --dir runs/step5_pilot`、`python exp/step5/analyze_signals.py --dir runs/step5_pilot`。**输出** `summary.json`、`per_question.csv`、`branches.jsonl`、`nli_scores.jsonl`、`audit_sample.csv`、`cache.jsonl`、`audit_review.csv`、`signal_summary.json`、`signal_by_class.csv`。已收录真实 `exp/step5/step5_pilot/per_question.csv`、`exp/step5/step5_pilot/branches.jsonl` 和人工审核表 `exp/step5/audit_review_yangqs.csv`，其余需补。**关键结果** 100 题 pilot **GO**；F1 A/B/Oracle 为 0.628/0.752/0.765，改善/持平/退化为 16/82/2；Oracle−A 为 0.137，95% CI [0.077, 0.203]。审核覆盖 20 个题目–分支对、15 道题，属定性抽样；NLI 对改善与持平的诊断 AUC 为 0.699，95% CI [0.579, 0.812]，首轮 token logprob 为全零。**日志** [Pilot 结果](exp/EXPERIMENT_LOG.md?plain=1#L146)、[人工审核](exp/EXPERIMENT_LOG.md?plain=1#L163)、[诊断](exp/EXPERIMENT_LOG.md?plain=1#L179)、[逐题导出](exp/EXPERIMENT_LOG.md?plain=1#L356)、[V2 §7.3 候选设置](exp/EXPERIMENT_LOG.md?plain=1#L362)。

## Step 5b DeepSeek logprob 排查

先用短提示词探测，再保持 temperature 0 重跑 pilot A/B 并请求 top-5 候选；沿用 Step 5 标签，在 A/B 答案均未改变的题上比较 margin 与 NLI。**脚本** `exp/step5/probe_logprobs.py`（随 Step 5 原目录发行）与 `exp/step5b/rerun_toplogprobs.py`。**命令** `python exp/step5/probe_logprobs.py --preset deepseek --out runs/probe_logprobs.json`（先建立 `runs/`）；`python exp/step5b/rerun_toplogprobs.py --data exp/step1/pilot.json --step5-dir runs/step5_pilot --out runs/step5b_toplp`。**输出** `probe_logprobs.json`、`toplp_summary.json`、`per_question_toplp.csv`、`consistency.csv`、`cache_toplp.jsonl`，真实文件待补。**关键结果** 200 次重跑调用成功；3,482 个输出 token 的 top-1 候选均为 0.0，3,477 个 token 的 top-2 候选为占位值 −9999.0。主子集 88 题的 margin AUC 为 0.500 [0.500, 0.500]，同题 NLI AUC 为 0.724 [0.593, 0.844]。重跑结果条目纠正了探测时对非零候选的解读。**日志** [探测](exp/EXPERIMENT_LOG.md?plain=1#L192)、[重跑决定](exp/EXPERIMENT_LOG.md?plain=1#L199)、[实现](exp/EXPERIMENT_LOG.md?plain=1#L206)、[执行与纠正](exp/EXPERIMENT_LOG.md?plain=1#L218)。

## Step 6a 本地 vLLM 非退化检查

用 Tesla T4 上的 vLLM 运行原始 Qwen2.5-7B-Instruct，取 tune 前 30 题，仅分支 A，temperature 0、max_tokens 128、top_logprobs 5。**脚本** `exp/step6a/check_logprobs.py` 和 `README_step6a.md`。**命令** `python exp/step6a/check_logprobs.py --data exp/step1/tune.json --base-url http://127.0.0.1:8000/v1 --out runs/step6a_check`。如只复核，追加 `--analyze-only --cache exp/step6a/step6a_check/cache_logprob_check.jsonl` 即可离线回算。**输出** `exp/step6a/step6a_check/` 下的 `logprob_check.json`、`logprob_check_tokens.csv`、`cache_logprob_check.jsonl` 均随包。**关键结果** 实测 **PASS**，30/30 题有可用 logprobs；答案片段选中 token 的零值 28/127（22.05%，门槛 ≤50%，按保留六位小数），占位候选（≤−9000）0/2595（0.00%，门槛 <5%）；逐题 mean logprob 与 mean margin 各 30 个不同值（门槛 ≥10），总体方差分别为 0.023727663329 和 15.391864434601（门槛 >0）。两种信号可作候选；V2 将不确定性输入列为条件项，正式纳入时须供 Fuzzy 与同输入硬规则共用。**日志** [预注册与实现](exp/EXPERIMENT_LOG.md?plain=1#L241)、[执行准备](exp/EXPERIMENT_LOG.md?plain=1#L289)、[实测](exp/EXPERIMENT_LOG.md?plain=1#L326)、[后续决定](exp/EXPERIMENT_LOG.md?plain=1#L338)。

## V2 §7.3 补充 Pilot 信号比较

用原 100 题及 A/B 缓存，按共同 20 题预算比较 NLI 与 NLI＋桥接信号。两种方法各选中 6 道改善、14 道持平、0 道退化题。运行方法见 [Pilot README](exp/v2/README_pilot_signals_v2.md)，输出为 [摘要和逐题选题表](exp/v2/pilot_signals_v2/)。 [实测日志](exp/EXPERIMENT_LOG.md?plain=1#L415)

## V2 步骤 4 Dev 校准

用 500 题、1,000 条 A/B 分支对两种同输入门控校准，目标为选择 100 道题。在 `exp/v2` 运行 `python calibrate_gates_v2.py --tune tune.json --branches step4_dev/nli/branches.jsonl --serve-script step4_dev/.serve-step4.sh --out ../../runs/v2_gates`。Fuzzy / Crisp 的 dev F1 为 0.536217749 / 0.535208225，两者共享 85 个选中的 ID。 [启动与运行说明](exp/v2/README_step4_v2.md) · [锁文件和校准输出](exp/v2/step4_dev/gates/) · [完成日志](exp/EXPERIMENT_LOG.md?plain=1#L482)

## V2 步骤 5 正式评估

1,000 题使用冻结门控和官方 HotpotQA 评分器回放九种策略。独立的共用 32 题子集用于六种策略的真实路径计时。正式生成由 `run_step5_v2.sh` 调度 `generate_test_v2.py` 和 `evaluate_test_v2.py`，离线运行命令见 [可复现性清单](exp/v2/step6_v2/Reproducibility_Checklist.md)。Fuzzy / Crisp 的答案 F1 为 0.54424354 / 0.54360782，实测正式再检索率为 23.0% / 20.9%。 [运行说明](exp/v2/README_step5_v2.md) · [正式产物](exp/v2/step5_v2/) · [完成日志](exp/EXPERIMENT_LOG.md?plain=1#L573)

## V2 步骤 6 配对统计、案例与论文

在 `exp/v2` 运行 `python analyze_step6_v2.py --test test.json --results step5_v2 --out ../../runs/v2_analysis`，由缓存生成配对区间、案例证据和质量–成本图。Fuzzy − Crisp 为 +0.064 个 F1 百分点，95% 区间 [−0.365, +0.517]。正式报告、论文预览、填入 §11 的方案副本和独立结果册均已归档。 [分析产物](exp/v2/step6_v2/) · [人工复核表](exp/v2/case_review/) · [统计日志](exp/EXPERIMENT_LOG.md?plain=1#L611) · [结果册日志](exp/EXPERIMENT_LOG.md?plain=1#L648)

## 材料导航

- [最新实验进度](PROGRESS.md)与[协作工作流](docs/WORKFLOW.md)
- [文件清单、归档映射与待确认副本](docs/INVENTORY.md)
- [结果汇总表](docs/RESULTS.md)
- [论文写作与复现缺口](docs/GAPS.md)
- [依赖、环境、测试与实际验证](docs/ENVIRONMENT.md)
- 实验方案 v2 [PDF](docs/Experiment_Protocol_v2.pdf) / [DOCX](docs/Experiment_Protocol_v2.docx)，阶段报告 [PDF](reports/Interim_Experiment_Report_2026-11-15.pdf) / [DOCX](reports/Interim_Experiment_Report_2026-11-15.docx)（Step 6a 实测前快照）

# 论文写作与复现缺口

这份清单以当前入库文件为界。YangQS 的 `G:\NLP_project\` 与 GPU 服务器没有在本次整理中读取。下列“需补”指随包未收到。指标状态以[权威日志](../exp/EXPERIMENT_LOG.md)为准，后续按 15:01 日志决定执行[实验方案 v2](Experiment_Protocol_v2.pdf)，先完成第 7.3 节及第 10.1 节步骤 3 的 pilot 信号检查。

| 优先级 | 环节 | 待补材料或计算 | 对论文和复现的用途 |
| --- | --- | --- | --- |
| 高 | Step 1 | 从 YangQS 补 `test.json`、原始 Parquet 的完整文件名和 SHA-256、下载的源 revision、切分转换脚本及确切命令，必要的版本或依赖锁。切分命令和原始哈希值记录中未给出。 | 重建相同顺序与分区，检验 test 和 pilot/tune 的 ID 隔离。已有 `pilot.json` 与 `tune.json`，包内已重查这两个集合。 |
| 中 | Step 2 | 包内已有 m=1 与 m=2 的 `summary.json`、`per_question.csv`。若论文要求原始运行链，补 YangQS 的 `step2_m1/`、`step2_m2/` 的文件哈希或原始导出副本。历史日志确认指标一致，Windows 文件逐字节一致性记录中未给出。 | 把便携运行副本与实际 YangQS 产物建立可核验的对应。 |
| 高 | Step 3 | `step3_deepseek/{summary.json,per_question.csv,branches.jsonl,cache.jsonl}`。日志列出前两个路径，另外两个由脚本/README定义；Step 5 记录复用 Step 3 答案缓存。GPT-4o-mini 实测和实际费用记录中未给出。 | 实证支撑模型选择；逐题核对分支、解析、耗时和 tokens，复用同批答案。若论文声称做过两模型实测比较，还需补第二个模型的实测或修正措辞。 |
| 高 | Step 5 | `step5_pilot/{summary.json,nli_scores.jsonl,audit_sample.csv,cache.jsonl}`。真实的 `per_question.csv` 和 `branches.jsonl` 于 15:07 确认收到并入库；填完的人工审核表已收录为 `audit_review_yangqs.csv`；如需审核全链，还需抽样母表和生成审核表的原始输入。 | 重算 GO、复核证据与误判、区分分层定性样本和总体，恢复可审计的 A/B 共享缓存。 |
| 高 | Step 5 诊断 | `step5_pilot/{signal_summary.json,signal_by_class.csv}`。日志有 AUC 与置信区间；各预设规则的实际再检索率、分组完整统计及均值差置信区间记录中未给出。 | 离线复核诊断，给出分布与不确定性；保留 pilot 的探索性口径。 |
| 高 | Step 5b | `probe_logprobs.json`、`step5b_toplp/{toplp_summary.json,per_question_toplp.csv,consistency.csv,cache_toplp.jsonl}`；取该批次的终端记录或带时间的运行元数据。 | 复核占位值、各分支答案变化、同题 AUC 子集。补齐文件后可离线重算。 |
| 中 | Step 6a 服务器证据 | `logprob_check.json`、`logprob_check_tokens.csv` 和 `cache_logprob_check.jsonl` 已随包，可离线复核 PASS。待补服务器原始启动封装 `~/nlp/.serve-step6a.sh`、`~/nlp/logs/requirements-step6a.lock`、服务日志、安装报告和分片校验清单。 | 复现经过校验的原始 checkpoint 与服务配置，核对部署与运行的完整证据。单次真实执行和客户端统计已有日志与结果文件。 |
| 高 | V2 的 pilot 信号对照 | 在 pilot 上补齐 NLI 与桥接实体信号，于相近的再检索率下和随机选择或单阈值比较，记录选中的改善题与退化题。桥接信号、对照方式和预算在 15:13 有候选提议，批准设置和检查结果记录中未给出。后来确定的设置应注明实际确定日期。 | 完成 V2 第 7.3 节和第 10.1 节步骤 3。现有 NLI AUC 是描述性诊断，另需上述对照。 |
| 高 | Dev 调参与方案锁定 | tune 两分支缓存和首轮信号、同输入且按共同目标再检索率调参的 Fuzzy/硬规则配置，锁定 prompt 与规则改写版本、确定正式样本量与划分。logprob 已通过非退化检查，V2 将是否纳入与度量留待决定；如纳入，两种门控均需接收该输入。实际阈值、目标再检索率、最终样本量和正式评价结果记录中未给出。 | 固定主比较条件后再做独立 test。Step 1 的 1,000 是已切出的 test 规模。 |
| 高 | 正式 test 与误差估计 | 逐题 A/B 缓存、策略选择、Never/Always/Oracle、Fuzzy、同输入硬规则等对照/消融、单独的 Full-context 运行。需要答案 F1、EM、实际再检索率、token 与端到端延迟、逐题配对差值和 bootstrap CI；门控精确率/召回率/F1、质量–成本图、按改善/持平/退化分层及错误分析待补。实际预算或费用记录中未给出。 | 填写方案主表和消融表，区分离线缓存模拟的成本与真实路径延迟。正式比较的点估计、CI 和其他统计检验记录中未给出。是否做额外配对检验依正式方案。 |
| 高 | 官方支持事实指标 | Step 5 现有引用是标题级，脚本在缺少句索引时将官方 sentence-level supporting-fact F1 置空。若论文报告该指标，需补句级预测与评估输出（及官方评估脚本或固定版本）；否则在正式方案明确当前标题级覆盖口径。 | 区分支持段落覆盖和官方句级指标。日志没有 Step 5 可报告的官方 supporting-fact F1。 |
| 中 | 历史运行环境 | Step 2–5b Windows 环境的 Python/pip 冻结文件、NLI 模型 revision/快照、实际设备/驱动信息和 API 响应元数据。Step 6a 已知版本见运行环境。 | 定位版本差异。真实 API 复跑可能出现与历史不同的答案，优先保全历史缓存并在报告中说明复跑记录。 |

补齐后可以把设备产物放到新目录 `runs/step3_deepseek/`、`runs/step5_pilot/`与 `runs/step5b_toplp/`。保留文件名、运行日期与来源设备，先扫描凭据再放入共享包。本包含方案 PDF 与整理时出现的可编辑 DOCX。阶段报告的 PDF 与 DOCX 两版均早于 14:52 实测，正式稿需要增补 Step 6a 的 PASS 与后续使用范围。

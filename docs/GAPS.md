# 论文写作与复现缺口

这份清单以当前入库文件为界。本地原始工作目录与 GPU 服务器没有在本次整理中读取。下列“需补”指随包未收到。指标状态以[权威日志](../exp/EXPERIMENT_LOG.md)为准，后续按[方案执行决定](../exp/EXPERIMENT_LOG.md?plain=1#L343)落实[实验方案 v2](Experiment_Protocol_v2.pdf)。V2 §7.3 与步骤 4–6 已完成，见[正式实验归档](../exp/v2/README.md)。

| 优先级 | 环节 | 待补材料或计算 | 对论文和复现的用途 |
| --- | --- | --- | --- |
| 高 | Step 1 | 已归档[正式测试集](../exp/v2/test.json)。待补原始 Parquet 的完整文件名和 SHA-256、下载的源 revision、切分转换脚本及确切命令，必要的版本或依赖锁。切分命令和原始哈希值记录中未给出。 | 重建相同顺序与分区，检验 test 和 pilot/tune 的 ID 隔离。日志已核对 pilot、dev、test 互不相交。 |
| 中 | Step 2 | 包内已有 m=1 与 m=2 的 `summary.json`、`per_question.csv`。若论文要求原始运行链，补原始 `step2_m1/`、`step2_m2/` 的文件哈希或原始导出副本。历史日志确认指标一致，逐字节一致性记录中未给出。 | 把便携运行副本与实际原始产物建立可核验的对应。 |
| 高 | Step 3 | `step3_deepseek/{summary.json,per_question.csv,branches.jsonl,cache.jsonl}`。日志列出前两个路径，另外两个由脚本/README定义；Step 5 记录复用 Step 3 答案缓存。GPT-4o-mini 实测和实际费用记录中未给出。 | 实证支撑模型选择；逐题核对分支、解析、耗时和 tokens，复用同批答案。若论文声称做过两模型实测比较，还需补第二个模型的实测或修正措辞。 |
| 高 | Step 5 | `step5_pilot/{summary.json,nli_scores.jsonl,audit_sample.csv,cache.jsonl}`。真实的 `per_question.csv` 和 `branches.jsonl` 已确认收到并入库；填完的人工审核表已收录为 `audit_review_yangqs.csv`；如需审核全链，还需抽样母表和生成审核表的原始输入。 | 重算 GO、复核证据与误判、区分分层定性样本和总体，恢复可审计的 A/B 共享缓存。 |
| 高 | Step 5 诊断 | `step5_pilot/{signal_summary.json,signal_by_class.csv}`。日志有 AUC 与置信区间；各预设规则的实际再检索率、分组完整统计及均值差置信区间记录中未给出。 | 离线复核诊断，给出分布与不确定性；保留 pilot 的探索性口径。 |
| 高 | Step 5b | `probe_logprobs.json`、`step5b_toplp/{toplp_summary.json,per_question_toplp.csv,consistency.csv,cache_toplp.jsonl}`；取该批次的终端记录或带时间的运行元数据。 | 复核占位值、各分支答案变化、同题 AUC 子集。补齐文件后可离线重算。 |
| 中 | Step 6a 服务器证据 | `logprob_check.json`、`logprob_check_tokens.csv` 和 `cache_logprob_check.jsonl` 已随包，可离线复核 PASS。待补服务器原始启动封装 `~/nlp/.serve-step6a.sh`、`~/nlp/logs/requirements-step6a.lock`、服务日志、安装报告和分片校验清单。 | 复现经过校验的原始 checkpoint 与服务配置，核对部署与运行的完整证据。单次真实执行和客户端统计已有日志与结果文件。 |
| 高 | 官方支持事实指标 | Step 5 现有引用是标题级，脚本在缺少句索引时将官方 sentence-level supporting-fact F1 置空。V2 正式 test 已有句级预测和固定版官方评分器；早期 DeepSeek pilot 没有句级预测归档。 | 区分支持段落覆盖和官方句级指标。日志没有 Step 5 可报告的官方 supporting-fact F1。 |
| 中 | 历史运行环境 | Step 2–5b 历史环境的 Python/pip 冻结文件、NLI 模型 revision/快照、实际运行环境/驱动信息和 API 响应元数据。Step 6a 已知版本见运行环境。 | 定位版本差异。真实 API 复跑可能出现与历史不同的答案，优先保全历史缓存并在报告中说明复跑记录。 |

补齐后可以把设备产物放到新目录 `runs/step3_deepseek/`、`runs/step5_pilot/`与 `runs/step5b_toplp/`。保留文件名、运行日期与来源设备，先扫描凭据再放入共享包。本包含方案 PDF 与整理时出现的可编辑 DOCX。阶段报告的 PDF 与 DOCX 两版为 Step 6a 实测前快照，正式稿需要增补 Step 6a 的 PASS 与后续使用范围。

## V2 正式实验的待补项

| 环节 | 待补或需明确的范围 |
| --- | --- |
| 代表案例复核 | [复核目录](../exp/v2/case_review/)有空表及已填写副本。[日志](../exp/EXPERIMENT_LOG.md?plain=1#L653)已核对三例返回内容；复核人姓名栏为空，复核意见尚未整合进论文错误分析。 |
| 从权重复跑 | [复现清单](../exp/v2/step6_v2/Reproducibility_Checklist.md)验证了从既有缓存回放。新一轮生成、独立 NLI 推理与重新计时记录中未给出。GPU 服务端完整依赖锁仍待补。 |
| 额外统计与泛化 | 每题已有五组预登记对比所需的缓存和分数。多重比较校正、预设等效界限、额外样本或硬件比较记录中未给出。 |

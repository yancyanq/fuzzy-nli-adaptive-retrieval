# 实验结果总表

每行的数值按[权威实验日志](../exp/EXPERIMENT_LOG.md)原值转录。来源栏链接到具体日志段落。A 为首轮证据，B 为首轮加二轮证据。表中的「双支持」指检回两个 gold 支持段落，「补获」指二轮新增 gold 段落的题目比例。表中包含预注册设置、历史真实运行记录和环境预检查，分别标明；mock 数据及本次整理时的测试数字见[运行环境](ENVIRONMENT.md)。

## V2 正式结果

表中的质量指标和再检索率来自同一批 1,000 道正式题。Supp-F1 采用官方句级指标。门控精确率、召回率及选题组成见归档。 [正式完成条目](../exp/EXPERIMENT_LOG.md?plain=1#L573-L590) · [质量汇总](../exp/v2/step5_v2/quality_summary.json)

| 策略 | 答案 F1 | EM | Supp-F1 | 再检索率 |
| --- | ---: | ---: | ---: | ---: |
| Never | 0.50848218 | 0.401 | 0.47511219 | 0.0% |
| Always | 0.57657564 | 0.462 | 0.52378889 | 100.0% |
| NLI-only | 0.53893035 | 0.427 | 0.50146111 | 21.9% |
| Crisp | 0.54360782 | 0.430 | 0.50215505 | 20.9% |
| Fuzzy | 0.54424354 | 0.432 | 0.50242778 | 23.0% |
| Full-context | 0.64265380 | 0.502 | 0.54903398 | 0.0% |
| A/B Oracle | 0.60606539 | 0.492 | 0.51348362 | 12.3% |
| Fuzzy 无 NLI | 0.56816135 | 0.452 | 0.51939949 | 66.0% |
| Fuzzy 无桥接 | 0.53793035 | 0.426 | 0.49979444 | 20.7% |

以下成本结果来自六种真实策略共用的 32 题子集。T4 运行 Qwen，NLI 使用 CPU。Full-context 在一次路径中直接给出所有候选段落；Oracle 质量来自 A/B 缓存选优。 [计时条目](../exp/EXPERIMENT_LOG.md?plain=1#L591-L602) · [端到端时延与调用汇总](../exp/v2/step5_v2/latency_summary.json)

| 策略 | 平均延迟（秒） | P50（秒） | P95（秒） | 平均 LLM 输入 tokens | 平均 LLM 输出 tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Never | 19.2633 | 19.2056 | 24.4067 | 697.75000 | 27.28125 |
| Always | 19.1285 | 18.7735 | 23.5562 | 814.65625 | 26.37500 |
| NLI-only | 23.3239 | 22.4733 | 31.1079 | 810.18750 | 30.84375 |
| Crisp | 22.8259 | 21.7110 | 31.2132 | 800.93750 | 30.28125 |
| Fuzzy | 23.3623 | 22.4659 | 31.2830 | 810.18750 | 30.84375 |
| Full-context | 24.9149 | 24.4573 | 31.4079 | 1916.75000 | 27.78125 |

下表使用以题为单位的配对 bootstrap，10,000 次重采样、种子 42，报告单项 95% 区间。 [统计条目](../exp/EXPERIMENT_LOG.md?plain=1#L611-L617) · [配对区间 CSV](../exp/v2/step6_v2/paired_bootstrap.csv)

| 预登记对比 | 答案 F1 差（百分点） | 95% 区间（百分点） |
| --- | ---: | --- |
| Fuzzy − Crisp | +0.064 | [−0.365, +0.517] |
| Fuzzy − NLI-only | +0.531 | [+0.155, +0.994] |
| Fuzzy − Never | +3.576 | [+2.265, +4.914] |
| A/B Oracle − Never | +9.758 | [+8.059, +11.471] |
| Full-context − Fuzzy | +9.841 | [+7.098, +12.614] |

| 正式前阶段 | 关键结果 | 来源 |
| --- | --- | --- |
| V2 §7.3 补充 pilot | 20/100 同预算下，NLI 与 NLI＋桥接均选中 6 道改善、14 道持平、0 道退化题；随机选择的对应理论期望为 3.2 / 16.4 / 0.4 | [补充 pilot 条目](../exp/EXPERIMENT_LOG.md?plain=1#L415-L428) |
| V2 步骤 4 校准 | 500 道 dev 题、共同目标 20%；Fuzzy F1 0.536217749、Crisp 0.535208225、NLI 阈值 0.532084416；Fuzzy 与 Crisp 共选中 85 题 | [校准条目](../exp/EXPERIMENT_LOG.md?plain=1#L482-L488) |

## V3.1 正式结果

V3.1 把候选池扩到 10／30／60 段，正式主比较为 300 道封存题、30 段、验证目标 20% 补查预算。质量与成本口径见 [P5 报告](../exp/v3/p5/REPORT.md)。 [配对区间](../exp/v3/p5/analysis/paired_intervals.csv) · [质量–成本曲线](../exp/v3/p5/analysis/quality_cost.csv)

| 方法 | 答案 F1 | EM | 支持句 F1 | 每题 Qwen 输入 token | 实际补查 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 完整 Sugeno seed 42 | 0.4464 | 0.3367 | 0.4536 | 802.03 | 49／300（16.33%） |
| 固定 Fuzzy | 0.4364 | 0.3333 | 0.4514 | 799.32 | 47／300（15.67%） |
| 线性收益回归 | 0.4464 | 0.3367 | 0.4536 | 802.03 | 49／300（16.33%） |
| Qwen 自检 | 0.4078 | 0.3100 | 0.4442 | 1,226.04 | 28／300（9.33%） |
| V2 原门控 | 0.4211 | 0.3233 | 0.4529 | 796.66 | 87／300（29.00%） |
| BM25 top-2 | 0.3961 | 0.3000 | 0.4307 | 643.28 | — |
| 原 2+1 直读 | 0.4650 | 0.3533 | 0.4848 | 797.91 | — |
| 原查询 2+4 直读 | 0.5377 | 0.4233 | 0.5140 | 1,252.14 | — |
| Full（30 段） | 0.5791 | 0.4600 | 0.4775 | 4,710.76 | — |

| 预登记比较（左减右） | 答案 F1 差 | 95% 配对区间 | 97.5% 校正区间 |
| --- | ---: | --- | --- |
| Sugeno − 固定 Fuzzy | +1.00 个百分点 | [−1.33, +3.33] | [−1.65, +3.61] |
| Sugeno − 线性收益回归 | 0.00 个百分点 | [0.00, 0.00] | [0.00, 0.00] |

Sugeno 触发 49 题中 19 题改善、29 题持平、1 题退化，另漏掉 49 道可改善题。原 2+1 直读以约 798 输入 token 得到 46.50%，在主样本上优于主档 20% Sugeno 的点估计。

**开发阶段对照（P1.5，50 题）。** 30 段 Full F1 56.73%、4,341 输入 token、32.47 秒；两阶段 2+4 F1 59.92%、1,316 token、23.59 秒，配对差 +3.19 个百分点、探索性 95% 区间 [−11.27, +17.77]。10 段以 2+4 获得 70.68%；60 段以 2+2 获得 58.65%。 [P1.5 报告](../exp/v3/p1_5/REPORT.md)

**关系核验（P2）。** 约束复测结构通过 96%（48／50），121／121 条引用可定位；人工复核的确定性忠实率 46.43%（26／56），低于 90% 门槛，正式路线回退到 V2 整题 NLI 与桥接代理。 [P2 报告](../exp/v3/p2/REPORT.md)

**试训（P4）。** 完整 Sugeno 验证 MSE 0.15454，线性收益回归 0.15887，常数 0.18104；四档补查预算下三个 Sugeno 种子与线性回归选中的题逐档相同。 [P4 报告](../exp/v3/p4/validation_report.md)

[P1.5 完成](../exp/EXPERIMENT_LOG.md?plain=1#L771) · [P2 验收](../exp/EXPERIMENT_LOG.md?plain=1#L817) · [P5 正式机测](../exp/EXPERIMENT_LOG.md?plain=1#L840)

## 早期实验结果


| 步骤 | 指标与范围 | 日志数值或状态 | 来源条目 |
| --- | --- | --- | --- |
| 1 | HotpotQA distractor validation 与筛选 | 7,405 题；bridge 5,918；seed 42 | [日志 L13](../exp/EXPERIMENT_LOG.md?plain=1#L13-L16) |
| 1 | pilot / tune / test | 100 / 500 / 1,000；1,600 个唯一 ID | [日志 L17](../exp/EXPERIMENT_LOG.md?plain=1#L17-L23) |
| 1 / 6a | 随包 pilot 与工作区 tune 的历史交叉核验 | tune 500 道 bridge、500 个唯一 ID，与归档 pilot 100 题无重叠；未核验 test | [日志 L289](../exp/EXPERIMENT_LOG.md?plain=1#L289-L294) |
| 2 | k=2、m=1 | 首轮召回 / 双支持 .635 / .310；加入二轮后 .785 / .590；补获 30% | [日志 L31](../exp/EXPERIMENT_LOG.md?plain=1#L31-L32) · [日志 L38](../exp/EXPERIMENT_LOG.md?plain=1#L38-L42) |
| 2 | k=3、m=1 | 首轮 .710 / .450；加入二轮后 .830 / .670；补获 24% | [日志 L33](../exp/EXPERIMENT_LOG.md?plain=1#L33) · [日志 L38](../exp/EXPERIMENT_LOG.md?plain=1#L38-L42) |
| 2 | k=4、m=1 | 首轮 .755 / .540；加入二轮后 .885 / .770；补获 26% | [日志 L34](../exp/EXPERIMENT_LOG.md?plain=1#L34) · [日志 L38](../exp/EXPERIMENT_LOG.md?plain=1#L38-L42) |
| 2 | m=2，按 k=2 / 3 / 4 | 加入二轮后的召回 / 双支持分别为 .845 / .700、.880 / .770、.920 / .840；补获 42% / 33% / 31% | [日志 L35](../exp/EXPERIMENT_LOG.md?plain=1#L35) · [日志 L38](../exp/EXPERIMENT_LOG.md?plain=1#L38-L42) |
| 2 | 行数、余量与最终选择 | 每组 300 行（100 题 × 3 个 k）；k≤4 时都有未用段落。选 k=2、m=1；同为 3 段，二轮双支持 59%，k=3 单轮 45% | [日志 L38](../exp/EXPERIMENT_LOG.md?plain=1#L38-L48) |
| 3 | deepseek-chat，pilot 前 30 题 | 60 次调用成功，0 次解析失败；日志记载返回了 logprobs 字段 | [日志 L66](../exp/EXPERIMENT_LOG.md?plain=1#L66-L67) · [日志 L179](../exp/EXPERIMENT_LOG.md?plain=1#L179-L185) · [日志 L218](../exp/EXPERIMENT_LOG.md?plain=1#L218-L239) |
| 3 | 答案质量 A / B / Oracle | EM A/B 0.433 / 0.600；F1 0.565 / 0.733 / 0.767；平均 ΔF1 +0.169；改善/持平/退化 7/22/1；Oracle−B 0.034、Oracle−A 0.202 | [日志 L68](../exp/EXPERIMENT_LOG.md?plain=1#L68-L71) |
| 3 | 原始 API 资源 | 26,713 tokens（输入 25,639、输出 1,074）；平均 0.697 s/次；费用记录中未给出 | [日志 L70](../exp/EXPERIMENT_LOG.md?plain=1#L70) |
| 4 | 预注册的标签与 GO 门槛 | ε=0；F1_B>F1_A 为正例，平局 Oracle 选 A；Oracle−A ≥0.05 且配对 bootstrap 95% CI 下界 >0；改善 ≥10%，退化 ≤改善的一半 | [日志 L79](../exp/EXPERIMENT_LOG.md?plain=1#L79-L112) |
| 4 | 预注册的执行与审核设置 | 失败时改写最多修订一次；NLI 最大 512 tokens；审核目标 20 条、3 类约各 6–7 条 | [日志 L114](../exp/EXPERIMENT_LOG.md?plain=1#L114-L130) |
| 5 | Pilot 答案质量与分类 | EM A/B 0.520 / 0.650；F1 A/B/Oracle 0.628 / 0.752 / 0.765；平均 ΔF1 +0.124；改善/持平/退化 16/82/2；退化与改善之比 0.125 | [日志 L146](../exp/EXPERIMENT_LOG.md?plain=1#L146-L149) |
| 5 | Pilot 预注册判定 | Oracle−A 0.137，95% CI [0.077, 0.203]（配对 bootstrap B=10000、seed 42）；改善比例 16%；Oracle−B 0.013；**GO** | [日志 L150](../exp/EXPERIMENT_LOG.md?plain=1#L150-L153) |
| 5 | Pilot NLI | 200 条（A 100，B 100）；截断 0/200（0%），回退到检索段落 0 次；平均蕴含概率 A/B 0.876 / 0.923 | [日志 L151](../exp/EXPERIMENT_LOG.md?plain=1#L151) |
| 5 | 人工审核，定性 | 20 个题目–分支对，15 道独立题（5 道 A/B 都出现）；人判答案正确 yes/no 7/13，证据支持 yes/no 2/18；`nli_correct` 11、`nli_wrong_lexical` 6、`nli_wrong_multihop` 2、`nli_wrong_other` 1、`nli_wrong_hypothesis` 0 | [日志 L163](../exp/EXPERIMENT_LOG.md?plain=1#L163-L171) |
| 5 | 审核交叉表，定性 | false_entailment 7（词汇 6、其他 1）；false_non_entailment 7（判对 5、多跳 2，来自同一题）；truncated_or_disagreement 6（均判对） | [日志 L166](../exp/EXPERIMENT_LOG.md?plain=1#L166-L169) |
| 5 | 真实逐题导出 | `per_question.csv` 和 `branches.jsonl` 各有 100 个不同 ID，与 pilot 一致。V2 §7.3 信号对照仅提出候选方案，未运行 | [日志 L356](../exp/EXPERIMENT_LOG.md?plain=1#L356-L360) · [日志 L362](../exp/EXPERIMENT_LOG.md?plain=1#L362-L368) |
| 5 | 首轮 NLI 描述性诊断 | 改善/持平/退化的蕴含均值 0.798 / 0.888 / 0.989（退化仅 2 题）；改善 vs 持平 AUC 0.699，95% CI [0.579, 0.812]（B=5000、seed 42，低值指向改善） | [日志 L179](../exp/EXPERIMENT_LOG.md?plain=1#L179-L181) |
| 5 | 首轮 DeepSeek logprob 描述性诊断 | 100 条 A 响应的已记录 token logprob 全为 0.0；mean/min 两信号各类均值 0.000，AUC 0.500 [0.500, 0.500] | [日志 L182](../exp/EXPERIMENT_LOG.md?plain=1#L182-L185) |
| 5b | DeepSeek 探测，非零候选的解释随后更正 | 2 条提示 × 温度 0/1，共 4 次；T=0 两个输出（1、2 tokens）全零；T=1 首提示 min/mean −0.000001073，第二提示 min −0.4549、mean −0.2275（2 个中 1 个为 0）。「非零候选」计数包含占位值 | [日志 L187](../exp/EXPERIMENT_LOG.md?plain=1#L187-L190) · [日志 L192](../exp/EXPERIMENT_LOG.md?plain=1#L192-L197) · [日志 L235](../exp/EXPERIMENT_LOG.md?plain=1#L235) |
| 5b | 重跑规模与答案一致性 | 200 次成功；A 变 9、B 变 4，合计涉及 12 道不同题；主子集 88 题 | [日志 L218](../exp/EXPERIMENT_LOG.md?plain=1#L218-L229) |
| 5b | 主分析，A/B 均未变 | margin AUC 0.500 [0.500, 0.500]；同题 NLI AUC 0.724 [0.593, 0.844] | [日志 L224](../exp/EXPERIMENT_LOG.md?plain=1#L224-L226) |
| 5b | 敏感性分析，全部 100 题 | margin AUC 0.482 [0.457, 0.500]；同题 NLI AUC 0.699 [0.579, 0.812] | [日志 L224](../exp/EXPERIMENT_LOG.md?plain=1#L224-L227) |
| 5b | 占位值退化 | 3,482 个输出 token（A 1,703、B 1,779）的 top-1 都为 0.0；3,477 个 top-2 为 −9999.0；88 题的 mean_margin_A 全为 9999.0 | [日志 L230](../exp/EXPERIMENT_LOG.md?plain=1#L230-L239) |
| 6a | 预注册输入与判定 | tune 前 30 题，branch A，T=0，k=2，max_tokens 128、top_logprobs 5；零值 ≤50%，占位值（≤−9000）占比 <5%；两个逐题均值各至少 10 个不同值且非零方差；全部题须有可用 logprobs | [日志 L241](../exp/EXPERIMENT_LOG.md?plain=1#L241-L280) · [日志 L316](../exp/EXPERIMENT_LOG.md?plain=1#L316-L319) |
| 6a | 环境和离线预检查 | 前 30 个 prompt 247–608 tokens；最长加 128 为 736，服务限制 4,096；最终 4 个权重分片 SHA-256 和 7 个配套文件 Git blob 校验通过 | [日志 L308](../exp/EXPERIMENT_LOG.md?plain=1#L308-L314) · [日志 L321](../exp/EXPERIMENT_LOG.md?plain=1#L321-L324) |
| 6a | 真实 vLLM 运行与完整性 | **PASS**；30 次 HTTP 200、30 个新响应、0 个缓存命中、0 个错误/不可用，30/30 题有可用 logprobs | [日志 L326](../exp/EXPERIMENT_LOG.md?plain=1#L326-L329) |
| 6a | 四项预注册判定 | 选中 token 零值 28/127 = 22.05%；占位候选 0/2595 = 0.00%；逐题 mean logprob 有 30 个不同值、总体方差 0.023727663329；逐题 mean margin 有 30 个不同值、总体方差 15.391864434601。四项均 PASS | [日志 L330](../exp/EXPERIMENT_LOG.md?plain=1#L330-L333) |
| 6a | 补充描述 | 519 个输出 token，全部输出中 209 个选中 logprob 为零；1 题回退到全部输出 token；30/30 题成功解析，EM 0.400000、F1 0.537460；请求延迟中位数 7.471 s、最小 6.190 s、最大 11.190 s | [日志 L334](../exp/EXPERIMENT_LOG.md?plain=1#L334) |
| 6a | 后续使用范围 | 两项 logprob 信号具备候选资格；V2 将不确定性指标与是否纳入列为条件项，纳入时两种同输入门控须共用。V2 实际锁定 NLI 与桥接输入，logprob 保留作诊断 | [日志 L338](../exp/EXPERIMENT_LOG.md?plain=1#L338-L341) · [日志 L343](../exp/EXPERIMENT_LOG.md?plain=1#L343-L348) |

Step 4 用温度 0 解释为何选择严格平局规则。Step 5b 同样在温度 0 下记录了答案变化，因此论文应把「固定温度」「固定缓存上的确定性评分」和「跨调用答案一致性」分别说明。Step 5 的 GO 通过的是 pilot 的三项条件，门控表现见本页 V2 校准与独立正式评估。 [权威实验日志](../exp/EXPERIMENT_LOG.md)

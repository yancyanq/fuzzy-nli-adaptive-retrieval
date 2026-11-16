# V2 完整实验结论

A Fuzzy-NLI-based QA Chatbot System with Adaptive Retrieval

BNBU NLP 课程小组实验　｜　2026 年 11 月 16 日

<strong>总体结论&#32;</strong>在 HotpotQA bridge 多跳题的候选段落池中，门控可以只对部分题追加检索，同时提高相对首轮基线的平均答案质量。正式比较尚未确立模糊规则相对同输入硬规则的独立优势。选择系统时需要分别考虑追加检索的次数、端到端延迟和模型读入的文本量。

### 三个研究问题的答案

表 1&#32;&#32;研究问题与实验结论

<table>
<thead>
<tr>
<th><p>研究问题</p></th>
<th><p>数据支持的结论</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>RQ1<br />选题与质量成本</p></td>
<td><p>Fuzzy 以 23.0% 的再检索率，将答案 F1 相对 Never 提高了 3.576 个百分点。Always 与 Full-context 的 F1 更高，三者的检索与计算成本不同。</p></td>
</tr>
<tr>
<td><p>RQ2<br />模糊推理的独立贡献</p></td>
<td><p>Fuzzy 的答案 F1 高于单阈值 NLI 策略。对同输入硬规则，F1 配对差为 +0.064 个百分点，95% 区间跨零。</p></td>
</tr>
<tr>
<td><p>RQ3<br />NLI 与桥接信号的作用</p></td>
<td><p>去掉 NLI 后触发范围扩大，精确率降低。去掉桥接后触发率、正例召回和答案 F1 同时下降。两项消融沿用同一已锁定边界。</p></td>
</tr>
</tbody>
</table>

### 结论来自哪些数据

正式质量基于 1,000 道保留题，真实成本基于六种策略共用的 32 道题。数据限 HotpotQA distractor 公开 validation 划分的 bridge 题。该实验先做 100 题预实验，再在独立的 500 道校准题上锁定策略。

正式作答使用 Qwen2.5-7B-Instruct。A 提供 BM25 首轮前两段，B 再追加一段。Fuzzy 与同输入硬规则用 A 的证据支持度与桥接线索选择是否走 B。六种可执行策略与 A/B Oracle 的完整数值表见配套《V2 第 11 节实验结果与解读》。

页码导读　RQ1 选题与成本 2｜RQ2 与 RQ3 3｜预实验与适用范围 4｜错误分析 5｜英文结论与归档 6

## RQ1 何时值得再检索

### 门控的质量收益与漏选

Fuzzy 在 230 个触发中命中 56 个改善题，另有 157 个持平、17 个变差。正式集共有 123 个 B 优于 A 的问题，Fuzzy 覆盖其中 45.5%，漏掉 67 题。相对 Never，答案 F1 从 50.85% 升到 54.42%，EM 从 40.10% 升到 43.20%，句级 Supp-F1 从 47.51% 升到 50.24%。配对 F1 差的 95% 区间为 \[+2.265, +4.914\] 个百分点。

A/B Oracle 只在 B 的官方答案 F1 严格更高时切换，并在同分时保留 A。其 F1 为 60.61%，相对 Never 增加 9.758 个百分点，95% 区间为 \[+8.059, +11.471\]。这表示已有 A/B 分支中可争取的质量余量。Full-context 使用更大的证据预算，其结果可超过这个 A/B 上界。

### 三种成本有各自的取舍

表 2&#32;&#32;主要成本对照

<table>
<thead>
<tr>
<th><p>策略</p></th>
<th><p>答案 F1</p></th>
<th><p>再检索率</p></th>
<th><p>平均延迟<br />秒</p></th>
<th><p>平均总 LLM<br />token</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>Never</p></td>
<td><p>50.85%</p></td>
<td><p>0.0%</p></td>
<td><p>19.26</p></td>
<td><p>725.03</p></td>
</tr>
<tr>
<td><p><strong>Fuzzy</strong></p></td>
<td><p>54.42%</p></td>
<td><p>23.0%</p></td>
<td><p>23.36</p></td>
<td><p>841.03</p></td>
</tr>
<tr>
<td><p>Always</p></td>
<td><p>57.66%</p></td>
<td><p>100.0%</p></td>
<td><p>19.13</p></td>
<td><p>841.03</p></td>
</tr>
<tr>
<td><p>Full-context</p></td>
<td><p>64.27%</p></td>
<td><p>0.0%</p></td>
<td><p>24.91</p></td>
<td><p>1,944.53</p></td>
</tr>
</tbody>
</table>

F1 和再检索率用全部 1,000 题。延迟和 token 用共用的 32 道题，包含问答和最终句级选择。

<strong>相对 Always&#32;</strong>Fuzzy 少触发 77 个百分点的再检索，答案 F1 低 3.233 个百分点。在计时子集上，两者平均每题都是 841.03 个 LLM token，平均延迟分别为 23.36 秒和 19.13 秒。Always 可直接执行 B，而 Fuzzy 先生成 A、运行一次 NLI，触发时再生成 B。团队以本次观测差值报告取舍，非劣效判断需要事先规定可接受的质量差。

<strong>相对 Full-context&#32;</strong>它一次读入全部候选段落，所以再检索率为 0.0%。它比 Fuzzy 高 9.841 个百分点，95% 区间为 \[+7.098, +12.614\]。它达到本实验最高的 F1，也消耗约 2.31 倍的 LLM token，平均多用 1.55 秒。

归档依据 \[1\] \[2\] \[3\]。

## RQ2 模糊规则与 RQ3 信号消融

### RQ2 模糊推理的独立优势尚未确立

表 3&#32;&#32;Fuzzy 与两类门控的比较

<table>
<thead>
<tr>
<th><p>配对比较</p></th>
<th><p>F1 差<br />百分点</p></th>
<th><p>95% 配对区间<br />百分点</p></th>
<th><p>正式再检索率<br />左侧 / 右侧</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>Fuzzy − 同输入硬规则</p></td>
<td><p>+0.064</p></td>
<td><p>[-0.365, +0.517]</p></td>
<td><p>23.0% / 20.9%</p></td>
</tr>
<tr>
<td><p>Fuzzy − NLI 阈值</p></td>
<td><p>+0.531</p></td>
<td><p>[+0.155, +0.994]</p></td>
<td><p>23.0% / 21.9%</p></td>
</tr>
</tbody>
</table>

同输入硬规则与 Fuzzy 共用 A/B 输出、NLI 与桥接信号、规则结构及 20.0% 的校准目标。两者分别从相同候选网格锁定参数，正式集用固定边界逐题决策。F1 区间包含零，正式触发率又相差 2.1 个百分点，现有比较无法将点估计的微小差值归因于模糊隶属度。

Fuzzy 相对单阈值 NLI 的区间在零以上，支持它作为一整套策略获得更高的平均 F1。该对照同时涉及桥接输入、决策形式和实际触发率。

### RQ3 移除信号会改变触发范围

表 4&#32;&#32;固定决策边界下的消融

<table>
<thead>
<tr>
<th><p>策略</p></th>
<th><p>答案 F1</p></th>
<th><p>再检索率</p></th>
<th><p>精确率</p></th>
<th><p>召回率</p></th>
<th><p>门控 F1</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>Fuzzy</strong></p></td>
<td><p>54.42%</p></td>
<td><p>23.0%</p></td>
<td><p>0.243</p></td>
<td><p>0.455</p></td>
<td><p>0.317</p></td>
</tr>
<tr>
<td><p>Fuzzy 去掉 NLI</p></td>
<td><p>56.82%</p></td>
<td><p>66.0%</p></td>
<td><p>0.152</p></td>
<td><p>0.813</p></td>
<td><p>0.255</p></td>
</tr>
<tr>
<td><p>Fuzzy 去掉桥接</p></td>
<td><p>53.79%</p></td>
<td><p>20.7%</p></td>
<td><p>0.227</p></td>
<td><p>0.382</p></td>
<td><p>0.285</p></td>
</tr>
</tbody>
</table>

<strong>去掉 NLI&#32;</strong>固定 NLI 风险为锚点中点后，触发率由 23.0% 扩到 66.0%，命中的改善题从 56 题增至 100 题，精确率从 0.243 降到 0.152。答案 F1 上升发生在明显更大的检索预算下。

<strong>去掉桥接&#32;</strong>改用缺桥接时的回退后，触发率降到 20.7%，改善题从 56 题减到 47 题，答案 F1 降约 0.631 个百分点。这个结果说明在原决策边界下去掉桥接会改变选题与质量。输入在同等预算下的贡献仍待比较。

归档依据 \[1\] \[2\]。门控指标以 B 的答案 F1 严格高于 A 为正类。

## 预实验依据与结论的适用范围

### 预实验支持进入正式评估

100 道 DeepSeek 预实验题中，两段金标均被检索到的比例从 31% 升至 59%。追加后有 16 题改善、82 题持平、2 题变差。A/B Oracle 相对首轮增加 13.7 个百分点，配对 95% 区间为 \[+7.7, +20.3\]。GO 四项条件均通过。团队预先要求增益至少 5 个百分点、区间下界大于 0、改善至少 10%，以及变差题数至多为改善题数的一半。段落覆盖说明检索拿到了哪些证据，正式的 Supp-F1 进一步评价选中的句子。

<strong>预实验信号&#32;</strong>首轮 entailment 区分改善与持平题的 AUC 为 0.699，95% 区间 \[0.579, 0.812\]，分数方向为低 entailment 倾向对应改善。在后来补做的同预算比较里，NLI 单信号与 NLI 加桥接代理都在各自选中的 20 题中记录到 6 个改善、14 个持平、0 个变差。该结果限定于这一个桥接定义、排名方式和预算。

<strong>不确定性信号&#32;</strong>DeepSeek 在该设置中提供的 token logprob 退化。Qwen 的本地接口通过非退化检查，说明其分数有可用变化。正式比较使用锁定的 NLI 与桥接输入，模型不确定性仍属于独立的候选信号。

### 如何界定结论的范围

表 5&#32;&#32;结果与对应的适用范围

<table>
<thead>
<tr>
<th><p>维度</p></th>
<th><p>证据覆盖范围</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>数据与检索设置</p></td>
<td><p>HotpotQA bridge 的候选池，正式集每题至多十段，B 最多追加一段。更大候选池、其他题型或不同模型需要对应数据。</p></td>
</tr>
<tr>
<td><p>统计量</p></td>
<td><p>五项正式对比以题为单位配对 bootstrap，10,000 次，种子 42。区间是各项单独的 95% 区间，未做多重比较校正。</p></td>
</tr>
<tr>
<td><p>成本配置</p></td>
<td><p>32 道共用题、并发 8、Tesla T4 上的 Qwen、四 CPU 线程的 DeBERTa。时延比较描述该实现与设备配置。</p></td>
</tr>
<tr>
<td><p>复现证据</p></td>
<td><p>已用归档缓存重放正式评分和分析，核验文件与汇总结果。复现检查对应缓存回放，重新生成与重新计时属于其他验证口径。</p></td>
</tr>
</tbody>
</table>

归档依据 \[1\] \[2\] \[3\] \[4\] \[5\]。

## 人工复核与错误机制

对正式结果的探索性诊断中，A 的双金标段落覆盖为 330/1,000，B 为 568/1,000。Fuzzy 漏掉的 67 个可改善题中，追加检索本可为 53 题取得至少一个新金标段落。Fuzzy 触发后变差的 17 题中，同样有 3 题找到了新金标段落。找到新证据之后，模型仍需选对实体、答对关系并引用必要句子。

表 6&#32;&#32;三道代表题的人工复核

<table>
<thead>
<tr>
<th><p>案例</p></th>
<th><p>A / B<br />答对</p></th>
<th><p>A / B<br />引证充分</p></th>
<th><p>复核发现</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>《The Rum Diary》制作人</p></td>
<td><p>否 / 是</p></td>
<td><p>否 / 否</p></td>
<td><p>A 把导演答成电视制作人。B 按金标答对 Colin Vaines，最终引用缺少影片与题干小说的连接。</p></td>
</tr>
<tr>
<td><p>伦敦大火的教堂数</p></td>
<td><p>是 / 是</p></td>
<td><p>否 / 否</p></td>
<td><p>两支都答 87，也都引用了数字句。已检索的重建线索未进入最终引用。</p></td>
</tr>
<tr>
<td><p>The Process 缺席原因</p></td>
<td><p>是 / 是</p></td>
<td><p>否 / 否</p></td>
<td><p>两支都表达腿伤。A 漏引绰号对应人物的句子，B 还漏引赛季序数的依据。</p></td>
</tr>
</tbody>
</table>

### 答案和证据需要分别评价

教堂题的 A 分支整段前提具备两跳线索，最终引用却只保留了数字句。高 NLI 支持度对应的是模型输入的整段前提，最终引证链仍取决于句级选择。正式 Supp-F1 对比的是金标句子集合，人工复核进一步判断所选句子能否贯通推理。

腿伤题的官方 F1 从 1.000 降为 0.667。A 回答 a leg injury，B 回答 due to a leg injury，人工复核认为两种说法均答对。这个例子说明词重叠指标能够把部分措辞变化计为分数变化。

正式集有 22 道分层抽取的探索性案例，上表是其中返回人工复核的 3 道。复核表的姓名栏为空。三个案例可用于说明角色错配、漏引关键一跳和措辞敏感性。对这些机制的总体发生率，现有案例只提供定性材料。

归档依据 \[2\] \[6\]。

## Conclusion

We evaluated an NLI-driven fuzzy gate for adaptive retrieval on 1,000 held-out bridge questions from HotpotQA distractor. The gate triggered an additional retrieval on 23.0% of questions and improved answer F1 over the first-pass baseline by 3.576 percentage points (95% paired bootstrap CI \[2.265, 4.914\]). It also outscored the single-threshold NLI policy by 0.531 points (95% CI \[0.155, 0.994\]). Against a crisp rule with the same input signals, the difference was 0.064 points (95% CI \[−0.365, 0.517\]). The two policies had a shared development target and different realized trigger rates. This comparison leaves the independent contribution of fuzzy inference unresolved.

The practical trade-off depended on how cost was measured. Fuzzy triggered fewer additional retrievals than Always, which achieved higher F1 and a lower mean latency in the shared 32-question timing sample. Full-context achieved the highest answer F1 (64.27%) and used 2.31 times as many LLM tokens per question as Fuzzy in the timing sample. Removing either NLI or the bridge signal changed the realized retrieval rate, and the ablation results describe behavior at those operating points. Qualitative review also showed that semantically correct answers may omit a necessary cited step and that changes in wording can alter official answer F1. These findings characterize adaptive retrieval in a small candidate pool under the tested models and runtime.

### 归档索引

\[1\] step6\_v2/Experiment\_Report.md&#32;&#32;·&#32;&#32;V2 正式报告与研究问题解读

\[2\] step5\_v2/quality\_summary.json、step5\_v2/per\_question.csv 与 step6\_v2/paired\_bootstrap.csv&#32;&#32;·&#32;&#32;正式质量、逐题结果和配对区间

\[3\] step5\_v2/latency\_summary.json 与 step6\_v2/quality\_cost.pdf&#32;&#32;·&#32;&#32;实测成本及质量成本图

\[4\] exp/EXPERIMENT\_LOG.md 与 pilot\_signals\_v2/summary.json&#32;&#32;·&#32;&#32;预注册、原始预实验及追加信号比较

\[5\] step6\_v2/Reproducibility\_Checklist.md&#32;&#32;·&#32;&#32;归档和回放验证

\[6\] step6\_v2/Error\_Analysis.md 与项目根目录的副本V2&#32;&#32;代表案例人工复核表.xlsx&#32;&#32;·&#32;&#32;案例证据和返回的人工判断

<!-- footer1.xml -->

<blockquote><p>V2 实验结论　｜　<!-- Word field: PAGE --></p></blockquote>

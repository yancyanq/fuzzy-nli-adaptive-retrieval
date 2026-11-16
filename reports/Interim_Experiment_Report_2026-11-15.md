# 现阶段实验报告

<em>A Fuzzy-NLI-based QA Chatbot System with Adaptive Retrieval</em>

基于模糊证据核验的自适应多跳问答系统

<strong>课程项目　</strong>BNBU NLP 课程小组学期论文 · 预实验阶段

<strong>报告日期　</strong>2026 年 11 月 15 日（Asia/Shanghai，UTC+8）

<strong>数据来源　</strong>权威数据来源为实验记录 EXPERIMENT\_LOG.md。系统表述参照实验方案模板 v2（Experiment\_Protocol\_v2）与交接说明；若与记录冲突，以记录为准。

<strong>撰写原则　</strong>本文只使用实验记录中已经出现的数字与事实。尚未运行的步骤一律标为待完成。脚本在隔离环境中的模拟（mock）测试数字是假数据，不作为实验结果，也不写入正文结果表。

## 摘要

本报告汇总截至 2026 年 11 月 15 日（Asia/Shanghai，UTC+8）已经完成的预实验工作。研究问题是多跳问答中的自适应再检索：在 HotpotQA distractor 设定下，系统先完成第一轮带引用作答，再依据第一轮即可获得的信号（优先为 NLI 证据支持分数）决定是否至多追加一次检索，从而在答案质量与检索成本之间取平衡。进入主实验之前，须先核实两件更基础的事情：（1）再检索本身能带来多少可争取增益；（2）第一轮信号能否预测这一增益。

数据来自 Hugging Face 数据集 hotpotqa/hotpot\_qa，配置 distractor，划分 validation（官方开发集；测试集答案未公开）。validation 共 7,405 题，其中 type == bridge 的有 5,918 题；过滤后以随机种子 42 打乱，再顺序切分为互不重叠的 pilot 100 题、tune 500 题与 test 1,000 题。检索为 BM25：分支 A 用原问题取 top-k（锁定 k=2）；分支 B 按规则改写查询，仅在未用段落中追加 top-m（锁定 m=1）。预实验作答模型为 deepseek-chat，温度 0，max\_tokens 128。NLI 模型为 MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli，在设备 YangQS 的 NVIDIA RTX 4060 Laptop（8GB）上本地运行。

在 100 题 pilot 上，分支 A、B 与 Oracle 的 F1 分别为 0.628、0.752 与 0.765；改善、持平、变差题数分别为 16、82、2。Oracle 相对 A 的 F1 余量为 0.137，配对 bootstrap 95% 置信区间为 \[0.077, 0.203\]（B=10000，seed 42）。第 4 步预先登记的四项 go/no-go 准则全部通过，结论为 GO。第一轮 NLI entailment 区分改善题与持平题的 AUC 为 0.699，bootstrap 95% 置信区间为 \[0.579, 0.812\]（B=5000，seed 42），属中等强度、方向正确的信号。DeepSeek API 在温度 0 下给出的 token 级 logprob 不可用：选中 token 一律报 0.0，候选中大量出现占位值 -9999.0；按预注册定义计算的 margin 在 88 道两分支答案均未改变的题目上完全没有区分力（AUC = 0.500）。第 6a 步（在租用 GPU 上检查本地 vLLM 模型的 logprob 是否退化），以及随后在 tune、test 上的门控设计与正式评测，均尚未运行。

## 1&#32;&#32;研究问题与系统概述

### 1.1&#32;&#32;研究问题

课程论文英文题目为 A Fuzzy-NLI-based QA Chatbot System with Adaptive Retrieval，中文题目为「基于模糊证据核验的自适应多跳问答系统」。论文计划采用 IEEE 格式（10–12 页，10pt，双栏，单倍行距）。本文件是预实验阶段的工作报告，采用单栏排版，不是最终论文正文。

核心问题可以表述为：在完成第一轮带引用作答之后，系统能否在「至多追加一次检索」的约束下，选出最值得再检索的那些问题，从而提升答案质量，或在质量可接受时节约成本。实验方案模板 v2 进一步要求：进入主实验之前，应先核实（1）再检索本身能带来多少增益，以及（2）第一轮即可获得的信号能否预测这一增益。若（1）的可争取空间很小，应先改进第二轮检索或再作答，而不是比较门控。本阶段工作正是围绕这两项基础核实展开的。

方案记录中的状态为「通过预实验，正式方案待锁定」。模糊门控的具体规则尚未在 tune 集上设计和调参，也尚未在 test 集上做一次性正式评测。因此，下文不把任何门控性能数字作为结果（记录中亦不存在这类数字）。

### 1.2&#32;&#32;系统流程与配对双分支设计

主路径在实验方案中固定为如下结构（模型与尚未锁定的超参数除外）：

- 在 HotpotQA distractor 设定下读入问题及其自带的候选段落池；

- 第一轮检索（分支 A）：以问题为查询，用 BM25 在该题上下文段落中取 top-k 段，并据此带引用作答；

- 由第一轮信号计算门控输入（本阶段已实现并评估的是 NLI 核验；logprob 类不确定性尚待本地模型接口确认）；

- 门控决定是否采用再检索分支（至多一次）；

- 再检索分支（分支 B）：按固定规则改写查询，仅从尚未使用的候选段落中取 top-m 段，与第一轮段落合并后再次作答；

- 输出最终答案与证据。

为了把「再检索本身的可争取增益」与「门控是否选对题」分开测量，预实验采用配对双分支设计，而不是只在门控触发时才再检索：对每道评估题都保存分支 A 与分支 B 的答案。令 ΔF1 = F1\_B − F1\_A。在锁定的标签规则下（ε = 0）：F1\_B &gt; F1\_A 为改善（improved，门控正类），F1\_B = F1\_A 为持平（tie），F1\_B &lt; F1\_A 为变差（degraded）。Oracle 在事后已知两分支 F1 时选择较优者；若持平，则选择 A（不再检索）。Never 对应始终使用 A，Always 对应始终使用 B。

实验方案中还列有全上下文（full-context）对照路径，以及桥接实体一致性等其他候选信号。截至本报告撰写时，这些项目尚未在实验记录中作为已运行步骤出现，故不在此报告结果，只在第 7 节作为后续可选工作提及。

## 2&#32;&#32;实验设置

### 2.1&#32;&#32;数据

数据源在 2026 年 11 月 14 日确定：Hugging Face hotpotqa/hotpot\_qa，配置 distractor，划分 validation。选择该来源是为了便于用 datasets 加载与切分，并转换为官方 JSON 格式，以便使用 hotpot\_evaluate\_v1.py。曾考虑官方站点的 hotpot\_dev\_distractor\_v1.json，以及 BEIR、KILT、FlashRAG 等版本；后两者因不具备「每题约 10 个段落的 distractor 池」而被否决。

用户于设备 YangQS 上执行切分：Parquet 经镜像下载，并做了 SHA-256 校验（记录未给出具体哈希值）。validation 共 7,405 题，bridge 5,918 题。过滤 type == bridge 后，以随机种子 42 打乱，再顺序切分：

<strong>表 1&#32;&#32;数据划分（seed = 42，三份文件的 \_id 互不重叠）</strong>

<table>
<thead>
<tr>
<th><p>子集</p></th>
<th><p>题数</p></th>
<th><p>用途</p></th>
<th><p>YangQS 路径</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>pilot.json</p></td>
<td><p>100</p></td>
<td><p>预实验（本阶段主要评测集）</p></td>
<td><p>G:/NLP_project/pilot.json</p></td>
</tr>
<tr>
<td><p>tune.json</p></td>
<td><p>500</p></td>
<td><p>门控设计与调参（尚未运行）</p></td>
<td><p>G:/NLP_project/tune.json</p></td>
</tr>
<tr>
<td><p>test.json</p></td>
<td><p>1,000</p></td>
<td><p>正式测试（尚未运行）</p></td>
<td><p>G:/NLP_project/test.json</p></td>
</tr>
</tbody>
</table>

<strong>注：</strong>三份文件重新读回后确认：全部为 bridge，合计 1,600 个 \_id 唯一且互不重叠。格式为官方 HotpotQA JSON（UTF-8）。记录注明：部分题目的上下文段落少于 10 个，按原始数据保留；这会影响第二轮可用的未用段落池，须在检索代码中处理，并在论文中报告。记录未给出少于 10 个段落的题目精确计数。记录同时注明：上述规模沿用了当时的示例取值，正式测试规模仍受方案第 7.4 节（预算 / 效应量）约束。

### 2.2&#32;&#32;检索：BM25，k=2，m=1，规则改写

检索实现为 rank\_bm25 的 BM25Okapi，分词为小写字母数字记号，并使用一个较小的停用词表。第一轮查询等于原问题，在该题自带的上下文段落（标题 + 句子）中排序，取 top-k。第二轮规则改写：查询 = 问题 + 第一轮 top-1 段落的标题 + 该段首句；只在尚未使用的段落中排序，追加 top-m。金标为 supporting\_facts 中的标题。主要检索指标为：金标段落的平均召回（mean gold-paragraph recall）、两段金标均被取到的比例（both-gold rate）、第二轮补入至少一段金标段落的题目占比，以及没有剩余未用段落的题目占比。

2026 年 11 月 14 日 21:43，在查看 pilot 上的召回结果后，用户批准锁定 k=2、m=1。理由是：该设置下第一轮双金标覆盖最低（31%），可争取空间最大；第二轮补入金标段落的题目占比最高（30%）；在相同预算（共 3 段）下，k=2+m=1 的双金标覆盖为 59%，高于单轮 k=3 的 45%，说明规则改写的收益不只是多取一段；m=1 使再检索成本保持较小，以便日后与 Always / 全上下文等对照仍然有意义（记录指出 m=2 会更接近 k=4 或全上下文）。当时的限制也被记下：上述比较只基于检索召回，不是答案 F1；n=100，一题对应一个百分点；记录建议必要时可在 tune.json 上复核，但该项复核尚未作为已执行步骤出现。

### 2.3&#32;&#32;作答模型与解码

计算方案于 2026 年 11 月 14 日 21:50 由用户批准：预实验作答走 API（候选包括 DeepSeek-V3 的 deepseek-chat 与 GPT-4o-mini）；主实验计划租用 GPU，部署本地作答模型（记录中的示例为经 vLLM 提供的 Qwen2.5-7B-Instruct，OpenAI 兼容接口），以便可复现、获取 logprobs，并稳定延迟。脚本须同时支持 API 与 OpenAI 兼容的本地端点。

本阶段实际完成的作答实验全部使用 deepseek-chat：温度 0，max\_tokens 128，输出 JSON \{answer, citations\}，并按官方 HotpotQA 规则做 EM/F1 规范化。gpt-4o-mini 对照尚未运行。主实验的本地模型尚未在真实 vLLM 上跑过任何评测。

### 2.4&#32;&#32;NLI 模型与输入构造

NLI 使用 MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli，在 YangQS 的 RTX 4060 Laptop（8GB）上本地推理。选择该检查点的预先登记理由是：它在 MNLI、FEVER、ANLI、LingNLI 与 WANLI 上训练，相对仅在 MNLI 上训练的模型更适合较长、较复杂的前提；本设定的前提是两到三段拼接；该模型在 Hugging Face 上下载量较大，便于审稿人识别；large 检查点约 4 亿参数，可在 8GB 显存上做推理。

前提（premise）为被引用段落按引用顺序拼接（若没有可用引用，则回退到检索段落，并做标记）。假设（hypothesis）不经大模型改写，而使用固定模板：The answer to the question "\{question\}" is: \{answer\}。最大输入长度 512，须统计截断次数。标签概率依据检查点的 id2label，不假设类别顺序。

### 2.5&#32;&#32;标签、Oracle 与设备

标签规则在看到 100 题结果之前锁定：ε = 0，即以 F1\_B = F1\_A 为持平，不以带宽吸收细小差异；门控正类为 F1\_B &gt; F1\_A；Oracle 在持平时选择 A。详细理由见第 3 节。

<strong>表 2&#32;&#32;设备与本阶段用途</strong>

<table>
<thead>
<tr>
<th><p>设备</p></th>
<th><p>角色（截至本报告）</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>YangQS（Windows 笔记本，NVIDIA RTX 4060 Laptop 8GB）</p></td>
<td><p>已完成步骤的执行机：数据切分、BM25 召回、deepseek-chat 作答、本地 NLI、人工审核与 logprob 探测 / 第 5b 步重跑。项目目录为 G:/NLP_project/。显存适合 NLI，不作为主实验作答模型的计划平台。</p></td>
</tr>
<tr>
<td><p>用户的 Mac</p></td>
<td><p>计划用于 SSH / scp 连接租用 GPU 服务器（第 6a 步及之后）。本阶段尚无在该机器上完成的评测结果。</p></td>
</tr>
<tr>
<td><p>租用 GPU 服务器</p></td>
<td><p>计划运行 vLLM（默认检查模型为 Qwen/Qwen2.5-7B-Instruct，绑定 127.0.0.1:8000，不对公网开放）。第 6a 步已准备脚本，真实运行尚未开始。</p></td>
</tr>
</tbody>
</table>

API 密钥只放入环境变量（如 DEEPSEEK\_API\_KEY、VLLM\_API\_KEY），不出现在命令行参数、聊天记录或脚本打印中。

## 3&#32;&#32;预注册参数与理由

下列九项参数于 2026 年 11 月 15 日 09:40 在用户批准后锁定，且锁定发生在 100 题 pilot（第 5 步）跑出结果之前。其中第 4 项的 0.05 点估计门槛，以及第 5、6、9 项，属于主观的预注册阈值；论文须写明它们是事先设定的，并给出当时的理由。记录写明：没有任何一项是在看到 100 题结果之后才选定的。

<strong>表 3&#32;&#32;第 4 步预先登记的九项参数</strong>

<table>
<thead>
<tr>
<th><p>项</p></th>
<th><p>取值</p></th>
<th><p>理由</p></th>
<th><p>被否决的备选及其影响</p></th>
<th><p>主观预注册</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>1</p></td>
<td><p>持平容差 ε = 0</p><p>（仅当 F1_B = F1_A 时为持平）</p></td>
<td><p>官方 HotpotQA F1 是确定性指标，且作答温度为 0，同一题重跑应得到同一 F1。因此任何 F1 差异都来自额外段落带来的真实变化，而不是测量噪声，不必再设容差带。</p></td>
<td><p>备选：ε &gt; 0（例如 0.1）。细小措辞变化（答案多一个词）会被算作持平，从而缩小改善集合以及门控可学习的正类。当时 30 题 API 试跑已仅有 7 道改善题。记录预留敏感性分析：若后续检查表明多数细小 F1 变化只是措辞、语义等价，可另报 ε = 0.1，但主定义保持 ε = 0。该项敏感性分析尚未执行。</p></td>
<td><p>否</p></td>
</tr>
<tr>
<td><p>2</p></td>
<td><p>门控正类：F1_B &gt; F1_A</p></td>
<td><p>门控的任务是判断再检索是否值得；最直接的标准是答案本身是否变好。这与实验方案一致，也与外部审阅意见（按逐题官方 F1 变化打标签）一致。</p></td>
<td><p>备选（1）「第二轮取到了新的金标段落」：这是检索事件而非作答事件；第 2 步已表明取到金标段落并不意味着答案正确。备选（2）「EM 从 0 变为 1」：过严，会丢掉部分 F1 增益，并使本已较小的正类进一步缩小。</p></td>
<td><p>否</p></td>
</tr>
<tr>
<td><p>3</p></td>
<td><p>Oracle 在持平时选择 A（不再检索）</p></td>
<td><p>持平意味着额外检索没有带来质量增益，其成本被浪费。Oracle 是「若事先知道结果时的最佳选择」，此时最佳选择是不再检索。</p></td>
<td><p>备选：持平时选择 B。这会抬高 Oracle 的再检索率。在 30 题试跑中有 22 题持平，Oracle 再检索率会从 7/30 升至接近 29/30，任何门控的成本节约上界都会变得看不见。</p></td>
<td><p>否</p></td>
</tr>
<tr>
<td><p>4</p></td>
<td><p>余量 go/no-go：Oracle − A 的点估计 ≥ 0.05 F1，且配对 bootstrap 95% 置信区间下界 &gt; 0（B=10000，seed 42）</p></td>
<td><p>相对「只看点估计阈值」，增加置信区间条件，是为了直接说明余量并非抽样假象。0.05 的点估计下限是课题组自行设定的「值得继续推进的最小效应」，并非引自某篇论文。当时的推理是：100 题上平均 F1 的标准误大约在 0.03–0.04（这是预注册时的估计，不是 100 题 bootstrap 的实测标准误；记录写明精确数字将由 100 题 bootstrap 给出）。若余量小于约一个标准误，日后各门控之间的比较会被噪声主导。0.05 大约相当于该估计下的 1.5 个标准误。</p></td>
<td><p>只要求「点估计 ≥ 0.05」会忽略不确定性。只要求「置信区间下界 &gt; 0」则可能放行统计上真实但极小的增益（例如 0.01），使门控相对 Always 或 Never 的优势难以在噪声之上被看见。</p></td>
<td><p>部分是</p><p>（0.05 门槛为主观预注册；置信区间下界 &gt; 0 不是主观阈值）</p></td>
</tr>
<tr>
<td><p>5</p></td>
<td><p>改善题占比 ≥ 10%</p></td>
<td><p>门控将在 500 题 tune 上调参、在 1,000 题 test 上评估。10% 的改善率意味着测试集约 100 个正例，精确率、召回率和 F1 可望较稳定。若只有 3%，则大约 30 个正例，一题分错就会使召回大约移动 3 个百分点，结论会不稳定。当时 30 题 API 试跑的改善率为 23%，因此 10% 是留有余量的下限，不是追求的目标。</p></td>
<td><p>该门槛是样本量与稳定性方面的判断，不是文献常数。</p></td>
<td><p>是</p></td>
</tr>
<tr>
<td><p>6</p></td>
<td><p>变差题数 ≤ 改善题数的一半</p></td>
<td><p>若变差与改善同样频繁，则 Always 再检索的平均增益接近零，说明改写—再检索程序本身有缺陷，应先修正改写规则再训练门控。把变差上限定为改善的一半，是为了使再检索的净效应明显为正。该项检查的是再检索程序的质量，不是门控的质量。变差占比更高会使门控更有必要（须避开有害检索），但同时也说明检索步骤不可靠。</p></td>
<td><p>该比例是预注册判断，不是文献常数。</p></td>
<td><p>是</p></td>
</tr>
<tr>
<td><p>7</p></td>
<td><p>若 pilot 未通过 go/no-go，再检索规则只允许修改一次</p></td>
<td><p>在同一 100 题上反复改写规则并回看结果，会把规则拟合到这份 pilot（过拟合）。允许一次修改，并把修改及其理由写入记录，是标准的保护措施。若这一次修改后仍不通过：应在论文中报告，在 HotpotQA distractor 设定下，一次额外检索的增益有限。这本身就是结果，而不是继续调参的理由。</p></td>
<td><p>不允许无限制地在同一 pilot 上迭代改写规则。本阶段第 5 步已通过，该项未被触发。</p></td>
<td><p>否</p></td>
</tr>
<tr>
<td><p>8</p></td>
<td><p>NLI 模型与输入构造见第 2.4 节；截断须计数</p></td>
<td><p>选择该模型的理由见第 2.4 节。采用整段拼接而非句级取最大或最小，是遵循外部审阅意见：句级取最大会把只支持其中一跳的句子当成充分支持；句级取最小会把必须两段合在一起才支持的答案判为不受支持。DeBERTa 最大输入长度为 512。在 k=2、m=1 时前提最多三段，多数题目预期可以放入。若截断比例偏高，后续可改为只使用被引用的句子而非整段；该项改动若作为主设置，须事先记入记录。</p></td>
<td><p>不以句级最大或最小作为主设置。截断比例偏高时的句子级前提，只是预先记下的后备方案，本阶段因截断为 0/200 而未启用。</p></td>
<td><p>否</p></td>
</tr>
<tr>
<td><p>9</p></td>
<td><p>人工审核 20 条，覆盖三类错误（目标约每类 6–7 条）；审核为定性分析</p></td>
<td><p>目的是发现系统性的 NLI 失效模式，而不是精确估计错误率。20 条、大约每类 6–7 条，足以观察某类失效是否常见。若某一类很多，可以再扩大该类样本。</p></td>
<td><p>记录明确限制：由 20 条估计的错误率抽样误差很大，论文只可作为定性分析报告，不得当作精确数字。该样本量是预注册判断，不是文献常数。</p></td>
<td><p>是</p></td>
</tr>
</tbody>
</table>

<strong>注：</strong>第 5 步脚本还把配对 bootstrap 的重复次数与种子锁定为 B=10000、seed 42，与第 4 项一并作为 go/no-go 的计算口径。

## 4&#32;&#32;结果

除另行说明外，下列结果均由用户在 YangQS 上实际运行得到，并写入实验记录。隔离环境中的脚本自测只用于交付前的正确性检查，其中的模拟数字不是结果。

### 4.1&#32;&#32;第 2 步：BM25 召回（pilot，100 题）

脚本 bm25\_topk.py 先在隔离环境用同一流程重建了 pilot（bridge，seed 42，前 100 题）做核验，随后用户在 YangQS 上对 G:/NLP\_project/pilot.json 做了官方运行（m=1 与 m=2）。两组结果完全一致，从而确认隔离环境中的 pilot 与用户文件一致。输出位于 G:/NLP\_project/step2\_m1/ 与 G:/NLP\_project/step2\_m2/（各有 summary.json 与 per\_question.csv；每个目录 300 行，即 100 题 × 3 个 k 值）。在 k≤4 时，没有题目出现「没有剩余未用段落」的情况。

<strong>表 4&#32;&#32;第 2 步检索召回（pilot，n=100，m=1）</strong>

<table>
<thead>
<tr>
<th><p>k</p></th>
<th><p>第一轮</p><p>金标召回</p></th>
<th><p>第一轮</p><p>双金标覆盖</p></th>
<th><p>第二轮</p><p>金标召回</p></th>
<th><p>第二轮</p><p>双金标覆盖</p></th>
<th><p>第二轮补入金标</p><p>段落的题目占比</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>2</p></td>
<td><p>0.635</p></td>
<td><p>0.310</p></td>
<td><p>0.785</p></td>
<td><p>0.590</p></td>
<td><p>30%</p></td>
</tr>
<tr>
<td><p>3</p></td>
<td><p>0.710</p></td>
<td><p>0.450</p></td>
<td><p>0.830</p></td>
<td><p>0.670</p></td>
<td><p>24%</p></td>
</tr>
<tr>
<td><p>4</p></td>
<td><p>0.755</p></td>
<td><p>0.540</p></td>
<td><p>0.885</p></td>
<td><p>0.770</p></td>
<td><p>26%</p></td>
</tr>
</tbody>
</table>

<strong>表 5&#32;&#32;第 2 步第二轮指标（pilot，n=100，m=2）</strong>

<table>
<thead>
<tr>
<th><p>k</p></th>
<th><p>第二轮金标召回</p></th>
<th><p>第二轮双金标覆盖</p></th>
<th><p>第二轮补入金标段落的题目占比</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>2</p></td>
<td><p>0.845</p></td>
<td><p>0.700</p></td>
<td><p>42%</p></td>
</tr>
<tr>
<td><p>3</p></td>
<td><p>0.880</p></td>
<td><p>0.770</p></td>
<td><p>33%</p></td>
</tr>
<tr>
<td><p>4</p></td>
<td><p>0.920</p></td>
<td><p>0.840</p></td>
<td><p>31%</p></td>
</tr>
</tbody>
</table>

<strong>注：</strong>记录在 m=2 条目中只给出了第二轮指标（第一轮指标由 k 决定，不随 m 变化，见表 4）。锁定选择为 k=2、m=1，理由见第 2.2 节。

### 4.2&#32;&#32;第 3 步：作答模型试跑（deepseek-chat，pilot 前 30 题）

脚本 compare\_models.py 使用与第 2 步相同的检索（记录写明：在 100 道 pilot 题上核对，0 处不匹配）。设置：k=2，m=1，温度 0，max\_tokens 128，n=30。每题两个分支，评测为官方 EM/F1。用户于 2026 年 11 月 14 日 22:07 在 YangQS 上跑完。60 次调用全部成功，全部返回了 logprobs，解析失败 0 次。

<strong>表 6&#32;&#32;第 3 步答案质量（deepseek-chat，n=30，ε=0）</strong>

<table>
<thead>
<tr>
<th><p>指标</p></th>
<th><p>分支 A</p></th>
<th><p>分支 B</p></th>
<th><p>Oracle</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>EM</p></td>
<td><p>0.433</p></td>
<td><p>0.600</p></td>
<td><p>—</p></td>
</tr>
<tr>
<td><p>F1</p></td>
<td><p>0.565</p></td>
<td><p>0.733</p></td>
<td><p>0.767</p></td>
</tr>
</tbody>
</table>

<strong>注：</strong>记录未给出 30 题 Oracle 的 EM。平均 ΔF1（B−A）= +0.169。Oracle − B = 0.034，Oracle − A = 0.202。

<strong>表 7&#32;&#32;第 3 步逐题类别与调用开销（n=30）</strong>

<table>
<thead>
<tr>
<th><p>项目</p></th>
<th><p>数值</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>改善 / 持平 / 变差</p></td>
<td><p>7 / 22 / 1</p></td>
</tr>
<tr>
<td><p>调用次数</p></td>
<td><p>60，全部成功</p></td>
</tr>
<tr>
<td><p>解析失败</p></td>
<td><p>0</p></td>
</tr>
<tr>
<td><p>总 token（输入 / 输出）</p></td>
<td><p>26,713（25,639 / 1,074）</p></td>
</tr>
<tr>
<td><p>平均延迟</p></td>
<td><p>0.697 秒/次调用</p></td>
</tr>
<tr>
<td><p>费用</p></td>
<td><p>未估计（未传入单价）</p></td>
</tr>
</tbody>
</table>

<strong>注：</strong>解读（记录原文口径）：分支 A 的 F1 落在预先希望的约 0.4–0.7 区间内；再检索有帮助；余量存在，可供门控争取。但 Always（B）已经接近 Oracle，因此门控的主要任务是在 22 道持平题上节约成本，同时留住 7 道改善题。gpt-4o-mini 对照尚未运行。输出位于 G:/NLP\_project/step3\_deepseek/\{summary.json, per\_question.csv\}。

### 4.3&#32;&#32;第 5 步：100 题 pilot（deepseek-chat + 本地 NLI）——结论 GO

用户于 2026 年 11 月 15 日 10:33 在 YangQS 上完成 100 题试点：设置与锁定参数一致（pilot.json，n=100，k=2，m=1，deepseek-chat，温度 0，max\_tokens 128，ε=0，Oracle 持平选 A）。第 3 步缓存被复用；NLI-only 通道未产生新的 API 调用（按用户当时的报告）。NLI 在 RTX 4060 上本地运行。

<strong>表 8&#32;&#32;第 5 步答案质量（n=100，ε=0）</strong>

<table>
<thead>
<tr>
<th><p>指标</p></th>
<th><p>分支 A</p></th>
<th><p>分支 B</p></th>
<th><p>Oracle</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>EM</p></td>
<td><p>0.520</p></td>
<td><p>0.650</p></td>
<td><p>—</p></td>
</tr>
<tr>
<td><p>F1</p></td>
<td><p>0.628</p></td>
<td><p>0.752</p></td>
<td><p>0.765</p></td>
</tr>
</tbody>
</table>

<strong>注：</strong>记录未给出 100 题 Oracle 的 EM。平均 ΔF1（B−A）= +0.124。Oracle − A = 0.137，Oracle − B = 0.013。

<strong>表 9&#32;&#32;第 5 步逐题类别（n=100，ε=0）</strong>

<table>
<thead>
<tr>
<th><p>类别</p></th>
<th><p>题数</p></th>
<th><p>占比或比值</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>改善（F1_B &gt; F1_A）</p></td>
<td><p>16</p></td>
<td><p>16%</p></td>
</tr>
<tr>
<td><p>持平（F1_B = F1_A）</p></td>
<td><p>82</p></td>
<td><p>82%</p></td>
</tr>
<tr>
<td><p>变差（F1_B &lt; F1_A）</p></td>
<td><p>2</p></td>
<td><p>2%</p></td>
</tr>
<tr>
<td><p>变差题数 / 改善题数</p></td>
<td><p>2 / 16</p></td>
<td><p>0.125</p></td>
</tr>
</tbody>
</table>

<strong>表 10&#32;&#32;第 5 步余量与配对 bootstrap（seed 42）</strong>

<table>
<thead>
<tr>
<th><p>项目</p></th>
<th><p>数值</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>mean(Oracle F1 − A F1)</p></td>
<td><p>0.137</p></td>
</tr>
<tr>
<td><p>配对 bootstrap 95% 置信区间</p></td>
<td><p>[0.077, 0.203]</p></td>
</tr>
<tr>
<td><p>bootstrap 重复次数 B</p></td>
<td><p>10000</p></td>
</tr>
<tr>
<td><p>随机种子</p></td>
<td><p>42</p></td>
</tr>
</tbody>
</table>

<strong>表 11&#32;&#32;第 5 步 NLI 统计（200 条输入）</strong>

<table>
<thead>
<tr>
<th><p>项目</p></th>
<th><p>数值</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>模型</p></td>
<td><p>MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli</p></td>
</tr>
<tr>
<td><p>计分输入</p></td>
<td><p>200（A 100，B 100）</p></td>
</tr>
<tr>
<td><p>截断</p></td>
<td><p>0/200（0%）</p></td>
</tr>
<tr>
<td><p>回退到检索段落（无可用引用）</p></td>
<td><p>0</p></td>
</tr>
<tr>
<td><p>平均 entailment 概率（A / B）</p></td>
<td><p>0.876 / 0.923</p></td>
</tr>
</tbody>
</table>

<strong>表 12&#32;&#32;第 5 步 go/no-go 对照预先登记准则</strong>

<table>
<thead>
<tr>
<th><p>准则</p></th>
<th><p>预先登记标准</p></th>
<th><p>实测</p></th>
<th><p>判定</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>余量点估计</p></td>
<td><p>≥ 0.05</p></td>
<td><p>0.137</p></td>
<td><p>PASS</p></td>
</tr>
<tr>
<td><p>余量 95% 置信区间下界</p></td>
<td><p>&gt; 0</p></td>
<td><p>0.077</p></td>
<td><p>PASS</p></td>
</tr>
<tr>
<td><p>改善题占比</p></td>
<td><p>≥ 10%</p></td>
<td><p>16%</p></td>
<td><p>PASS</p></td>
</tr>
<tr>
<td><p>变差题数 / 改善题数</p></td>
<td><p>≤ 0.5</p></td>
<td><p>0.125</p></td>
<td><p>PASS</p></td>
</tr>
<tr>
<td><p>总体</p></td>
<td><p>上述各项均须通过</p></td>
<td><p>全部通过</p></td>
<td><p>GO</p></td>
</tr>
</tbody>
</table>

<strong>注：</strong>第 7 项（规则只许修改一次）未被触发。记录中的解读：Oracle − B 只有 0.013，Always（B）已经接近 Oracle；在 82% 的持平题上，门控的价值主要在于削减再检索成本，同时留住 16 道改善题。论文主主张应是「以明显更低的再检索率达到接近 B 的 F1」，而不是「F1 超过 B」。这一解读与第 3 步 30 题结果相一致。记录同时提醒：第一轮平均 entailment 已经较高（0.876），NLI 能否区分改善与持平当时尚未检验；该项检验见第 4.5 节，且只作描述，不在 pilot 上调门控。输出位于 G:/NLP\_project/step5\_pilot/。

### 4.4&#32;&#32;人工审核（20 条，定性分析）

抽查样本由第 5 步脚本按预先登记的三类自动错误类型分层抽取（目标约每类 6–7 条，seed 42），人工列 human\_label 留空。用户填写后，于 2026 年 11 月 15 日 10:48 收回。20 行均为（题目，分支）配对，覆盖 15 道不同的题（其中 5 道题同时出现 A、B 两个分支）。所有 20 行的 human\_answer\_correct、human\_premise\_supports、human\_label 与 note 均已填写。

审核编码预先约定如下。须强调：NLI 判断的是前提是否支持答案，不是答案相对金标是否正确；因此，「答案错误但被前提所支持」应标为 nli\_correct。

- nli\_correct：NLI 实际上是对的，自动规则发出了误报；

- nli\_wrong\_multihop：两段合在一起支持答案，但 NLI 未能完成这一推断；

- nli\_wrong\_lexical：词面重叠使 NLI 误判为蕴含；

- nli\_wrong\_hypothesis：假设模板的措辞导致错误，例如在是非题上；

- nli\_wrong\_other：其他，须在 note 中说明。

<strong>表 13&#32;&#32;人工审核标签计数（n=20 条，不是 20 道互异题）</strong>

<table>
<thead>
<tr>
<th><p>字段</p></th>
<th><p>取值</p></th>
<th><p>计数</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>human_answer_correct</p></td>
<td><p>yes</p></td>
<td><p>7</p></td>
</tr>
<tr>
<td><p>human_answer_correct</p></td>
<td><p>no</p></td>
<td><p>13</p></td>
</tr>
<tr>
<td><p>human_premise_supports</p></td>
<td><p>yes</p></td>
<td><p>2</p></td>
</tr>
<tr>
<td><p>human_premise_supports</p></td>
<td><p>no</p></td>
<td><p>18</p></td>
</tr>
<tr>
<td><p>human_label</p></td>
<td><p>nli_correct</p></td>
<td><p>11</p></td>
</tr>
<tr>
<td><p>human_label</p></td>
<td><p>nli_wrong_lexical</p></td>
<td><p>6</p></td>
</tr>
<tr>
<td><p>human_label</p></td>
<td><p>nli_wrong_multihop</p></td>
<td><p>2</p></td>
</tr>
<tr>
<td><p>human_label</p></td>
<td><p>nli_wrong_other</p></td>
<td><p>1</p></td>
</tr>
<tr>
<td><p>human_label</p></td>
<td><p>nli_wrong_hypothesis</p></td>
<td><p>0</p></td>
</tr>
</tbody>
</table>

<strong>表 14&#32;&#32;自动错误类型与人工标签的交叉表（n=20）</strong>

<table>
<thead>
<tr>
<th><p>自动错误类型</p></th>
<th><p>条数</p></th>
<th><p>人工标签分布</p></th>
<th><p>记录中的说明</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>false_entailment</p></td>
<td><p>7</p></td>
<td><p>6 条 nli_wrong_lexical；1 条 nli_wrong_other</p></td>
<td><p>自动「错误蕴含」桶大体对应真正的 NLI 错误，以词面重叠为主。那一条 nli_wrong_other 是 NLI 把弃答 “Unknown” 判成了蕴含。</p></td>
</tr>
<tr>
<td><p>false_non_entailment</p></td>
<td><p>7</p></td>
<td><p>5 条 nli_correct；2 条 nli_wrong_multihop</p></td>
<td><p>两条例外属于同一道题的 A、B 两个分支，内容与海绵宝宝剧集日期有关。</p></td>
</tr>
<tr>
<td><p>truncated_or_</p><p>disagreement</p></td>
<td><p>6</p></td>
<td><p>全部为 nli_correct</p></td>
<td><p>与 0% 截断相一致：当前提并不支持答案时，NLI 正确地没有给出蕴含。</p></td>
</tr>
</tbody>
</table>

<strong>注：</strong>定性解读（记录强调：n=20，不得当作错误率点估计）：自动「错误蕴含」桶大体追踪真实的 NLI 错误，主要是词面重叠；自动「错误非蕴含」和「不一致」桶多数是误报——模型答案可以与金标相同，但被引用的前提仍不支持该答案（模型可能使用了参数知识）；真正的多跳推断失败在本样本中出现两次，且同属一道题；本样本中没有假设模板错误。记录还记下一项尚未付诸实施的可能细化：部分 nli\_correct 行的 argmax 为 contradiction，而人工注记描述的是「证据缺失」（neutral 可能更合适）；这并不改变编码表的判定，因为任何非蕴含都被视为与「前提不支持」一致。

### 4.5&#32;&#32;信号诊断（描述性分析，不调门控）

脚本 analyze\_signals.py 只离线读取第 5 步的 per\_question.csv，不发起 API 或 NLI 调用，也不选择阈值。主要对比是改善题与持平题（16 对 82）。AUC 使用定向分数（−signal），因此 AUC &gt; 0.5 表示第一轮取值更低更倾向于标记改善题——这正是再检索门控所期望的方向。AUC 与 mean(改善)−mean(持平) 均给出 bootstrap 95% 置信区间（默认 B=5000，seed 42）。脚本还打印了若干说明性规则「若 nli\_entailment\_A &lt; t 则再检索」，预置 t ∈ \{0.50, 0.80, 0.90, 0.95\}；这些规则只作描述，不得当作门控；调参仍须在 tune.json 上进行。记录写明这些说明性阈值已写入 signal\_summary.json，但均未被选用。本报告不引用该文件中记录正文未列出的数字。

用户于 2026 年 11 月 15 日 11:04 在 YangQS 上执行。

<strong>表 15&#32;&#32;分支 A 上各类别的信号均值与定向 AUC（改善 vs 持平）</strong>

<table>
<thead>
<tr>
<th><p>信号</p></th>
<th><p>改善均值（n=16）</p></th>
<th><p>持平均值（n=82）</p></th>
<th><p>变差均值（n=2）</p></th>
<th><p>AUC（改善 vs 持平）</p></th>
<th><p>95% 置信区间</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>NLI entailment</p></td>
<td><p>0.798</p></td>
<td><p>0.888</p></td>
<td><p>0.989</p></td>
<td><p>0.699</p></td>
<td><p>[0.579, 0.812]</p></td>
</tr>
<tr>
<td><p>mean_logprob_A</p></td>
<td><p>0.000</p></td>
<td><p>0.000</p></td>
<td><p>0.000</p></td>
<td><p>0.500</p></td>
<td><p>[0.500, 0.500]</p></td>
</tr>
<tr>
<td><p>min_logprob_A</p></td>
<td><p>0.000</p></td>
<td><p>0.000</p></td>
<td><p>0.000</p></td>
<td><p>0.500</p></td>
<td><p>[0.500, 0.500]</p></td>
</tr>
</tbody>
</table>

<strong>注：</strong>变差类 n=2，记录写明「不可解释」，表中列出仅为完整转录，不对其均值做解读。NLI 的置信区间下界高于 0.5，说明它带有中等强度、方向正确的信号，但单独使用还不够强；这支持在模糊门控中组合信号，而不是只用单一 NLI 阈值。两类 logprob 的各类均值均为 0.000，AUC 为 0.500。用户检查作答缓存后确认：全部 100 道第一轮回答中，每一个被记录的 token logprob 都是 0.0。代码检查表明，compare\_models.py 只是把接口返回的 choice.logprobs.content\[i\].logprob 转为 float，不会填默认 0。因此这些 0 是 deepseek-chat 在温度 0 下返回的值，不是 span 匹配程序的缺陷。厂商侧的根本原因尚未确认。记录给出的结论是：本批 API logprob 信号无效（退化），不能据此断言「logprob 没有判别力」。输出位于 G:/NLP\_project/step5\_pilot/\{signal\_summary.json, signal\_by\_class.csv\}。

### 4.6&#32;&#32;logprob 调查：探测、做法选择、第 5b 步重跑与占位值问题

#### 4.6.1&#32;&#32;第 5 步中的全零 logprob

如上节所述，第 5 步缓存里第一轮全部 token logprob 均为 0.0，相应 AUC 为 0.500。这促使在正式改用其他不确定性度量之前，先做一次小规模接口探测。

#### 4.6.2&#32;&#32;探测（4 次调用）

脚本 probe\_logprobs.py 使用 2 个短提示（一个低不确定性的事实性提示，一个开放式提示）与温度 \{0, 1\} 交叉，共 4 次调用；max\_tokens 8，logprobs=True，top\_logprobs=5。用户于 2026 年 11 月 15 日 11:48 在 YangQS 上执行，模型仍为 deepseek-chat。

<strong>表 16&#32;&#32;logprob 探测中与选中 token 有关的结果</strong>

<table>
<thead>
<tr>
<th><p>温度</p></th>
<th><p>提示（记录中的简称）</p></th>
<th><p>输出 token 数</p></th>
<th><p>选中 token 的 logprob</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>0</p></td>
<td><p>Paris</p></td>
<td><p>1</p></td>
<td><p>全部为 0</p></td>
</tr>
<tr>
<td><p>0</p></td>
<td><p>Kiwi</p></td>
<td><p>2</p></td>
<td><p>全部为 0</p></td>
</tr>
<tr>
<td><p>1</p></td>
<td><p>Paris</p></td>
<td><p>1</p></td>
<td><p>最小值与均值均为 −0.000001073（非零）</p></td>
</tr>
<tr>
<td><p>1</p></td>
<td><p>Kiwi</p></td>
<td><p>2</p></td>
<td><p>最小值 −0.4549，均值 −0.2275；2 个 token 中有 1 个为 0</p></td>
</tr>
</tbody>
</table>

<strong>注：</strong>记录当时还写有「top-5 候选非零」计数：温度 0 下为 4/5 与 8/10，温度 1 下为 5/5 与 9/10，并据此认为「温度 0 下候选（top\_logprobs）仍然有信息」。这一计数在第 5b 步之后被更正：探测把 -9999.0 也算成了非零，应当检查占位值。该疏漏已记入 12:08 条目。因此，上表只转录与选中 token 有关、且随后未被更正的数字；「候选非零」计数不得作为「候选可用」的证据，也不应在论文中引用。关于选中 token 的结论仍然成立：第 5 步中的全零输出 token logprob，与 deepseek-chat 在温度 0 下为选中 token 计分的方式有关，而不是抽取代码的错误。原始文件：G:/NLP\_project/probe\_logprobs.json。

#### 4.6.3&#32;&#32;三种做法与用户选择

探测之后，记录中写下三种做法，并建议采用做法 3；用户于 11:51 选择做法 1。三种做法的要点如下。

<strong>表 17&#32;&#32;针对 API 全零 logprob 的三种做法（决定于看到第 5b 步结果之前）</strong>

<table>
<thead>
<tr>
<th><p>做法</p></th>
<th><p>内容</p></th>
<th><p>要点</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>1（用户选择）</p></td>
<td><p>保持温度 0，重跑全部 200 次调用并加 top_logprobs；用 top-1 与 top-2 候选的 margin 作为不确定性度量。</p></td>
<td><p>优点是不改已经锁定的温度 0，从而尽量保持与第 5 步同一解码设定。缺点是这是针对该 API 行为的变通，必须在论文中披露；且该 margin 并不等于主实验本地模型上计划使用的选中 token logprob，分布也不能直接迁移。</p></td>
</tr>
<tr>
<td><p>2</p></td>
<td><p>改用温度 1，以获取非零的选中 token logprob。</p></td>
<td><p>可以得到真实的选中 token logprob，但会打破已经锁定的温度 0 与可复现设定，记录中明确不建议。</p></td>
</tr>
<tr>
<td><p>3（当时建议，未被采纳）</p></td>
<td><p>pilot 只评估 NLI；logprob 类信号留到主实验的本地 vLLM 模型上，并在首次运行时先验证其非退化。</p></td>
<td><p>避免把一种 API 变通当作预实验结论，也避免改温度。代价是预实验阶段不再拥有可用的 token 置信度信号。</p></td>
</tr>
</tbody>
</table>

做法 1 在看到重跑结果之前即完成预注册，要点包括：重跑 200 次调用（100 题 × 分支 A/B），模型与提示、检索（k=2，m=1）、温度 0、max\_tokens 128 保持不变，仅增加 logprobs=True 与 top\_logprobs=5；新调用写入单独缓存，不覆盖第 5 步缓存与结果；对每个输出 token，margin = logprob(top-1 候选) − logprob(top-2 候选)；主信号为分支 A 答案跨度上各 token margin 的均值（若找不到答案跨度，则回退到全部输出 token，并计数）；次要描述指标为：答案跨度上的最小 margin、首个答案 token 的 margin、在返回候选上重新归一化后的平均 top-5 熵；较低 margin / 较高熵表示更不确定，预期用于标记改善题；用官方规范化后的字符串相等比较重跑答案与第 5 步缓存答案，并报告各分支答案改变的题数；改善 / 持平 / 变差标签仍使用第 5 步 per\_question.csv，不因重跑而改判 GO；主分析 AUC 只在 A、B 答案均未改变的题目上计算，全部题目的 AUC 作为敏感性分析；同一批题目上同时报告 NLI AUC，以便在完全相同的数据上比较两种信号。

#### 4.6.4&#32;&#32;第 5b 步结果

用户在 YangQS 上运行 rerun\_toplogprobs.py，200 次调用全部成功。输出为 G:/NLP\_project/step5b\_toplp/toplp\_summary.json。

<strong>表 18&#32;&#32;第 5b 步主信号 mean\_margin\_A 与同一批题目上的 NLI AUC</strong>

<table>
<thead>
<tr>
<th><p>分析</p></th>
<th><p>题数</p></th>
<th><p>主指标 mean_margin_A 的 AUC（95% CI）</p></th>
<th><p>同批题 NLI AUC（95% CI）</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>主分析：A、B 答案均未改变</p></td>
<td><p>88</p></td>
<td><p>0.500 [0.500, 0.500]</p></td>
<td><p>0.724 [0.593, 0.844]</p></td>
</tr>
<tr>
<td><p>敏感性分析：全部题目</p></td>
<td><p>100</p></td>
<td><p>0.482 [0.457, 0.500]</p></td>
<td><p>0.699 [0.579, 0.812]</p></td>
</tr>
</tbody>
</table>

<strong>表 19&#32;&#32;第 5b 步一致性与 logprob 退化观察</strong>

<table>
<thead>
<tr>
<th><p>项目</p></th>
<th><p>数值</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>按 HotpotQA 规范化后，分支 A 答案改变的题数</p></td>
<td><p>9</p></td>
</tr>
<tr>
<td><p>分支 B 答案改变的题数</p></td>
<td><p>4</p></td>
</tr>
<tr>
<td><p>涉及的不同题目数</p></td>
<td><p>12</p></td>
</tr>
<tr>
<td><p>输出 token 总数（A / B）</p></td>
<td><p>3,482（1,703 / 1,779）</p></td>
</tr>
<tr>
<td><p>其中 top-1 候选 logprob 报为 0.0 的 token 数</p></td>
<td><p>全部 3,482</p></td>
</tr>
<tr>
<td><p>top-2 候选报为 -9999.0 的 token 数</p></td>
<td><p>3,477</p></td>
</tr>
<tr>
<td><p>主分析 88 题的 mean_margin_A</p></td>
<td><p>全部为 9999.0</p></td>
</tr>
</tbody>
</table>

记录中的解释如下。

- −9999.0 是表示「概率小到可以忽略 / 不予报告」的占位值，不是真实的对数概率。因此，在温度 0 下，deepseek-chat 对选中 token 报 0，对几乎全部其他候选报占位值。预注册的 margin 信号是退化的；AUC = 0.500 的含义是「没有信息」，而不是「信号很弱」。

- 对 11:48 探测条目的更正：「候选非零」把 -9999.0 算成了非零。探测本应检查占位值。这是探测检查上的疏漏，已写入记录，以免报告把该计数当作「候选可用」的证据。

- 没有做事后补救：由同一批候选计算的次要指标（最小 margin、首 token margin、熵）依赖同样的占位值，故不用它们替代主指标。改成温度 1 重跑，或把 -9999 当作普通数字参与计算，都属于预注册之外的新分析，因而没有做。

- NLI 信号在不同子集上稳定（全部 100 题为 0.699，88 道答案未变的题为 0.724），第 5 步「NLI 是中等强度信号」的结论仍然成立。

对论文的结论是：在本预实验中，DeepSeek API 在温度 0 下不能提供可用的 token 级置信度信号（无论是选中 token 的 logprob，还是 top-k margin）。门控所用的 logprob 类信号，只在主实验的本地模型（vLLM）上评估；并须先在 tune 集前 30 题上检查其对数概率是否非退化——既没有「选中 token 全为 0」，也没有占位候选。

### 4.7&#32;&#32;第 6a 步：已准备、尚未运行

第 6a 步脚本 check\_logprobs.py 已于 2026 年 11 月 15 日 12:13 准备完毕，目的是：在 tune 划分的前 30 题上，检查经 vLLM 提供的本地模型是否返回非退化的 token logprob，从而决定 logprob 类信号能否进入主实验的模糊门控。该步只跑分支 A，温度 0，max\_tokens 128，logprobs=True，top\_logprobs=5，计划 30 次调用。默认模型为 Qwen/Qwen2.5-7B-Instruct，接口为 http&#58;//localhost:8000/v1。这一步只检验是否退化，不计算 AUC，也不选择门控阈值。截至本报告撰写时，尚未进行任何真实的 vLLM 运行；隔离环境中的模拟测试数字是假数据，不在此列出。

下列四条通过标准在真实本地模型运行之前已经锁定。默认阈值可用命令行覆盖，但主判定以预注册默认值为准。仅当四条全部成立时判定为 PASS，否则为 FAIL，并列出未通过的条目。第 1–4 条使用主观阈值，论文须写明它们是事先设定的，并给出下面这些理由。另有一条程序性规则（不是主观阈值）：所有预定题目都必须具有可用的 logprobs；若任何一次调用失败或没有返回 token，判定为 FAIL，失败项记为 incomplete，因为无法在不完整的运行上证明非退化。

<strong>表 20&#32;&#32;第 6a 步预先登记的四条通过标准（真实运行尚未开始）</strong>

<table>
<thead>
<tr>
<th><p>条</p></th>
<th><p>标准</p></th>
<th><p>理由与被否决的备选</p></th>
<th><p>主观预注册</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>1</p></td>
<td><p>答案跨度内，选中 token 的 logprob 恰好为 0.0 的比例不超过 50%（「至多」，即 ≤ 50%）</p></td>
<td><p>在贪心解码（温度 0）下，非常有把握的 token 其 logprob 有可能四舍五入为 0（例如 -1e-6），因此允许少数恰好为 0 的情况。若大多数 token 恰好为 0.0，则接口很可能在做截断，正如 deepseek-chat 在第 5b 步中把每个选中 token 都报成 0.0。备选「不允许任何一个恰好为 0」过严，可能使只是把少数高置信 token 圆整的正常服务失败；备选「只要存在方差就忽略为零的比例」过宽，会漏掉完全截断。在 50% 这一取值下，DeepSeek 式的 100% 为零会 FAIL，偶发圆整仍可 PASS。</p></td>
<td><p>是</p></td>
</tr>
<tr>
<td><p>2</p></td>
<td><p>占位候选（logprob ≤ -9000）占全部被报告候选的比例低于 5%（「低于」为严格小于）</p></td>
<td><p>第 5b 步发现 -9999.0 被用作「概率可忽略 / 不报告」的哨兵，而不是真实对数概率（3,477 个 token 的 top-2 候选为 -9999.0）。截止值 -9000 旨在抓住该哨兵，同时又远低于通常的 top-5 logprob。允许很小比例，是为了容忍可能的编码毛刺；比例过高则意味着这些候选不能用于 margin 信号。备选「不允许任何占位值」稍严；备选「只检查选中 token 的 logprob」会漏掉第 5b 步 margin 信号的那种失效方式。DeepSeek 类端点（几乎全部候选为 -9999）会 FAIL；返回普通 top-5 logprob 的 vLLM 端点应 PASS。</p></td>
<td><p>是</p><p>（-9000 与 5%</p><p>均为主观预注册）</p></td>
</tr>
<tr>
<td><p>3</p></td>
<td><p>每题平均选中 token logprob（答案跨度；若找不到跨度则回退到全部输出 token，规则与第 5b 步相同）在 30 题上至少有 10 个不同取值，且方差不为 0。不同取值在保留 6 位小数后计数（与第 5b 步 token 缓存精度相同）；方差为总体方差。</p></td>
<td><p>即便逐 token 的零值很少，各题均值仍可能坍缩成一个常数。若模型给出的是真实 token 概率，30 题应表现出分散。10 是 30 的三分之一：足以说明取值没有坍缩到少数几个箱子，又不要求 30 个均值全部互异（圆整或短答案造成的并列是合理的）。备选「只要方差不为 0」过弱（两个不同值即可通过）；备选「30 个全部唯一」过严。若每题均值都相同（例如全是 0.0），则 FAIL。</p></td>
<td><p>是（其中的 10 为主观预注册）</p></td>
</tr>
<tr>
<td><p>4</p></td>
<td><p>对每题平均 margin（top-1 候选 logprob 减 top-2 候选 logprob，跨度规则相同）施加与第 3 条相同的要求。</p></td>
<td><p>在第 5b 步中，因为候选是占位值，88 道主分析题的 mean_margin_A 全部为 9999.0。把平均 margin 的分散程度与选中 token logprob 分开检查，才能抓住「选中 logprob 可用但候选为占位值」（或相反）的服务。只检查选中 token logprob 会漏掉这种失效。若 margin 坍缩（全部为 9999.0，或任意一个常数），则第 4 条 FAIL，即使第 3 条已经通过。</p></td>
<td><p>是（其中的 10 为主观预注册）</p></td>
</tr>
</tbody>
</table>

<strong>注：</strong>第 6a 步尚未运行，上表不是结果。计划命令为：在 GPU 服务器上启动 vLLM 后，执行 python check\_logprobs.py --data tune.json --out step6a\_check。官方 tune.json 位于 G:/NLP\_project/tune.json。

## 5&#32;&#32;讨论

第一，再检索带来的可争取增益主要来自少数改善题，而门控的现实价值更可能是在大量持平题上节约成本。100 题上 Oracle F1 为 0.765，Always（B）为 0.752，二者只差 0.013；与此同时，Oracle 相对 Never（A）的余量为 0.137，且 95% 置信区间下界 0.077 大于 0。改善题只有 16 道，持平题多达 82 道，变差题 2 道。这意味着：即便一个完美门控，能在 F1 上超过 Always 的空间也很小；它真正能显示出来的贡献，是把再检索率从 100% 降下来，同时尽量保留那 16 道改善题，并避开 2 道变差题。因此，后续论文主张应写成「以明显更低的再检索率达到接近 B 的 F1」，而不是「F1 超过 B」。30 题试跑中 Oracle − B = 0.034、持平 22 题，方向与此一致。

第二，第一轮 NLI entailment 是目前唯一已经显示出中等判别力的可用信号。改善题的平均 entailment 为 0.798，持平题为 0.888，定向 AUC 为 0.699，95% 置信区间为 \[0.579, 0.812\]，下界高于 0.5。在第 5b 步答案未变的 88 题子集上，NLI AUC 为 0.724（95% CI \[0.593, 0.844\]），与全样本 0.699 相近，说明该信号对这 12 道答案发生变化的题并不敏感依赖。与此同时，第一轮平均 entailment 已经高达 0.876，改善与持平的均值差距有限，记录因此认为它「单独使用还不够强」，更适合作为模糊门控中的组合信号之一，而不是单一硬阈值。人工审核是定性的，不能给出错误率，但提示了两类需要在论文中诚实讨论的现象：词面重叠造成的错误蕴含，以及「答案碰巧正确、引用前提并不支持」时自动规则对非蕴含的误报。真正的多跳推断失败在 20 条样本中只出现在同一道题的两个分支上，不宜外推。

第三，DeepSeek API 在温度 0 下不能提供可用的 token 级置信度。第 5 步中选中 token logprob 全为 0.0；第 5b 步进一步表明，3,482 个输出 token 的第一候选均为 0.0，其中 3,477 个 token 的第二候选为占位值 -9999.0，主分析 88 题的 mean\_margin\_A 全部为 9999.0，AUC 恰好为 0.500。这不是「信号很弱」，而是度量在这批调用里没有变异。探测阶段曾把占位值计为非零候选，这一检查疏漏已经更正，不能再引用那组计数。因此，预实验阶段不应把 API logprob 或基于占位候选的 margin 写入门控；该信号族是否可用，完全取决于第 6a 步在本地 vLLM 模型上的检查结果。

第四，检索侧的结果为上述作答增益提供了机制上的呼应：在 k=2 时，第一轮双金标覆盖只有 31%，追加一轮 m=1 后升至 59%，且优于同等预算的单轮 k=3（45%）。再检索不是简单多取一段，规则改写有独立贡献。不过第 2 步只测量召回；答案是否因此变好，要以第 3、5 步的 F1 为准。二者方向一致，但幅度不能直接换算。

## 6&#32;&#32;局限

- 样本量。第 5 步主结论来自 n=100 的 pilot；第 3 步仅为前 30 题。改善题只有 16 道，变差题只有 2 道，类别均值（尤其是变差类）不稳定。go/no-go 已经用配对 bootstrap 处理余量的抽样误差，但许多描述性比例（如 16%）本身仍带有较大的二项方差。

- 人工审核规模。审核为 20 条（15 道不同的题），是预先登记的定性分析，不能给出精确错误率，也不能代表全部自动错误类型或全部题型。

- 作答模型与接口。本阶段答案质量与 NLI 诊断都建立在 deepseek-chat 上；主实验计划换用本地模型，F1、改善率与信号分布都不能默认迁移，必须在本地模型上重测。

- API logprob 变通失败。做法 1 的 margin 是针对该 API 在温度 0 下把选中 token 报为 0 的变通，本就不能迁移到主实验模型；第 5b 步进一步表明，候选侧还存在占位值，使该变通在这批数据上没有区分力。

- 探测检查上的疏漏。11:48 的探测把 -9999.0 计为非零，一度误以为温度 0 下的候选「仍有信息」。该疏漏已在 12:08 更正。这提醒我们：对第三方接口返回的极端数值应先检查是否为哨兵，再做统计。

- 主观阈值。改善率 10%、变差不超过改善的一半、余量点估计 0.05，以及第 6a 步的 50%、5%、-9000 与「至少 10 个不同值」，都是事先登记的判断，不是文献常数。它们影响 go/no-go 或后续是否采纳 logprob 信号，须在论文中原样披露。本阶段没有在看到结果之后改这些阈值。

- 尚未纳入的对照与信号。全上下文路径、桥接实体一致性、gpt-4o-mini 对照，以及 tune / test 上的门控评测，均未运行。第 5 步记录也未给出引用覆盖率、句子级 supporting-fact F1、100 题的 token 或延迟，本报告因此不以估计值补全。

- 部分题目上下文段落少于 10 个。数据按原样保留，记录未给出精确题数；这会限制个别题的第二轮未用段落池，须在论文中说明。

- 正式测试规模仍受方案第 7.4 节（预算 / 效应量）约束。当前 test.json 为 1,000 题，但是否作为最终主实验规模，记录仍保留该限制。

## 7&#32;&#32;下一步计划

以下步骤均须先预注册分析口径与通过标准，再查看结果；不得根据结果改换主指标或事后挑选阈值。

- 第 6a 步真实运行（待完成）。在租用 GPU 上启动 vLLM（计划示例：vllm serve Qwen/Qwen2.5-7B-Instruct --host 127.0.0.1 --port 8000 --max-logprobs 5），用 tune.json 的前 30 题跑 check\_logprobs.py，依据表 20 的四条标准判定 PASS 或 FAIL。PASS 则 logprob 信号可以进入后续门控设计；FAIL 则门控只用 NLI 等非 logprob 信号，并在论文中说明本地接口的检查结果。

- 在 tune（500 题）上生成本地模型的 A/B 两个分支与 NLI 分数，并设计、调参模糊门控（输入可包括 NLI entailment，以及第 6a 步通过后才加入的 logprob 置信度等；输出为是否再检索）。须比较的基线至少包括：Never（只用 A）、Always（总用 B）、Oracle（持平选 A），以及单阈值 NLI 门控。实验方案中还计划在输入完全相同、再检索率目标对齐的条件下比较模糊推理与硬规则，并视需要纳入全上下文对照；这些对照应在调参方案预先登记时一并写明。

- 锁定门控后，在 test（1,000 题）上只做一次正式评测：报告 F1/EM、再检索率（成本）及与基线的比较，并给出配对 bootstrap 置信区间。不得在 test 上继续调参或多次回看后改规则。

- 依据完整实验记录撰写详细实验报告与论文的 Implementation and Experimental Results 章节。正式论文仍须遵守 IEEE 格式要求。

## 附录&#32;&#32;脚本、文件与输出路径

下列路径分别位于隔离工作目录（/workspace）与用户设备 YangQS（G:/NLP\_project/）。脚本测试次数只说明交付前的自检，不是实验结果。

<strong>表 21&#32;&#32;脚本与记录中的测试情况</strong>

<table>
<thead>
<tr>
<th><p>步骤</p></th>
<th><p>主要脚本（隔离目录）</p></th>
<th><p>说明</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>2</p></td>
<td><p>/workspace/exp/step2/bm25_topk.py</p></td>
<td><p>BM25 召回；官方运行在 YangQS 上确认与核验运行一致。</p></td>
</tr>
<tr>
<td><p>3</p></td>
<td><p>/workspace/exp/step3/compare_models.py</p><p>README_step3.md</p><p>test_mock_server.py</p></td>
<td><p>检索、提示、解析、评分与 API 客户端的公共实现，后续步骤导入该模块，而不是复制代码。</p></td>
</tr>
<tr>
<td><p>5</p></td>
<td><p>/workspace/exp/step5/run_pilot.py</p><p>README_step5.md</p><p>test_step5.py（23 项自检通过）</p></td>
<td><p>100 题试点：双分支作答、本地 NLI、go/no-go。</p></td>
</tr>
<tr>
<td><p>5 审核</p></td>
<td><p>/workspace/exp/step5/audit_helper.py</p></td>
<td><p>生成供人工填写的 audit_review.csv；标签由人填写，不由脚本指定。</p></td>
</tr>
<tr>
<td><p>5 诊断</p></td>
<td><p>/workspace/exp/step5/analyze_signals.py</p><p>test_analyze_signals.py（6 项自检通过）</p></td>
<td><p>离线 AUC 与类别均值；不调阈值。</p></td>
</tr>
<tr>
<td><p>探测</p></td>
<td><p>/workspace/exp/step5/probe_logprobs.py</p></td>
<td><p>4 次短调用，检查温度 0/1 下的 logprob。</p></td>
</tr>
<tr>
<td><p>5b</p></td>
<td><p>/workspace/exp/step5b/rerun_toplogprobs.py</p><p>README_step5b.md</p><p>test_step5b.py（17 项自检通过）</p></td>
<td><p>top_logprobs 重跑与 margin 分析；拒绝写入名为 cache.jsonl 的文件。</p></td>
</tr>
<tr>
<td><p>6a（未运行）</p></td>
<td><p>/workspace/exp/step6a/check_logprobs.py</p><p>README_step6a.md</p><p>test_step6a.py（16 项自检通过）</p></td>
<td><p>本地 vLLM 退化检查。准备条目写明：既有测试仍通过（step5 23/23，analyze_signals 6/6，step5b 17/17）。</p></td>
</tr>
<tr>
<td><p>记录与方案</p></td>
<td><p>/workspace/exp/EXPERIMENT_LOG.md</p><p>/workspace/lr/Experiment_Protocol_v2.docx（及 .pdf）</p></td>
<td><p>实验记录为数字与决策的权威来源；方案模板 v2 的状态为「通过预实验，正式方案待锁定」。</p></td>
</tr>
</tbody>
</table>

<strong>表 22&#32;&#32;YangQS 上已产生或计划产生的输出路径</strong>

<table>
<thead>
<tr>
<th><p>步骤</p></th>
<th><p>路径</p></th>
<th><p>状态</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>数据</p></td>
<td><p>G:/NLP_project/{pilot,tune,test}.json</p></td>
<td><p>已生成</p></td>
</tr>
<tr>
<td><p>2</p></td>
<td><p>G:/NLP_project/step2_m1/{summary.json, per_question.csv}</p><p>G:/NLP_project/step2_m2/{…}</p></td>
<td><p>已生成</p></td>
</tr>
<tr>
<td><p>3</p></td>
<td><p>G:/NLP_project/step3_deepseek/{summary.json, per_question.csv, cache.jsonl}</p></td>
<td><p>已生成</p></td>
</tr>
<tr>
<td><p>5</p></td>
<td><p>G:/NLP_project/step5_pilot/{summary.json, per_question.csv, branches.jsonl, nli_scores.jsonl, audit_sample.csv, cache.jsonl, audit_review.csv, signal_summary.json, signal_by_class.csv}</p></td>
<td><p>已生成</p></td>
</tr>
<tr>
<td><p>探测</p></td>
<td><p>G:/NLP_project/probe_logprobs.json</p></td>
<td><p>已生成</p></td>
</tr>
<tr>
<td><p>5b</p></td>
<td><p>G:/NLP_project/step5b_toplp/toplp_summary.json（以及该目录下的单独缓存等）</p></td>
<td><p>已生成</p></td>
</tr>
<tr>
<td><p>6a</p></td>
<td><p>计划：step6a_check/logprob_check.json（及 token 表）</p></td>
<td><p>待运行</p></td>
</tr>
</tbody>
</table>

<strong>注：</strong>第 5 步审核文件在隔离目录另有副本 /workspace/exp/step5/audit\_review\_yangqs.csv。

报告全文依据实验记录撰写。记录中未出现、因而本文也未给出的数量包括但不限于：上下文段落少于 10 个的题目精确计数、SHA-256 哈希值、第 5 步 100 题的 token / 延迟 / 费用、引用覆盖率与句子级 supporting-fact F1、Oracle 的 EM、说明性阈值 t ∈ \{0.50, 0.80, 0.90, 0.95\} 的具体性能数字、第 5b 步答案跨度定位失败而回退到全部 token 的次数，以及第 6a 步、tune 门控与 test 正式评测的任何结果。

<!-- header1.xml -->

<blockquote><p>现阶段实验报告  ·  Fuzzy-NLI Adaptive Retrieval</p></blockquote>

<!-- footer1.xml -->

<blockquote><p>2026-11-15  ·  第 <!-- Word field: PAGE --> 页 / 共 <!-- Word field: NUMPAGES --> 页</p></blockquote>

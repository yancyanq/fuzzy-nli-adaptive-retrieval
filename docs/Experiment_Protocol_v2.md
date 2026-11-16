<table>
<tbody>
<tr>
<td><p><strong>BNBU NLP 课程小组学期论文  ·  实验方案模板 v2</strong></p></td>
</tr>
</tbody>
</table>

# 实验方案模板

<em>A Fuzzy-NLI-based QA Chatbot System with Adaptive Retrieval</em>

基于模糊证据核验的自适应多跳问答系统

<table>
<thead>
<tr>
<th><p>项目</p></th>
<th><p>内容</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>文档类型</strong></p></td>
<td><p>实验方案模板（非最终方案；供勾选与填写后，经预实验再锁定）</p></td>
</tr>
<tr>
<td><p><strong>版本</strong></p></td>
<td><p>Template v2</p></td>
</tr>
<tr>
<td><p><strong>日期</strong></p></td>
<td><p>2026年11月12日（Asia/Shanghai，北京时间）</p></td>
</tr>
<tr>
<td><p><strong>方案状态</strong></p></td>
<td><p>通过预实验，正式方案待锁定</p></td>
</tr>
<tr>
<td><p><strong>填写约定</strong></p></td>
<td><p>凡标有「【待确认】」、下划线或「☐」的项目均为待填/待选项，不代表已做决策。</p></td>
</tr>
<tr>
<td><p><strong>结果声明</strong></p></td>
<td><p>本文不包含任何实验结果或已测得的超参数。第 6 节中 F1 从 0 到 1（或相反）的例子仅为说明门控标签，不是实测数据。</p></td>
</tr>
</tbody>
</table>

## 如何使用本模板

<strong>•&#32;&#32;</strong>先阅读第 0 节，确认核心问题、方案状态与流程描述是否准确。

<strong>•&#32;&#32;</strong>第 6 节的配对双分支设计与第 7 节的预实验是正式方案锁定前的必做项；请先完成预实验，再按第 7 节的 go / no-go 规则决定是否进入主实验。

<strong>•&#32;&#32;</strong>模型、数据规模、划分、超参数与阈值一律留空或勾选，确认后再填入，不要在未见数据前写成定论。

<strong>•&#32;&#32;</strong>第 11 节的结果表仅为记录格式，保持空白，待相应实验完成后再填。

<strong>•&#32;&#32;</strong>填写完成后用第 15 节总清单复核。本文件是工作稿，不必采用 IEEE 双栏；课程论文正文仍须按 IEEE 格式（10–12 页，10pt，双栏，单倍行距）撰写。

## 0&#32;&#32;项目概况

### 0.1&#32;&#32;题目与课程要求

<strong>英文题目：</strong><em>A Fuzzy-NLI-based QA Chatbot System with Adaptive Retrieval</em>

<strong>中文题目：</strong>基于模糊证据核验的自适应多跳问答系统（若需调整中文译名：【待确认】）

<table>
<thead>
<tr>
<th><p>项目</p></th>
<th><p>内容</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>课程与作业类型</strong></p></td>
<td><p>BNBU NLP 课程小组学期论文（term paper）</p></td>
</tr>
<tr>
<td><p><strong>论文格式</strong></p></td>
<td><p>IEEE 格式；10–12 页；10pt；双栏（double column）；单倍行距（single spacing）</p></td>
</tr>
<tr>
<td><p><strong>规定章节</strong></p></td>
<td><p>Introduction；Literature Review；Methodology；Implementation &amp; Experimental Results；Conclusion</p></td>
</tr>
<tr>
<td><p><strong>阶段性文献综述</strong></p></td>
<td><p>提交平台：iSpace；截止日期：2026年11月13日 23:00（Asia/Shanghai，北京时间）；参考文献不少于 10 篇；查重相似度低于 20%</p></td>
</tr>
<tr>
<td><p><strong>方案状态</strong></p></td>
<td><p>通过预实验，正式方案待锁定。预实验设置见第 7 节；主实验在 go / no-go 通过并锁定参数后再进行。</p></td>
</tr>
<tr>
<td><p><strong>本文定位</strong></p></td>
<td><p>文献综述之后的实验方案讨论稿。方案锁定后，再据此撰写 Methodology 与 Implementation &amp; Experimental Results。</p></td>
</tr>
</tbody>
</table>

### 0.2&#32;&#32;核心问题（修订后表述）

在完成第一轮带引用作答之后，系统能否在「至多追加一次检索」的约束下，选出最值得再检索的那些问题，从而提升答案质量，或在质量可接受时节约成本。

进入主实验之前，应先核实两件更基础的事情：（1）再检索本身能带来多少增益；（2）第一轮即可获得的信号，能否预测这一增益。若（1）的可争取空间很小，应先改进第二轮检索或再作答，而不是比较门控。若（1）有明显空间，再检验信号与门控是否选对了题。

<strong>核心问题表述确认：</strong>☐ 采用以上表述&#32;&#32;&#32;&#32;☐ 需修改：\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

### 0.3&#32;&#32;研究动机与逻辑链

综述与方法部分建议沿用下面这条由宽到窄的逻辑链。各环节保持审慎表述，不做「尚无工作 / 首次提出」一类过强宣称。

<table>
<thead>
<tr>
<th><p>环节</p></th>
<th><p>内容</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>Need</strong><br /><strong>（需求）</strong></p></td>
<td><p>Multi-hop QA 常需跨段落取证。第一轮检索的证据可能不足以支撑已起草的答案；但若每题都再检索一次，成本会上升，且再检索也可能改坏已经正确的答案。因此需要判断：哪些题值得再检索。</p></td>
</tr>
<tr>
<td><p><strong>Existing mechanisms</strong><br /><strong>（已有机制）</strong></p></td>
<td><p>自适应检索已有多种做法，包括 Adaptive-RAG、Self-RAG、CRAG、S2G-RAG，以及 Moskvoretskii et al.（ACL 2025）等工作。它们分别从问题复杂度、生成中的特殊标记、检索结果评价或训练得到的判断器等角度，决定何时检索或如何修正检索。</p></td>
</tr>
<tr>
<td><p><strong>Missing signal</strong><br /><strong>（缺失信号）</strong></p></td>
<td><p>上述机制较少把「已起草答案是否被当前证据所支持」作为门控的主信号。NLI / 事实一致性（factual consistency）一类验证器可以提供这种证据支持信号。</p></td>
</tr>
<tr>
<td><p><strong>Signal is hard to use</strong><br /><strong>（信号不易直接使用）</strong></p></td>
<td><p>NLI 给出蕴含、中立、矛盾三类分数，分数带有噪声，硬阈值往往较脆。跨段落证据还会带来聚合问题（见第 3.3 节）。MiniCheck 等验证器的主要验证场景仍以单文档为主，搬到 multi-hop、多引用设定时需要谨慎，并辅以人工抽查。</p></td>
</tr>
<tr>
<td><p><strong>Fuzzy logic as a tool</strong><br /><strong>（工具）</strong></p></td>
<td><p>模糊逻辑适合把若干软的、异质的连续信号结合起来。本项目拟把 NLI 分数、桥接实体一致性，以及在接口与度量确认之后的模型不确定性，一并纳入模糊规则，并与「使用完全相同输入的硬规则」对照，以分离「组合信号」与「模糊推理」的贡献。</p></td>
</tr>
<tr>
<td><p><strong>Gap</strong><br /><strong>（差距，措辞需谨慎）</strong></p></td>
<td><p>在统一的双分支缓存与成本口径下，检验模糊门控能否选出值得再检索的问题，并报告质量、再检索率与端到端成本。这是本项目拟推进的工作，不是对既有文献的否定。具体措辞：【待确认】</p></td>
</tr>
</tbody>
</table>

### 0.4&#32;&#32;系统流程

主路径只固定结构，模型和超参数在后续章节填写。正式比较门控时，第一轮答案与「固定策略再检索后的答案」应对每道评估题都保存下来，而不是只在门控触发时才再检索（理由见第 6 节）。

HotpotQA distractor 设定下的问题&#32;&#32;→&#32;&#32;第 1 轮检索&#32;&#32;→&#32;&#32;带引用作答（作为共享的第一轮分支）&#32;&#32;→&#32;&#32;由第一轮信号计算门控输入（NLI 核验等）&#32;&#32;→&#32;&#32;门控决定是否采用再检索分支（至多一次）&#32;&#32;→&#32;&#32;再检索分支：按固定策略改写查询，从尚未使用的候选段落中取新证据并再次作答&#32;&#32;→&#32;&#32;输出最终答案与证据。

对照路径另设全上下文（full-context）：将 distractor 池中全部 10 个候选段落一次性提供给同一作答模型，只作答一次、不再检索。该路径用于衡量「小候选池上不做门控」时的质量、token 与端到端延迟（见第 5 节与第 14 节）。

<strong>流程确认：</strong>☐ 同意以上主路径&#32;&#32;&#32;&#32;☐ 需修改：\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

### 0.5&#32;&#32;门控信号

预实验与主实验优先使用前两类信号；模型不确定性待接口与度量确认后再加入。

<strong>•&#32;&#32;</strong><strong>NLI three-way scores。</strong>NLI 三分类分数：entailment / neutral / contradiction。作为门控输入，不作为主表中的引用命中指标。

<strong>•&#32;&#32;</strong><strong>Bridge-entity coherence。</strong>答案所依赖的桥接实体在已检索证据中是否可定位、前后是否一致。

<strong>•&#32;&#32;</strong><strong>Model uncertainty（后置）。</strong>作答模型对其答案或引用的不确定程度。加入主实验前须确认接口与具体度量（例如生成概率、token entropy，或其他）：【待确认】。

<strong>信号集合确认：</strong>☐ 预实验先用 NLI + 桥接实体&#32;&#32;&#32;&#32;☐ 不确定性的度量已确定，一并加入&#32;&#32;&#32;&#32;☐ 其他：\_\_\_\_\_\_\_\_

### 0.6&#32;&#32;成本口径与一项需提前注意的限制

HotpotQA distractor 设定下，每题候选段落为 10 个（含金标准段落与干扰段落）。在如此小的池内省去一次排序或补查，节省可能有限，而 NLI 核验与查询改写还会引入额外开销。因此不能预先假定「门控一定更省」。若预实验或主实验表明，全上下文在质量相近的同时更快或更便宜，应如实报告；这一结果将限定门控在小候选池上的实际价值。若成本优势不明显，论文可以把门控的选题准确率与质量增益作为主要论述，成本作为次要结果——但仍须完整报告成本。

拟统一统计的成本项（请勾选）：

☐&#32;&#32;每道题至多追加一次检索。

☐&#32;&#32;再检索触发比例（re-retrieval rate）。

☐&#32;&#32;模型调用次数（LLM 与 NLI 分别计数）。

☐&#32;&#32;处理的 token 数（输入 / 输出分别记录，口径：【待确认】）。

☐&#32;&#32;端到端延迟（平均 / P90：【待确认】）。门控策略的延迟须在真实执行路径上另测，计入 NLI 与查询改写开销，不能只用离线回放的分支缓存来代替。

☐&#32;&#32;其他：\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

### 0.7&#32;&#32;预期贡献（谨慎表述，供改写）

以下仅为拟声称贡献的草稿，须与最终实验结果相符后再写入论文。不使用「首次 / 尚无先前工作」等过强表述。

<strong>•&#32;&#32;</strong>在配对双分支设定下，用模糊门控（及同输入硬规则、NLI 阈值等对照）决定是否采用再检索分支，并报告质量、再检索率与端到端成本。表述确认：【待确认】

<strong>•&#32;&#32;</strong>把「再检索本身的可争取增益」（Oracle 上界）与「门控是否选对题」分开报告，避免只看平均分而掩盖改进与改坏相互抵消。表述确认：【待确认】

<strong>•&#32;&#32;</strong>在输入完全相同、再检索率目标对齐的条件下，比较模糊推理与硬规则，以考察模糊门控的独立贡献。表述确认：【待确认】

如需增删或改写：\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

### 0.8&#32;&#32;现有原型

已有可运行的 Python 原型骨架，目录名为 fnli\_qa（当前工作副本位于 /workspace/fnli\_qa）。原型默认使用 mock LLM 与 mock NLI，用途仅限于验证数据格式、模块接口与全流程能否跑通，不能替代预实验或正式实验，其结果也不得写入论文主表。

<table>
<thead>
<tr>
<th><p>项目</p></th>
<th><p>现状（据现有原型，非实验结果）</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>门控实现</strong></p></td>
<td><p>已实现六种门控接口：Never、Always、Threshold、Rule、Fuzzy、Full-context（fullctx）。正式方案中的「同输入硬规则」应对齐 Fuzzy 的全部输入，见第 5 节。</p></td>
</tr>
<tr>
<td><p><strong>LLM / NLI</strong></p></td>
<td><p>当前为 mock，只验证流程。预实验起必须接入一个真实作答模型与一个真实 NLI 模型。</p></td>
</tr>
<tr>
<td><p><strong>测试</strong></p></td>
<td><p>单元测试 14 项已通过（以原型仓库当前状态为准），不代表方法有效。</p></td>
</tr>
<tr>
<td><p><strong>真实运行所需条件</strong></p></td>
<td><p>接入真实 LLM 需配置 FNLI_API_KEY（及可选的 FNLI_BASE_URL、FNLI_MODEL）；接入真实 NLI 需安装 torch 与 transformers。</p></td>
</tr>
<tr>
<td><p><strong>已知限制</strong></p></td>
<td><p>稠密检索器目前为 stub。预实验与第一版主实验拟在候选池内使用 BM25，不依赖 dense。</p></td>
</tr>
<tr>
<td><p><strong>与本方案的关系</strong></p></td>
<td><p>原型中的小规模子集（如用于冒烟的样本）不得当作本方案已确定的样本量。预实验与正式样本见第 2、第 7、第 8 节。</p></td>
</tr>
</tbody>
</table>

## 1&#32;&#32;研究问题与假设

三个研究问题与第 0.2 节的核心问题对应。主实验优先回答 RQ1 与 RQ2；RQ3 在前两者有结果后再做，并优先考察 NLI 与桥接实体。假设请在预实验观察之后、查看正式测试结果之前填写，不要写成已证实的结论。

<table>
<thead>
<tr>
<th><p>编号</p></th>
<th><p>简称</p></th>
<th><p>研究问题</p></th>
<th><p>假设（待填写）</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>RQ1</strong></p></td>
<td><p>选题与质量–成本权衡</p></td>
<td><p>在至多一次额外检索的约束下，门控能否选出最值得再检索的问题，从而提升答案质量，或在质量可接受时控制成本？再检索本身的可争取增益有多大（以 Oracle 为上界）？</p></td>
<td><p>H1：【待确认】</p></td>
</tr>
<tr>
<td><p><strong>RQ2</strong></p></td>
<td><p>模糊门控的独立贡献</p></td>
<td><p>在第一轮结果、再检索方法与再作答模型都相同，且在 dev 上调到同一目标再检索率的条件下，模糊门控是否优于使用完全相同输入的硬规则，以及是否优于仅使用 NLI 阈值的硬门控？</p></td>
<td><p>H2：【待确认】</p></td>
</tr>
<tr>
<td><p><strong>RQ3</strong></p></td>
<td><p>主要信号的贡献</p></td>
<td><p>去掉 NLI 相关输入、或去掉桥接实体一致性之后，门控的选题质量与最终 F1、再检索率如何变化？模型不确定性仅在接口与度量确认后再纳入本问题。</p></td>
<td><p>H3：【待确认】</p></td>
</tr>
</tbody>
</table>

其他研究问题或假设（如有）：【待确认】\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

<strong>假设检验的显著性水平 α =</strong>&#32;&#32;【待确认】&#32;&#32;&#32;&#32;☐ 0.05&#32;&#32;&#32;&#32;☐ 0.01&#32;&#32;&#32;&#32;☐ 其他：\_\_\_\_

<table>
<tbody>
<tr>
<td><p><strong>说明  </strong>预实验先回答两个前置问题：再检索相对 Never 的 Oracle 增益是否足够大；在相近再检索率下，NLI 与桥接实体信号是否能选出更多「再检索后 F1 上升」的题。这两个问题的 go / no-go 阈值见第 7 节，本身不等于 RQ 的最终答案。</p></td>
</tr>
</tbody>
</table>

## 2&#32;&#32;数据集

预实验与正式评估必须使用互斥样本。正式评估须写明所取的公开 HotpotQA 划分。预实验建议规模与题型见第 7 节；正式样本量根据预实验中的逐题差异、改进题比例与预算再定，此处不提前写死。

### 2.1&#32;&#32;候选数据与来源

☐&#32;&#32;HotpotQA distractor 设定（官方下载：https&#58;//hotpotqa.github.io/）。

☐&#32;&#32;HotpotQA distractor 设定（Hugging Face：hotpotqa/hotpot\_qa，config 选 distractor）。

☐&#32;&#32;其他数据集或设定：\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

该设定下每题附带 10 个候选段落（含金标准段落与干扰段落），并标注支持事实句（supporting facts）。答案与支持事实的官方评分使用 HotpotQA 评测脚本：https&#58;//github.com/hotpotqa/hotpot/blob/master/hotpot\_evaluate\_v1.py。主表中的引用命中指标采用该脚本计算的 supporting-fact F1，而不是 NLI 分数。

### 2.2&#32;&#32;题型、划分与样本量

<table>
<tbody>
<tr>
<td><p><strong>说明  </strong>规则、阈值与隶属函数只允许在预实验 / dev / tuning 划分上确定，不得在正式评估样本上调参。预实验样本与正式评估样本必须互斥。</p></td>
</tr>
</tbody>
</table>

<table>
<thead>
<tr>
<th><p>项目</p></th>
<th><p>填写 / 勾选</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>数据版本 / dump 日期</strong></p></td>
<td><p>【待确认】</p></td>
</tr>
<tr>
<td><p><strong>预实验题型</strong></p></td>
<td><p>先行以 bridge 题为主。☐ 预实验仅用 bridge    ☐ 预实验同时包含 comparison    ☐ 其他：____</p></td>
</tr>
<tr>
<td><p><strong>关于 comparison 题的说明义务</strong></p></td>
<td><p>若预实验或主实验排除 comparison 题，或之后再加入，必须在论文中明确写出范围，不得把仅在 bridge 上的结论写成整个 HotpotQA distractor 的结论。</p></td>
</tr>
<tr>
<td><p><strong>预实验（dev / tuning）样本量</strong></p></td>
<td><p>建议 50–100 题，确切数目：【待确认】  题</p></td>
</tr>
<tr>
<td><p><strong>正式评估所用的公开划分</strong></p></td>
<td><p>【待确认】  ☐ 官方 distractor dev 中与预实验互斥的子集    ☐ 其他公开划分：____</p></td>
</tr>
<tr>
<td><p><strong>正式评估样本量</strong></p></td>
<td><p>【待确认】（根据预实验的逐题 F1 差异、improved 比例与预算决定，见第 7.4 节）</p></td>
</tr>
<tr>
<td><p><strong>两套样本是否互斥</strong></p></td>
<td><p>☐ 是（要求）    ☐ 否（须说明理由）：____</p></td>
</tr>
<tr>
<td><p><strong>抽样方式与随机种子</strong></p></td>
<td><p>方式：【待确认】    种子：【待确认】</p></td>
</tr>
<tr>
<td><p><strong>抽样清单文件路径</strong></p></td>
<td><p>【待确认】</p></td>
</tr>
<tr>
<td><p><strong>是否另设流程冒烟子集（不计入预实验与正式结果）</strong></p></td>
<td><p>☐ 是，规模：____    ☐ 否</p></td>
</tr>
</tbody>
</table>

### 2.3&#32;&#32;预处理

☐&#32;&#32;保留官方段落与句子切分，不做额外清洗。

☐&#32;&#32;支持事实句与系统引用 ID 的对齐方式：\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

☐&#32;&#32;缺失字段、坏样本的过滤规则：\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

☐&#32;&#32;其他：\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

<strong>预处理代码入口 / 配置文件：</strong>&#32;&#32;【待确认】

## 3&#32;&#32;系统组件

预实验对检索与第二轮改写给出了最小版本约定（见第 7 节）。主实验若沿用或更改，须在锁定方案时注明。模型名称仍待确认。

### 3.1&#32;&#32;检索器

☐&#32;&#32;在 distractor 候选池内使用 BM25（预实验与第一版主实验的默认候选）。实现与参数 k1 / b：【待确认】

☐&#32;&#32;Dense retriever（仅在实现补全后作为补充；现有原型中仍为 stub）。模型：【待确认】

☐&#32;&#32;其他：\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

<strong>第 1 轮 top-k（单位：☐ 段落&#32;&#32;☐ 句子）=</strong>&#32;&#32;【待确认】&#32;&#32;&#32;&#32;预实验中该值应固定。

<strong>第 2 轮取证范围：</strong>&#32;&#32;从尚未被第一轮使用的候选段落中选取新证据。第 2 轮 top-k = 【待确认】

<strong>第 2 轮查询生成：</strong>&#32;&#32;☐ 规则改写（预实验采用）&#32;&#32;&#32;&#32;☐ LLM 生成 follow-up query&#32;&#32;&#32;&#32;☐ 其他：\_\_\_\_

<table>
<tbody>
<tr>
<td><p><strong>说明  </strong>预实验规定：第二轮使用基于规则的查询改写，并从尚未使用的候选段落中选择新证据。主实验默认沿用同一再检索方法，以便门控比较不被检索器差异干扰。若主实验更改再检索方法，须重新缓存再检索分支。</p></td>
</tr>
</tbody>
</table>

### 3.2&#32;&#32;作答模型

预实验与主实验各使用一个真实作答模型（可相同）。候选如下，主模型待圈定：

☐&#32;&#32;GPT-4o-mini（实验当日的接口与模型名：【待确认】）

☐&#32;&#32;DeepSeek（具体型号：【待确认】）

☐&#32;&#32;Qwen2.5-7B-Instruct

☐&#32;&#32;Llama-3.1-8B-Instruct

☐&#32;&#32;其他：\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

<table>
<thead>
<tr>
<th><p>项目</p></th>
<th><p>填写 / 勾选</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>预实验所用作答模型</strong></p></td>
<td><p>【待确认】</p></td>
</tr>
<tr>
<td><p><strong>主实验所用作答模型</strong></p></td>
<td><p>【待确认】    与预实验是否相同：☐ 是  ☐ 否（说明）：____</p></td>
</tr>
<tr>
<td><p><strong>Full-context 所用模型</strong></p></td>
<td><p>须与门控路径的作答模型相同（同一模型、全部 10 段、只作答一次）。</p></td>
</tr>
<tr>
<td><p><strong>部署方式</strong></p></td>
<td><p>☐ API    ☐ 本地 GPU    ☐ 其他：____</p></td>
</tr>
<tr>
<td><p><strong>temperature / top-p / max tokens / seed</strong></p></td>
<td><p>【待确认】 / 【待确认】 / 【待确认】 / 【待确认】</p></td>
</tr>
<tr>
<td><p><strong>输出形式</strong></p></td>
<td><p>☐ 结构化 JSON（answer + cited_ids）    ☐ 其他：____    非法输出处理：【待确认】</p></td>
</tr>
<tr>
<td><p><strong>再作答是否使用同一模型与同一解码设置</strong></p></td>
<td><p>☐ 是（要求，除非另有说明）    ☐ 否：____</p></td>
</tr>
<tr>
<td><p><strong>prompt 模板路径与版本</strong></p></td>
<td><p>【待确认】（见下框）</p></td>
</tr>
</tbody>
</table>

Prompt 模板占位（定稿后粘贴或写明版本化路径；此处不预设措辞）：

<table>
<tbody>
<tr>
<td><p>【Prompt 模板待确认】<br /><br />System:<br />________________<br /><br />User:<br />________________<br /><br />输出约束（answer / cited_ids / 其他字段）：<br />________________<br /><br />文件路径与版本：________________</p></td>
</tr>
</tbody>
</table>

### 3.3&#32;&#32;NLI 核验器与跨段落证据构造

候选（预实验与主实验各选定一个真实 NLI 模型）：

☐&#32;&#32;cross-encoder/nli-deberta-v3-base

☐&#32;&#32;MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli

☐&#32;&#32;roberta-large-mnli

☐&#32;&#32;其他：\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

<strong>预实验 / 主实验所用 NLI：</strong>&#32;&#32;【待确认】 / 【待确认】

跨段落聚合是本项目必须写明的设计选择。若对每条引用句分别打分再取 max，可能把「只被其中一跳支持」当成答案已被充分支持；若取 min，又可能把「必须两段合在一起才成立」的答案误判为不支持。因此第一版不采用先逐句打分再 max / min 的做法。

<table>
<thead>
<tr>
<th><p>项目</p></th>
<th><p>填写 / 勾选</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>第一版 premise 构造</strong></p></td>
<td><p>将有效引用（valid citations）按固定顺序拼接后，作为单一 premise。拼接顺序规则：【待确认】    「有效」的定义：【待确认】</p></td>
</tr>
<tr>
<td><p><strong>第一版 hypothesis 构造</strong></p></td>
<td><p>把问题与简短答案改写成一句可判定的陈述（checkable declarative hypothesis）。改写方式：☐ 规则模板    ☐ 另调用模型    ☐ 其他：____    模板 / 路径：【待确认】</p></td>
</tr>
<tr>
<td><p><strong>NLI 输出的用途</strong></p></td>
<td><p>三分类分数作为门控输入。主表中的引用命中不使用 NLI 分数，而使用官方 supporting-fact F1（hotpot_evaluate_v1.py）。</p></td>
</tr>
<tr>
<td><p><strong>设备与批大小</strong></p></td>
<td><p>【待确认】</p></td>
</tr>
</tbody>
</table>

须对 NLI 判断做人工抽查，至少覆盖以下三类情形（可与文献综述中「MiniCheck 等验证器主要以单文档验证」的边界讨论相呼应）：

☐&#32;&#32;缺失一跳（missing hop）：证据只覆盖部分推理链。

☐&#32;&#32;错误引用（wrong citation）：所引句子与答案无关或引错。

☐&#32;&#32;两段共同支持（jointly supported by two paragraphs）：单段不足以支持，拼接后应被支持。

<strong>抽查样本量与记录表路径：</strong>&#32;&#32;【待确认】

## 4&#32;&#32;模糊门控设计

隶属函数、规则库与决策阈值只允许在预实验 / dev / tuning 样本上调节，锁定后再用于正式评估。与第 5 节的同输入硬规则须使用完全相同的输入变量。模型不确定性仅在接口与度量确认后出现在下表中。

### 4.1&#32;&#32;输入变量

<table>
<thead>
<tr>
<th><p>变量</p></th>
<th><p>是否使用 / 定义</p></th>
<th><p>模糊集（语言值）</p></th>
<th><p>隶属函数类型与参数</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>NLI entailment 分数</strong></p></td>
<td><p>☐ 使用（优先）</p></td>
<td><p>【待确认】，如 Low / Medium / High</p></td>
<td><p>【待确认】</p></td>
</tr>
<tr>
<td><p><strong>NLI neutral 分数</strong></p></td>
<td><p>☐ 使用  ☐ 不使用</p></td>
<td><p>【待确认】</p></td>
<td><p>【待确认】</p></td>
</tr>
<tr>
<td><p><strong>NLI contradiction 分数</strong></p></td>
<td><p>☐ 使用  ☐ 不使用</p></td>
<td><p>【待确认】</p></td>
<td><p>【待确认】</p></td>
</tr>
<tr>
<td><p><strong>Bridge-entity coherence</strong></p></td>
<td><p>☐ 使用（优先）；定义：____</p></td>
<td><p>【待确认】</p></td>
<td><p>【待确认】</p></td>
</tr>
<tr>
<td><p><strong>Model uncertainty</strong></p></td>
<td><p>☐ 暂不使用    ☐ 已确认后使用；度量：____</p></td>
<td><p>【待确认】</p></td>
<td><p>【待确认】</p></td>
</tr>
<tr>
<td><p><strong>其他：____</strong></p></td>
<td><p>【待确认】</p></td>
<td><p>【待确认】</p></td>
<td><p>【待确认】</p></td>
</tr>
</tbody>
</table>

### 4.2&#32;&#32;隶属函数、规则与决策

☐&#32;&#32;三角隶属函数（triangular）

☐&#32;&#32;梯形隶属函数（trapezoidal）

☐&#32;&#32;高斯隶属函数（Gaussian）

☐&#32;&#32;其他：\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

<strong>参数与附图 / 配置文件路径：</strong>&#32;&#32;【待确认】

规则库模板（空行供定稿后填写，不预写规则内容）：

<table>
<thead>
<tr>
<th><p>编号</p></th>
<th><p>前件（IF）</p></th>
<th><p>后件（THEN）</p></th>
<th><p>权重（若有）</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>1</strong></p></td>
<td><p>IF  【待确认】</p></td>
<td><p>THEN  【待确认】</p></td>
<td><p>【待确认】</p></td>
</tr>
<tr>
<td><p><strong>2</strong></p></td>
<td><p>IF  【待确认】</p></td>
<td><p>THEN  【待确认】</p></td>
<td><p>【待确认】</p></td>
</tr>
<tr>
<td><p><strong>3</strong></p></td>
<td><p>IF  【待确认】</p></td>
<td><p>THEN  【待确认】</p></td>
<td><p>【待确认】</p></td>
</tr>
<tr>
<td><p><strong>4</strong></p></td>
<td><p>IF  【待确认】</p></td>
<td><p>THEN  【待确认】</p></td>
<td><p>【待确认】</p></td>
</tr>
<tr>
<td><p><strong>5</strong></p></td>
<td><p>IF  【待确认】</p></td>
<td><p>THEN  【待确认】</p></td>
<td><p>【待确认】</p></td>
</tr>
<tr>
<td><p><strong>6</strong></p></td>
<td><p>IF  【待确认】</p></td>
<td><p>THEN  【待确认】</p></td>
<td><p>【待确认】</p></td>
</tr>
</tbody>
</table>

<strong>规则总数与来源：</strong>&#32;&#32;【待确认】&#32;&#32;&#32;&#32;☐ 人工设计&#32;&#32;&#32;&#32;☐ 结合 dev 观察&#32;&#32;&#32;&#32;☐ 其他：\_\_\_\_

<table>
<thead>
<tr>
<th><p>项目</p></th>
<th><p>填写 / 勾选</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>推理方法</strong></p></td>
<td><p>☐ Mamdani    ☐ Sugeno    ☐ 其他：____</p></td>
</tr>
<tr>
<td><p><strong>and / or 算子与去模糊化</strong></p></td>
<td><p>算子：【待确认】    ☐ centroid    ☐ bisector    ☐ MOM    ☐ 其他：____</p></td>
</tr>
<tr>
<td><p><strong>输出变量含义</strong></p></td>
<td><p>【待确认】（例如「采用再检索分支的倾向」）</p></td>
</tr>
<tr>
<td><p><strong>决策阈值（转为是否再检索）</strong></p></td>
<td><p>【待确认】</p></td>
</tr>
<tr>
<td><p><strong>与硬规则对齐的调参目标</strong></p></td>
<td><p>在 dev 上把 Fuzzy 与同输入硬规则调到同一目标再检索率（见第 5.2 节）。目标再检索率：【待确认】</p></td>
</tr>
<tr>
<td><p><strong>边界情况处理</strong></p></td>
<td><p>【待确认】</p></td>
</tr>
</tbody>
</table>

## 5&#32;&#32;对比策略

主实验保留六种策略，优先服务 RQ1 与 RQ2。除 Full-context 外，门控策略都在同一对缓存分支上做离线决策（第 6 节）：第一轮答案相当于 Never，固定策略再检索后的答案相当于 Always。Oracle 不是可部署策略，只作为「门控可争取增益」的上界，在结果表中单列一行。

<table>
<thead>
<tr>
<th><p>策略</p></th>
<th><p>做法简述</p></th>
<th><p>比较目的</p></th>
<th><p>待填参数</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>Never</strong><br /><strong>（从不追加）</strong></p></td>
<td><p>每题都采用第一轮答案，不使用再检索分支。</p></td>
<td><p>质量下限参照，也是双分支中的第一支。</p></td>
<td><p>无额外门控参数。</p></td>
</tr>
<tr>
<td><p><strong>Always</strong><br /><strong>（总是追加）</strong></p></td>
<td><p>每题都采用固定策略再检索后的答案。</p></td>
<td><p>给出「一律再检索」的质量与成本；也是双分支中的第二支。</p></td>
<td><p>第 2 轮 top-k 与规则改写：【待确认】</p></td>
</tr>
<tr>
<td><p><strong>NLI threshold</strong><br /><strong>（NLI 阈值）</strong></p></td>
<td><p>仅根据 NLI 相关分数与硬阈值，决定采用哪一支。</p></td>
<td><p>单信号硬门控对照，用于 RQ2。</p></td>
<td><p>所用分数：【待确认】<br />阈值在 dev 上选定：☐ 是</p></td>
</tr>
<tr>
<td><p><strong>Same-input</strong><br /><strong>crisp rule</strong><br /><strong>（同输入硬规则）</strong></p></td>
<td><p>使用与 Fuzzy 完全相同的输入变量，但以硬规则（if–else / 硬切分）决定采用哪一支。</p></td>
<td><p>这是检验模糊推理独立贡献的关键对照（即原「Crisp vs Fuzzy」比较，放入主策略表，不再另设重复消融）。</p></td>
<td><p>规则条目：【待确认】<br />与 Fuzzy 在 dev 上调到同一目标再检索率，见 5.2 节。</p></td>
</tr>
<tr>
<td><p><strong>Fuzzy（本方法）</strong></p></td>
<td><p>将与硬规则相同的输入转为隶属度，经模糊规则推理后决定采用哪一支。</p></td>
<td><p>检验本方法在选题、质量与成本上的表现（RQ1–RQ2）。</p></td>
<td><p>见第 4 节。须与硬规则共享第一轮结果、再检索方法与再作答模型。</p></td>
</tr>
<tr>
<td><p><strong>Full-context</strong><br /><strong>（全上下文）</strong></p></td>
<td><p>向同一作答模型一次性提供全部 10 个候选段落，只作答一次，不走再检索、也不走门控。</p></td>
<td><p>衡量小候选池上「不做门控」的质量、token 与端到端延迟，用于限定门控的实际价值。</p></td>
<td><p>输入顺序与截断：【待确认】</p></td>
</tr>
</tbody>
</table>

### 5.2&#32;&#32;同输入硬规则与 Fuzzy 的对齐要求

为了把「多信号组合」与「模糊推理」分开，同输入硬规则与 Fuzzy 必须满足下列约束。这组对比构成 RQ2 的主证据，第 8 节不再单列一项重复的 Crisp vs Fuzzy 消融。

☐&#32;&#32;二者使用完全相同的输入变量（预实验阶段为 NLI 相关分数与桥接实体一致性；不确定性仅在确认后同时加入二者）。

☐&#32;&#32;共享同一批第一轮检索与作答结果。

☐&#32;&#32;共享同一种再检索方法（规则改写 + 从未使用段落中取新证据）与同一个再作答模型及解码设置。

☐&#32;&#32;只在 dev / 预实验划分上调参，并把二者调到同一目标再检索率。目标再检索率 = 【待确认】（例如接近 Always 的某一比例，或按 dev 上 improved 比例来定）。

☐&#32;&#32;参数锁定后，在正式评估上报告实际再检索率与答案 F1（以及第 9 节的其他主 / 次指标），不得再调。

<strong>硬规则的规则表路径：</strong>&#32;&#32;【待确认】

### 5.3&#32;&#32;Full-context 与延迟测量

门控策略之间的质量与选题比较，在缓存好的双分支上离线完成，以保证每题的两支答案对所有门控都相同。端到端延迟不能用这种离线回放代替：须按真实执行路径另测，计入第一轮作答、NLI、查询改写、第二轮检索与再作答中实际会发生的步骤。Full-context 则单独测量「一次读入全部 10 段并作答」的质量、token 与端到端延迟。若 Full-context 在质量相近时更快，应如实写入结果，作为小候选池上门控实用价值的上界约束。

<strong>六种策略是否全部进入主实验：</strong>☐ 是&#32;&#32;&#32;&#32;☐ 删减（须说明）：\_\_\_\_\_\_\_\_

## 6&#32;&#32;配对双分支设计

本节是预实验与主实验共用的评价设计。若不给每道评估题都准备再检索分支，就无法计算门控的 Recall（「本应再检索却被跳过」的题根本没有第二支分数），也不能得到 Oracle 上界。

### 6.1&#32;&#32;对每道评估题都保存两支答案

<strong>•&#32;&#32;</strong><strong>分支 A。</strong>第一轮分支：固定 top-k 检索后的带引用答案。所有门控共享这一支，相当于 Never。

<strong>•&#32;&#32;</strong><strong>分支 B。</strong>按固定策略再检索（规则改写，从未使用的候选段落中取新证据）并再次作答后的答案。所有门控共享这一支，相当于 Always。即使某门控后来不会触发再检索，该题仍须预先生成并保存这一支。

<strong>•&#32;&#32;</strong>答案与支持事实一律用官方脚本 hotpot\_evaluate\_v1.py 评分。

<strong>双分支缓存的文件路径与字段清单：</strong>&#32;&#32;【待确认】

### 6.2&#32;&#32;门控标签、三类占比与 Oracle

门控的正负标签由逐题的官方答案 F1 变化定义，而不是由 NLI 分数定义。对每道题计算 ΔF1 = F1(分支 B) − F1(分支 A)，并据此分成三类：

<table>
<thead>
<tr>
<th><p>类别</p></th>
<th><p>定义</p></th>
<th><p>含义</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>improved（改进）</strong></p></td>
<td><p>ΔF1 &gt; 0</p></td>
<td><p>再检索提高了官方答案 F1；跳过该题等于漏掉一次有用再检索。</p></td>
</tr>
<tr>
<td><p><strong>tie（持平）</strong></p></td>
<td><p>ΔF1 = 0</p></td>
<td><p>再检索没有改变官方答案 F1。是否把极小数值波动并入 tie：【待确认】</p></td>
</tr>
<tr>
<td><p><strong>degraded（改坏）</strong></p></td>
<td><p>ΔF1 &lt; 0</p></td>
<td><p>再检索降低了官方答案 F1；跳过该题等于避免了一次有害再检索。</p></td>
</tr>
</tbody>
</table>

须报告三类题的数量与比例。门控决策的 Precision / Recall / F1 以「是否选对再检索」为标准，正类操作化定义：【待确认】&#32;&#32;☐ 仅 improved 应触发&#32;&#32;&#32;&#32;☐ improved 应触发且 degraded 应跳过，tie 的处理为：\_\_\_\_。

Oracle：对每道题在分支 A 与分支 B 中选取官方答案 F1 较高的一支（持平时的选取规则：【待确认】，建议保持第一轮答案以反映「不必要的再检索」）。Oracle 相对 Never 的平均 F1 之差，是任何只在这两支之间做选择的门控所能取得的增益上界。

### 6.3&#32;&#32;示意例子（不是实验结果）

下面两个数字只用来说明「平均分可能互相抵消」，不得当作已测结果。假设题 x 的官方答案 F1 从 0 变为 1：若门控跳过该题，就漏掉了一次有用再检索。假设题 y 的官方答案 F1 从 1 变为 0：若门控跳过该题，就避免了一次改坏。若只比较 Always 与 Never 的平均 F1，题 x 的提升与题 y 的下降可能相互抵消，看起来「再检索几乎没有用」，但门控其实既可能漏掉 x，也可能错误地对 y 再检索。因此必须按题报告 improved / tie / degraded，并用 Oracle 给出可争取的上界。

### 6.4&#32;&#32;离线评价与延迟分测

所有门控（NLI 阈值、同输入硬规则、Fuzzy，以及相应消融）都在同一份双分支缓存上离线评价：先算各题的门控输入，再决定采用 A 还是 B，最后统一评分。这样可保证对照之间的差异只来自决策，而不是来自再检索或再作答的随机波动。端到端延迟与 token 则按第 5.3 节在真实执行路径上另行测量。

## 7&#32;&#32;预实验（最小版本）

预实验在锁定正式方案之前进行，目的不是写出论文主表，而是判断再检索是否值得做、第一轮信号是否有预测力，以及正式评估需要多大样本。方案状态「通过预实验，正式方案待锁定」以本节的 go / no-go 为准。

### 7.1&#32;&#32;最小设置

<table>
<thead>
<tr>
<th><p>项目</p></th>
<th><p>最小版本约定 / 待填</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>样本量</strong></p></td>
<td><p>50–100 道，用于 dev / tuning。确切数目：【待确认】  题</p></td>
</tr>
<tr>
<td><p><strong>题型</strong></p></td>
<td><p>先行以 bridge 题为主。若排除 comparison，或之后再加入，须在论文中声明。</p></td>
</tr>
<tr>
<td><p><strong>检索</strong></p></td>
<td><p>在 10 个候选段落的池内做 BM25；第一轮 top-k 固定为：【待确认】</p></td>
</tr>
<tr>
<td><p><strong>第二轮</strong></p></td>
<td><p>基于规则的查询改写；从尚未使用的候选段落中选取新证据。改写规则路径：【待确认】</p></td>
</tr>
<tr>
<td><p><strong>作答模型</strong></p></td>
<td><p>接入一个真实作答模型：【待确认】（不得使用 mock）</p></td>
</tr>
<tr>
<td><p><strong>NLI 模型</strong></p></td>
<td><p>接入一个真实 NLI 模型：【待确认】（不得使用 mock）；premise / hypothesis 按第 3.3 节的第一版构造</p></td>
</tr>
<tr>
<td><p><strong>必须缓存的内容</strong></p></td>
<td><p>每道预实验题的分支 A、分支 B、官方 EM / F1 / supporting-fact F1、NLI 分数、桥接实体信号</p></td>
</tr>
<tr>
<td><p><strong>与正式评估的关系</strong></p></td>
<td><p>预实验样本不得进入正式评估；正式评估须另取互斥的公开划分子集，见第 2.2 节与第 7.4 节</p></td>
</tr>
</tbody>
</table>

### 7.2&#32;&#32;三项必读结果（预实验读出，不写入论文主结论亦可，但须内部记录）

<strong>•&#32;&#32;</strong><strong>读出 1。</strong>再检索是否提高了支持事实覆盖（官方 supporting-fact F1 或金标准段落 / 句子覆盖，具体口径：【待确认】）。比较分支 B 相对分支 A 的变化。

<strong>•&#32;&#32;</strong><strong>读出 2。</strong>按官方答案 F1 统计 improved / tie / degraded 的题数与比例。

<strong>•&#32;&#32;</strong><strong>读出 3。</strong>Oracle 相对 Never（分支 A）的答案 F1 增益，作为可争取空间的上界。

预实验记录表见第 11.4 节，填写前保持空白。

### 7.3&#32;&#32;决策规则与 go / no-go（阈值待填）

根据读出 3 与随后的信号检查，决定是否锁定并进入主实验。下列阈值须在查看预实验汇总前预先写明，避免事后改标准。

<table>
<thead>
<tr>
<th><p>条件</p></th>
<th><p>行动</p></th>
<th><p>阈值（须预先填写）</p></th>
<th><p>预实验后结论</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>若 Oracle 相对 Never 的增益较小</strong></p></td>
<td><p>判定：可争取空间不足，应先改进第二轮检索或再作答，而不是比较门控。</p></td>
<td><p>「较小」的标准：【待确认】<br />（例如平均 ΔF1 低于 ____，或 improved 比例低于 ____）</p></td>
<td><p>☐ 未测    ☐ 触发（停留改进）    ☐ 未触发</p></td>
</tr>
<tr>
<td><p><strong>若 Oracle 增益足够清楚</strong></p></td>
<td><p>进入信号检查：在相近的再检索率下，NLI 与桥接实体信号能否比随机或单阈值选出更多 improved 题、更少 degraded 题。</p></td>
<td><p>「足够清楚」的标准：【待确认】<br />信号检查的对照方式与再检索率：【待确认】</p></td>
<td><p>☐ 未测    ☐ 通过    ☐ 未通过</p></td>
</tr>
<tr>
<td><p><strong>模型不确定性</strong></p></td>
<td><p>不在最小预实验中强行加入。待接口与度量确认后，再决定是否纳入主实验输入，并同时加入同输入硬规则。</p></td>
<td><p>接口 / 度量确认状态：【待确认】</p></td>
<td><p>☐ 暂缓    ☐ 已确认，纳入</p></td>
</tr>
<tr>
<td><p><strong>NLI 人工抽查</strong></p></td>
<td><p>若第 3.3 节三类情形中错误过多，应先修正 premise / hypothesis 构造，再做门控比较。</p></td>
<td><p>不可接受的错误比例：【待确认】</p></td>
<td><p>☐ 未测    ☐ 通过    ☐ 需修正</p></td>
</tr>
<tr>
<td><p><strong>其他 go / no-go：____</strong></p></td>
<td><p>【待确认】</p></td>
<td><p>【待确认】</p></td>
<td><p></p></td>
</tr>
</tbody>
</table>

<strong>预实验综合决定：</strong>&#32;&#32;☐ 进入主实验并锁定方案&#32;&#32;&#32;&#32;☐ 先改进再检索 / 再作答后重做预实验&#32;&#32;&#32;&#32;☐ 其他：\_\_\_\_

### 7.4&#32;&#32;正式样本量如何确定

正式评估样本量不在此处预先指定，而由预实验的逐题 F1 差异、improved 比例以及预算共同决定。确定后须写明：所用公开划分、互斥规则、样本数、抽样种子与清单路径。预算约束（API 或算力）：【待确认】。拟定正式样本量：【待确认】（预实验结束后填写）。

## 8&#32;&#32;主实验安排与消融

仅在第 7 节 go / no-go 通过、并将 Fuzzy 与同输入硬规则的参数锁定之后，才在正式评估样本上给出主结果。主实验优先回答 RQ1 与 RQ2；RQ3 随其后。

### 8.1&#32;&#32;主实验范围

<table>
<thead>
<tr>
<th><p>项目</p></th>
<th><p>约定</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>策略集合</strong></p></td>
<td><p>第 5 节的六种策略全部保留，并在结果表中另列 Oracle 行作为上界。</p></td>
</tr>
<tr>
<td><p><strong>评价方式</strong></p></td>
<td><p>Never / Always / NLI 阈值 / 同输入硬规则 / Fuzzy 在同一双分支缓存上离线评价；Full-context 单独运行并测量质量、token 与延迟。</p></td>
</tr>
<tr>
<td><p><strong>首要报告</strong></p></td>
<td><p>答案 F1、再检索率、端到端成本（token 与真实路径延迟）。</p></td>
</tr>
<tr>
<td><p><strong>次要报告</strong></p></td>
<td><p>EM、官方 supporting-fact F1，以及逐题配对差异的置信区间（配对 bootstrap，见第 12 节）。</p></td>
</tr>
<tr>
<td><p><strong>正式样本</strong></p></td>
<td><p>与预实验互斥，来自写明的公开划分；样本量按第 7.4 节确定：【待确认】</p></td>
</tr>
</tbody>
</table>

### 8.2&#32;&#32;消融（服务 RQ3，优先级已排）

同输入硬规则已在主策略表中，不再作为消融重复出现。RQ3 优先做下面两项；模型不确定性仅在确认后增加相应去信号消融。

<table>
<thead>
<tr>
<th><p>纳入</p></th>
<th><p>名称</p></th>
<th><p>操作</p></th>
<th><p>备注</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>☐ 优先</p></td>
<td><p>w/o NLI</p></td>
<td><p>从 Fuzzy（及必要时从同输入硬规则）中去掉 NLI 相关输入，其余不变。</p></td>
<td><p>【待确认】</p></td>
</tr>
<tr>
<td><p>☐ 优先</p></td>
<td><p>w/o bridge-entity</p></td>
<td><p>去掉桥接实体一致性信号。</p></td>
<td><p>【待确认】</p></td>
</tr>
<tr>
<td><p>☐ 确认后再做</p></td>
<td><p>w/o uncertainty</p></td>
<td><p>仅当该信号已纳入主实验时进行。</p></td>
<td><p>度量：【待确认】</p></td>
</tr>
<tr>
<td><p>☐ 可选</p></td>
<td><p>其他</p></td>
<td><p>________________</p></td>
<td><p>【待确认】</p></td>
</tr>
</tbody>
</table>

<strong>消融是否使用与主实验相同的双分支缓存和正式样本：</strong>&#32;&#32;☐ 是（要求）&#32;&#32;&#32;&#32;☐ 否：\_\_\_\_

## 9&#32;&#32;评价指标

指标服务于第 0.2 节的核心问题与 RQ1–RQ3。答案与支持事实一律按官方脚本计算。NLI 分数只作门控输入，并可用于诊断性抽查，不替代主表中的 supporting-fact F1。

### 9.1&#32;&#32;首要指标

<table>
<thead>
<tr>
<th><p>采用</p></th>
<th><p>指标</p></th>
<th><p>理由（供讨论，不是实验结果）</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>☐</p></td>
<td><p>答案 F1（官方脚本）</p></td>
<td><p>HotpotQA 主要重叠指标，也是逐题 ΔF1、improved / tie / degraded 与 Oracle 的定义基础。</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>再检索率（re-retrieval rate）</p></td>
<td><p>门控触发采用分支 B 的比例。Never 为 0，Always 为 1；Fuzzy 与同输入硬规则须报告相对目标再检索率的实际值。</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>端到端成本：token 与真实路径延迟</p></td>
<td><p>Full-context 与各真实执行路径分别测量。离线门控回放不能代替延迟。成本优势若不明显，须如实报告，并把论述重点放到选题准确率与质量增益上。</p></td>
</tr>
</tbody>
</table>

### 9.2&#32;&#32;次要指标与诊断

<table>
<thead>
<tr>
<th><p>采用</p></th>
<th><p>指标</p></th>
<th><p>说明</p></th>
<th><p>位置</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>☐</p></td>
<td><p>EM（官方脚本）</p></td>
<td><p>与 F1 一并报告，但不作为门控标签的主定义。</p></td>
<td><p>次要</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>官方 supporting-fact F1</p></td>
<td><p>主表中的引用命中指标，衡量所引支持事实是否命中标注。预实验读出 1 亦用此口径或预先写明的覆盖率。</p></td>
<td><p>次要</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>逐题配对差异的置信区间</p></td>
<td><p>对 F1 等指标的逐题差值做配对 bootstrap，见第 12 节。</p></td>
<td><p>次要（推断）</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>improved / tie / degraded 比例，及门控 Precision / Recall / F1</p></td>
<td><p>回答「是否选对了题」。正类定义见第 6.2 节。</p></td>
<td><p>诊断 / 选题</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>Oracle 相对 Never 的 F1 增益</p></td>
<td><p>门控可争取空间的上界，不是可部署系统。</p></td>
<td><p>参照</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>Acc†、LLM-as-judge、ALCE citation P/R、AlignScore / MiniCheck、API 费用等</p></td>
<td><p>如需使用，放入附录，并说明与官方指标、与门控用 NLI 的关系。</p></td>
<td><p>☐ 附录  ☐ 不用</p></td>
</tr>
</tbody>
</table>

### 9.3&#32;&#32;计算细节

<table>
<thead>
<tr>
<th><p>项目</p></th>
<th><p>填写 / 约定</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>官方评测脚本</strong></p></td>
<td><p>https://github.com/hotpotqa/hotpot/blob/master/hotpot_evaluate_v1.py</p></td>
</tr>
<tr>
<td><p><strong>EM / F1 / supporting-fact 的标准化</strong></p></td>
<td><p>遵循该脚本，不另造规则（若有例外：【待确认】）</p></td>
</tr>
<tr>
<td><p><strong>门控标签所用的 ΔF1</strong></p></td>
<td><p>官方答案 F1(B) − F1(A)；tie 的数值容差：【待确认】</p></td>
</tr>
<tr>
<td><p><strong>延迟起止点</strong></p></td>
<td><p>【待确认】（须写明是否含模型加载、NLI、查询改写）</p></td>
</tr>
<tr>
<td><p><strong>token 统计口径</strong></p></td>
<td><p>【待确认】（是否含 prompt、是否分输入输出）</p></td>
</tr>
</tbody>
</table>

## 10&#32;&#32;实验流程与可复现性

### 10.1&#32;&#32;建议步骤

<strong>步骤 1&#32;&#32;</strong>按第 7 节准备预实验样本（bridge 为主，50–100 题的最终数目锁定为：【待确认】），接入真实作答模型与真实 NLI，固定第一轮 top-k 与第二轮规则改写。

<strong>步骤 2&#32;&#32;</strong>为每道预实验题生成并缓存分支 A 与分支 B，用官方脚本评分，完成三项读出，并做 NLI 三类情形的人工抽查。

<strong>步骤 3&#32;&#32;</strong>按第 7.3 节预先填写的阈值做 go / no-go。若空间不足，先改进再检索或再作答并重做本节；若通过，再在预实验样本上检查 NLI 与桥接实体的选题能力，并确定正式样本量与公开划分。

<strong>步骤 4&#32;&#32;</strong>在 dev 上将 Fuzzy 与同输入硬规则调到同一目标再检索率，锁定全部门控参数与 prompt / 改写规则版本。

<strong>步骤 5&#32;&#32;</strong>抽取与预实验互斥的正式评估样本，生成正式样本的双分支缓存；离线评价全部门控与优先消融；单独运行 Full-context；在真实路径上测量延迟与 token。

<strong>步骤 6&#32;&#32;</strong>填写第 11 节表格，计算配对差异的置信区间，完成错误分析，并撰写论文方法与实验章节。

### 10.2&#32;&#32;可复现性清单

<table>
<thead>
<tr>
<th><p>项目</p></th>
<th><p>填写 / 勾选</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>随机种子（抽样 / 若支持的解码）</strong></p></td>
<td><p>【待确认】 / 【待确认】</p></td>
</tr>
<tr>
<td><p><strong>正式实验重复次数</strong></p></td>
<td><p>【待确认】    因主比较在缓存分支上离线进行，须写明缓存是否来自单次生成：☐ 单次  ☐ 多次后汇总</p></td>
</tr>
<tr>
<td><p><strong>硬件与软件环境</strong></p></td>
<td><p>【待确认】</p></td>
</tr>
<tr>
<td><p><strong>代码版本</strong></p></td>
<td><p>仓库：【待确认】    commit：【待确认】    配置文件：【待确认】</p></td>
</tr>
<tr>
<td><p><strong>双分支与日志</strong></p></td>
<td><p>每题记录两支答案、引用、官方分数、NLI 与桥接信号、门控决策、耗时与 token。目录：【待确认】</p></td>
</tr>
<tr>
<td><p><strong>缓存策略</strong></p></td>
<td><p>☐ 缓存第一轮    ☐ 缓存再检索分支    ☐ 缓存 NLI    ☐ 其他：____    失效规则：____</p></td>
</tr>
<tr>
<td><p><strong>失败重试</strong></p></td>
<td><p>【待确认】</p></td>
</tr>
</tbody>
</table>

## 11&#32;&#32;结果记录表模板

下列表格只提供记录格式，单元格保持「—」或空白。请在相应实验完成前不要填入数字。Oracle 行为参照上界；同输入硬规则行用于 RQ2。

### 11.1&#32;&#32;主结果：质量、再检索率与成本

<em>表 11-1&#32;&#32;首要与次要指标（空白表。Fuzzy 与同输入硬规则须同时报告目标再检索率与实际再检索率）</em>

<table>
<thead>
<tr>
<th><p>策略</p></th>
<th><p>答案 F1</p></th>
<th><p>再检索率</p></th>
<th><p>端到端延迟</p></th>
<th><p>Tokens</p></th>
<th><p>EM</p></th>
<th><p>Supp-F1</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>Never（分支 A）</strong></p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
</tr>
<tr>
<td><p><strong>Always（分支 B）</strong></p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
</tr>
<tr>
<td><p><strong>NLI threshold</strong></p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
</tr>
<tr>
<td><p><strong>同输入硬规则</strong></p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
</tr>
<tr>
<td><p><strong>Fuzzy（本方法）</strong></p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
</tr>
<tr>
<td><p><strong>Full-context</strong></p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
</tr>
<tr>
<td><p><strong>Oracle（上界，非系统）</strong></p></td>
<td><p>—</p></td>
<td><p>—（按题选优）</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
</tr>
</tbody>
</table>

<strong>Fuzzy / 硬规则的目标再检索率（dev）：</strong>&#32;&#32;【待确认】 / 【待确认】&#32;&#32;&#32;&#32;二者应相同。

### 11.2&#32;&#32;逐题变化：improved / tie / degraded

<em>表 11-2&#32;&#32;再检索相对第一轮的官方答案 F1 变化（空白表）。Always 行即分支 B 相对分支 A 的真实变化，与门控无关；各门控行表示「该门控实际采用的那一支」相对分支 A 的变化。</em>

<table>
<thead>
<tr>
<th><p>策略</p></th>
<th><p>improved 数 / 比例</p></th>
<th><p>tie 数 / 比例</p></th>
<th><p>degraded 数 / 比例</p></th>
<th><p>备注</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>Always vs Never（数据本身）</strong></p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p></p></td>
</tr>
<tr>
<td><p><strong>NLI threshold</strong></p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p></p></td>
</tr>
<tr>
<td><p><strong>同输入硬规则</strong></p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p></p></td>
</tr>
<tr>
<td><p><strong>Fuzzy（本方法）</strong></p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p></p></td>
</tr>
<tr>
<td><p><strong>Oracle</strong></p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p></p></td>
</tr>
</tbody>
</table>

### 11.3&#32;&#32;门控选题质量与消融

<em>表 11-3&#32;&#32;门控决策指标（空白表；正类定义见第 6.2 节）与优先消融</em>

<table>
<thead>
<tr>
<th><p>设定</p></th>
<th><p>答案 F1</p></th>
<th><p>再检索率</p></th>
<th><p>门控 P</p></th>
<th><p>门控 R</p></th>
<th><p>门控 F1</p></th>
<th><p>备注</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>NLI threshold</strong></p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p></p></td>
</tr>
<tr>
<td><p><strong>同输入硬规则</strong></p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p></p></td>
</tr>
<tr>
<td><p><strong>Fuzzy（完整）</strong></p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p></p></td>
</tr>
<tr>
<td><p><strong>Fuzzy w/o NLI</strong></p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p></p></td>
</tr>
<tr>
<td><p><strong>Fuzzy w/o bridge-entity</strong></p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p></p></td>
</tr>
<tr>
<td><p><strong>其他：____</strong></p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p>—</p></td>
<td><p></p></td>
</tr>
</tbody>
</table>

### 11.4&#32;&#32;预实验读出表

<em>表 11-4&#32;&#32;预实验三项读出与 go / no-go（空白表，供内部记录）</em>

<table>
<thead>
<tr>
<th><p>读出</p></th>
<th><p>口径</p></th>
<th><p>结果（预实验后填）</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>支持事实覆盖是否随再检索提高</strong></p></td>
<td><p>【待确认：Supp-F1 或其他覆盖率】</p></td>
<td><p>—</p></td>
</tr>
<tr>
<td><p><strong>improved / tie / degraded</strong></p></td>
<td><p>官方答案 ΔF1</p></td>
<td><p>— / — / —</p></td>
</tr>
<tr>
<td><p><strong>Oracle 相对 Never 的 F1 增益</strong></p></td>
<td><p>逐题选优后的平均 F1 差</p></td>
<td><p>—</p></td>
</tr>
<tr>
<td><p><strong>go / no-go 结论</strong></p></td>
<td><p>第 7.3 节预填阈值</p></td>
<td><p></p></td>
</tr>
</tbody>
</table>

### 11.5&#32;&#32;质量–成本图（只约定格式，不预绘数据）

<table>
<thead>
<tr>
<th><p>项目</p></th>
<th><p>约定 / 填写</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>横轴</strong></p></td>
<td><p>☐ 再检索率    ☐ 端到端延迟    ☐ token    ☐ 其他：____</p></td>
</tr>
<tr>
<td><p><strong>纵轴</strong></p></td>
<td><p>☐ 答案 F1    ☐ 其他：____</p></td>
</tr>
<tr>
<td><p><strong>必标出的点</strong></p></td>
<td><p>Never、Always、NLI 阈值、同输入硬规则、Fuzzy、Full-context；Oracle 可用参照线或单独标记。</p></td>
</tr>
<tr>
<td><p><strong>误差表示</strong></p></td>
<td><p>☐ 配对差异的置信区间    ☐ 不绘制    ☐ 其他：____</p></td>
</tr>
<tr>
<td><p><strong>若 Full-context 更优或成本更低</strong></p></td>
<td><p>如实绘制并在正文讨论；作为小池上门控实用价值的限定。</p></td>
</tr>
<tr>
<td><p><strong>文件路径</strong></p></td>
<td><p>【待确认】</p></td>
</tr>
</tbody>
</table>

## 12&#32;&#32;统计检验与分析

主推断采用逐题配对设计：同一题在不同策略（或不同分支）下的官方指标之差。优先报告配对 bootstrap 置信区间。

☐&#32;&#32;对主要逐题差异（如 Fuzzy − 同输入硬规则、Fuzzy − Never、Oracle − Never 的答案 F1）做配对 bootstrap。重复次数 B = 【待确认】；置信水平：【待确认】。

☐&#32;&#32;必要时补充配对检验：☐ McNemar&#32;&#32;&#32;&#32;☐ Wilcoxon signed-rank&#32;&#32;&#32;&#32;☐ 配对 t&#32;&#32;&#32;&#32;☐ 其他：\_\_\_\_

☐&#32;&#32;多重比较校正：☐ 不校正&#32;&#32;&#32;&#32;☐ Bonferroni&#32;&#32;&#32;&#32;☐ Holm&#32;&#32;&#32;&#32;☐ FDR&#32;&#32;&#32;&#32;☐ 其他：\_\_\_\_

<strong>预先计划的主要两两比较：</strong>&#32;&#32;Fuzzy vs 同输入硬规则；Fuzzy vs NLI threshold；Fuzzy vs Never；Oracle vs Never；Full-context vs Fuzzy。其他：\_\_\_\_

<strong>显著性水平 α：</strong>&#32;&#32;【待确认】

### 12.2&#32;&#32;错误分析类别（预留，待观察后命名）

建议覆盖：漏掉的 improved 题、误触发的 degraded 题，以及第 3.3 节三类 NLI 抽查情形。类别名称在见到数据前不预设结论。

<table>
<thead>
<tr>
<th><p>编号</p></th>
<th><p>类别（待命名）</p></th>
<th><p>定义（待写）</p></th>
<th><p>例题 ID（实验后填）</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>E1</strong></p></td>
<td><p>【待确认：类别名称】</p></td>
<td><p>【待确认：定义】</p></td>
<td><p></p></td>
</tr>
<tr>
<td><p><strong>E2</strong></p></td>
<td><p>【待确认：类别名称】</p></td>
<td><p>【待确认：定义】</p></td>
<td><p></p></td>
</tr>
<tr>
<td><p><strong>E3</strong></p></td>
<td><p>【待确认：类别名称】</p></td>
<td><p>【待确认：定义】</p></td>
<td><p></p></td>
</tr>
<tr>
<td><p><strong>E4</strong></p></td>
<td><p>【待确认：类别名称】</p></td>
<td><p>【待确认：定义】</p></td>
<td><p></p></td>
</tr>
<tr>
<td><p><strong>其他</strong></p></td>
<td><p>________________</p></td>
<td><p>________________</p></td>
<td><p></p></td>
</tr>
</tbody>
</table>

<strong>错误分析抽样方式与样本量：</strong>&#32;&#32;【待确认】

## 13&#32;&#32;时间线

下表只列里程碑与截止时间，不指派人员。时间均按 Asia/Shanghai（北京时间）填写。除已公布的阶段性综述截止外，其余日期待填。

<table>
<thead>
<tr>
<th><p>编号</p></th>
<th><p>里程碑</p></th>
<th><p>说明</p></th>
<th><p>截止日期</p></th>
<th><p>状态</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>T0</strong></p></td>
<td><p>阶段性文献综述提交（iSpace）</p></td>
<td><p>参考文献不少于 10 篇，查重相似度低于 20%。</p></td>
<td><p>2026-11-13 23:00（已确定）</p></td>
<td><p></p></td>
</tr>
<tr>
<td><p><strong>T1</strong></p></td>
<td><p>预实验准备与执行</p></td>
<td><p>按第 7 节接入真实模型，缓存双分支，完成三项读出与 NLI 抽查。</p></td>
<td><p>【待确认】</p></td>
<td><p></p></td>
</tr>
<tr>
<td><p><strong>T2</strong></p></td>
<td><p>go / no-go 与方案锁定</p></td>
<td><p>按预填阈值决定是否进入主实验；锁定门控参数、目标再检索率、正式样本量与划分。</p></td>
<td><p>【待确认】</p></td>
<td><p></p></td>
</tr>
<tr>
<td><p><strong>T3</strong></p></td>
<td><p>正式样本双分支缓存与主实验</p></td>
<td><p>离线评价六种策略及优先消融；测量 Full-context 与真实路径延迟。</p></td>
<td><p>【待确认】</p></td>
<td><p></p></td>
</tr>
<tr>
<td><p><strong>T4</strong></p></td>
<td><p>撰写 Methodology（第 3 章）</p></td>
<td><p>方案锁定后即可开始，不必等待全部主结果。</p></td>
<td><p>【待确认】</p></td>
<td><p></p></td>
</tr>
<tr>
<td><p><strong>T5</strong></p></td>
<td><p>撰写 Implementation &amp; Experimental Results（第 4 章）</p></td>
<td><p>主表、消融、区间估计与图表完成后再写分析。</p></td>
<td><p>【待确认】</p></td>
<td><p></p></td>
</tr>
<tr>
<td><p><strong>T6</strong></p></td>
<td><p>全文统稿与 IEEE 排版</p></td>
<td><p>引言、结论、参考文献；10–12 页，10pt 双栏单倍行距。</p></td>
<td><p>【待确认】</p></td>
<td><p></p></td>
</tr>
<tr>
<td><p><strong>T7</strong></p></td>
<td><p>其他：____</p></td>
<td><p>________________</p></td>
<td><p>【待确认】</p></td>
<td><p></p></td>
</tr>
</tbody>
</table>

<strong>学期论文最终提交时间（若已公布）：</strong>&#32;&#32;【待确认】

## 14&#32;&#32;风险与备选

<table>
<thead>
<tr>
<th><p>风险</p></th>
<th><p>可能影响</p></th>
<th><p>备选（请勾选或填写）</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>小候选池上成本未必下降</strong></p></td>
<td><p>distractor 每题仅 10 个候选段落，省一次池内取证的收益可能很小，NLI 与改写还会增加开销。Full-context 可能在质量相近时更快。</p></td>
<td><p>如实报告质量、token 与延迟。若成本优势弱，论文以门控选题准确率与质量增益为主要论述，成本作次要结果。☐ 同意这一写作预案</p></td>
</tr>
<tr>
<td><p><strong>再检索可争取空间不足</strong></p></td>
<td><p>若 Oracle 相对 Never 的增益很小，比较门控的意义有限。</p></td>
<td><p>按第 7.3 节先改进第二轮检索或再作答，再重做预实验。☐ 采用该规则</p></td>
</tr>
<tr>
<td><p><strong>NLI 跨段落误判</strong></p></td>
<td><p>逐句 max / min 都会偏；即便改为拼接引用，仍可能在缺跳、错引或两段共同支持时出错。</p></td>
<td><p>按第 3.3 节构造第一版 premise / hypothesis，并做三类人工抽查；错误过多则先改构造。</p></td>
</tr>
<tr>
<td><p><strong>API 成本或限流</strong></p></td>
<td><p>每题需生成两支答案，预实验与正式样本都会消耗调用次数。</p></td>
<td><p>☐ 按第 7.4 节用预算约束样本量<br />☐ 加强分支缓存，避免重复生成<br />☐ 其他：____</p></td>
</tr>
<tr>
<td><p><strong>GPU / 本地算力</strong></p></td>
<td><p>真实 NLI 或本地作答模型可能受显存限制。</p></td>
<td><p>☐ 选用更小的 NLI<br />☐ 作答改走 API<br />☐ 其他：____</p></td>
</tr>
<tr>
<td><p><strong>时间风险</strong></p></td>
<td><p>阶段性综述截止于 2026-11-13 23:00（北京时间）之后，预实验、方案锁定与主实验仍需排期。</p></td>
<td><p>☐ 先完成最小预实验再决定主实验规模<br />☐ 其他：____</p></td>
</tr>
<tr>
<td><p><strong>其他：____</strong></p></td>
<td><p>【待确认】</p></td>
<td><p>【待确认】</p></td>
</tr>
</tbody>
</table>

## 15&#32;&#32;待确认事项清单

请在预实验前后分两次复核：先确认第 7 节阈值与最小设置已经预填，再在 go / no-go 之后确认正式方案已锁定。清单不含人员或签名项。

<table>
<thead>
<tr>
<th><p>确认</p></th>
<th><p>编号</p></th>
<th><p>类别</p></th>
<th><p>事项</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p>☐</p></td>
<td><p>C01</p></td>
<td><p>核心问题与状态</p></td>
<td><p>第 0.2 节核心问题表述已确认；方案状态仍理解为「通过预实验，正式方案待锁定」，直到 T2 完成。</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>C02</p></td>
<td><p></p></td>
<td><p>预期贡献草稿无需再改，或已记下改写。</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>C03</p></td>
<td><p>研究问题</p></td>
<td><p>RQ1–RQ3 已定稿；主实验优先 RQ1 与 RQ2 的安排已同意；α 已勾选。</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>C04</p></td>
<td><p>数据与样本</p></td>
<td><p>数据来源已选定；官方评测脚本已确定使用 hotpot_evaluate_v1.py。</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>C05</p></td>
<td><p></p></td>
<td><p>预实验题型（bridge 为主）及 comparison 题是否排除，已决定并将在论文中声明。</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>C06</p></td>
<td><p></p></td>
<td><p>预实验确切题数（50–100 范围内）已填写；正式划分、互斥规则与样本量的确定方法已同意。</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>C07</p></td>
<td><p>系统组件与 NLI 构造</p></td>
<td><p>预实验的真实作答模型、真实 NLI、池内 BM25、固定第一轮 top-k、第二轮规则改写已圈定。</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>C08</p></td>
<td><p></p></td>
<td><p>第一版 premise（按固定顺序拼接有效引用）与 hypothesis（问题+短答案改为可判定陈述）已确认；三类人工抽查计划已有样本量。</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>C09</p></td>
<td><p>双分支与标签</p></td>
<td><p>同意对每道评估题都缓存分支 A 与分支 B，而不是只在触发时再检索。</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>C10</p></td>
<td><p></p></td>
<td><p>ΔF1 定义、tie 容差、门控正类操作化定义、Oracle 持平时的选取规则已填写。</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>C11</p></td>
<td><p>门控对齐</p></td>
<td><p>Fuzzy 与同输入硬规则的输入集合、共享分支与再作答模型已确认；目标再检索率已预填，并将只在 dev 上调参后锁定。</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>C12</p></td>
<td><p></p></td>
<td><p>模型不确定性的接口与度量：☐ 暂缓    ☐ 已确认并同时加入二者。</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>C13</p></td>
<td><p>预实验 go / no-go</p></td>
<td><p>第 7.3 节的「增益较小 / 足够清楚」等阈值已在查看汇总前填写。</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>C14</p></td>
<td><p></p></td>
<td><p>预实验结束后的综合决定已勾选，正式方案版本已准备锁定或已决定返工。</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>C15</p></td>
<td><p>主实验报告口径</p></td>
<td><p>首要指标为答案 F1、再检索率、端到端成本；次要为 EM、官方 supporting-fact F1、配对差异置信区间。</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>C16</p></td>
<td><p></p></td>
<td><p>结果表将包含 improved / tie / degraded、Oracle 行、再检索率，以及同输入硬规则行。</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>C17</p></td>
<td><p></p></td>
<td><p>延迟在真实路径上另测；若 Full-context 质量相近且更快，将如实报告，并可采用「质量与选题为主、成本为次」的写作预案。</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>C18</p></td>
<td><p>可复现性与时间</p></td>
<td><p>种子、缓存、代码版本与日志目录已定；第 13 节截止日期已尽量补全。</p></td>
</tr>
<tr>
<td><p>☐</p></td>
<td><p>C19</p></td>
<td><p>版本锁定</p></td>
<td><p>已确认方案的文件名 / 版本号与锁定日期：【待确认】。</p></td>
</tr>
</tbody>
</table>

<strong>确认栏</strong>

本栏只记录方案版本与日期，不设人员签名。

<table>
<thead>
<tr>
<th><p>项目</p></th>
<th><p>填写</p></th>
</tr>
</thead>
<tbody>
<tr>
<td><p><strong>方案版本号</strong></p></td>
<td><p>【待确认】</p></td>
</tr>
<tr>
<td><p><strong>确认或锁定日期（Asia/Shanghai）</strong></p></td>
<td><p>【待确认】</p></td>
</tr>
<tr>
<td><p><strong>当前状态</strong></p></td>
<td><p>☐ 仍待预实验    ☐ 预实验结束、方案已锁定    ☐ 预实验未通过、需返工</p></td>
</tr>
<tr>
<td><p><strong>仍未关闭的事项（如有）</strong></p></td>
<td><p>【待确认】</p></td>
</tr>
<tr>
<td><p><strong>下一步</strong></p></td>
<td><p>☐ 开始预实验    ☐ 按 go / no-go 返工    ☐ 进入主实验    ☐ 其他：____</p></td>
</tr>
</tbody>
</table>

<em>— 模板 v2 结束 —</em>

请勿在相应实验完成前向第 11 节表格填入任何数字。本文不构成已完成的实验报告。

<!-- header1.xml -->

<blockquote><p><strong>实验方案模板 v2（正式方案待锁定）</strong><em>    A Fuzzy-NLI-based QA Chatbot System with Adaptive Retrieval</em></p></blockquote>

<!-- footer1.xml -->

<blockquote><p>本文为模板 v2，不含实验结果。正式方案待预实验后锁定。        第 <!-- Word field: PAGE --> 页 / 共 <!-- Word field: NUMPAGES --> 页</p></blockquote>

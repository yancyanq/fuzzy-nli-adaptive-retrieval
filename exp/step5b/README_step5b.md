# 第 5b 步：带 top_logprobs 重跑 100 题预实验，评估「候选差值」不确定度信号

**为什么要做这一步。** 第 5 步的 logprob 全是 0。探测（`probe_logprobs.py`）证实：`deepseek-chat` 在 temperature 0 时，把**被选中 token** 的 logprob 一律报成 0.0，但 `top_logprobs` 里的候选 token 有非零值。按[做法 1 的决定](../EXPERIMENT_LOG.md?plain=1#L199)，这一步用相同的提示词和检索（k=2、m=1、temperature 0、max_tokens 128）把 100 题 × 2 个分支重跑一遍，加上 `logprobs=True` 和 `top_logprobs=5`，再用候选 token 计算不确定度。

**预先登记的定义（看到结果之前就已写定，不改）：**

- 每个输出 token 的 **margin** = 第一名候选的 logprob − 第二名候选的 logprob（候选按 logprob 从高到低排序；不足 2 个候选时记为缺失）。margin 越小，说明模型在前两名之间越犹豫。
- **主指标**：分支 A 答案片段上各 token margin 的平均值（`mean_margin_A`）。找不到答案片段时退回用全部输出 token，并统计退回次数。
- **次要指标**（只作描述）：答案片段上的最小 margin（`min_margin_A`）、答案第一个 token 的 margin（`first_margin_A`）、把返回的候选重新归一化后算出的平均熵（`mean_entropy_A`）。
- **方向**：margin 越低、熵越高，越可能是「补查后改善」的题。
- **标签**：沿用第 5 步 `per_question.csv` 里的 `delta_class`（improved / tie / degraded），不用重跑出来的答案重新打标签，第 5 步的 GO 结论也不重新判定。
- **AUC**：只比较改善题和持平题，bootstrap 95% 置信区间（B=5000，种子 42），函数直接复用 `analyze_signals.py`。
- **主分析子集**：A、B 两个分支的新答案都和第 5 步一致的题；**敏感性分析**：全部题。
- **公平对比**：在**同一批题**上也计算第 5 步 NLI 蕴含概率（`nli_entailment_A`）的 AUC。
- 只做描述，**不选任何门控阈值**。门控仍在 tune 集上调。

> 本目录下的测试只用 mock 服务器和合成的 `per_question.csv`，其中的所有数字都是**假的**（由哈希生成），**不是**实验结果。

## 1. 需要哪些文件

把 `rerun_toplogprobs.py` 复制到 `G:\NLP_project\`。同一文件夹里应该已经有：

- `pilot.json`、`compare_models.py`、`bm25_topk.py`（提示词、检索、解析、打分都从 `compare_models.py` 导入，和第 3、5 步完全一致）；
- `analyze_signals.py`（AUC 和 bootstrap 函数从这里导入）；
- `step5_pilot\per_question.csv`（第 5 步的结果，用来读标签、旧答案和 NLI 分数）。

依赖和第 3 步相同，不需要 torch：

```bat
pip install openai rank_bm25
```

## 2. 设置 API Key（不要写进命令行，也不要发到聊天里）

脚本只从环境变量读密钥，终端只会显示 `DEEPSEEK_API_KEY=set` 或 `MISSING`，不会显示密钥本身。

**cmd（只对当前窗口有效）：**

```bat
set DEEPSEEK_API_KEY=这里填你的key
```

**PowerShell（只对当前窗口有效）：**

```powershell
$env:DEEPSEEK_API_KEY = "这里填你的key"
```

检查是否设置成功（只显示 set / MISSING）：

```bat
python -c "import os; print('DEEPSEEK_API_KEY=' + ('set' if os.environ.get('DEEPSEEK_API_KEY') else 'MISSING'))"
```

## 3. 运行

**cmd：**

```bat
cd /d G:\NLP_project
python rerun_toplogprobs.py --data pilot.json --step5-dir step5_pilot --out step5b_toplp
```

**PowerShell：**

```powershell
Set-Location G:\NLP_project
python rerun_toplogprobs.py --data pilot.json --step5-dir step5_pilot --out step5b_toplp
```

默认值已经是锁定的设置：`--preset deepseek`（deepseek-chat）、`--n 100`、`--k 2`、`--m 1`、`--temperature 0`、`--max-tokens 128`、`--top-logprobs 5`。

**会发多少次请求。** 这一步会**新发 200 次调用**（100 题 × A、B 两个分支），不会复用第 5 步的缓存（第 5 步的缓存里没有候选 token）。提示词和第 5 步相同，所以 token 用量应和第 5 步作答阶段的量级相近；按第 3 步「60 次约 2.7 万 token」粗略推算，200 次大约 9 万 token。这里不给价格，单价请到 DeepSeek 官网查当前价格。想让脚本估算费用，可以加上 `--price-in 单价 --price-out 单价`（单位是每 100 万 token 的美元）。

**中断后续跑。** 每次调用完成就立即写入 `step5b_toplp\cache_toplp.jsonl`。中途断网或关掉窗口，重新执行同一条命令即可：已完成的调用直接从缓存读取，出错的调用会重试。遇到限流可以加 `--sleep 0.5`。

**只重新分析、不调用 API：**

```bat
python rerun_toplogprobs.py --data pilot.json --step5-dir step5_pilot --out step5b_toplp --analyze-only
```

（`--skip-api` 与 `--analyze-only` 等价。）

**第 5 步的文件不会被改动。** 新缓存是单独的 `cache_toplp.jsonl`，按 `(model, _id, branch, top_logprobs)` 区分。如果用 `--cache` 指向任何名为 `cache.jsonl` 的文件（例如 `step5_pilot\cache.jsonl`），脚本会拒绝运行。

## 4. 输出文件

都在 `G:\NLP_project\step5b_toplp\` 下：

| 文件 | 内容 |
|---|---|
| `per_question_toplp.csv` | 逐题：第 5 步标签、A/B 新答案、新 F1/EM、各项 margin 和熵、答案片段 token 数、是否退回全部 token、margin 缺失数、「选中 token ≠ 第一名候选」次数、第一名候选恰好为 0.0 的次数、token 用量。 |
| `consistency.csv` | 每个（题，分支）新旧答案对比。答案变了的行标为 `CHANGED`，排在最前面。 |
| `toplp_summary.json` | 汇总：调用次数、缓存命中、token 数、每个分支变了几题（及题号）、退回次数、各项计数、两个子集上所有信号的 AUC 和置信区间、方法说明。 |
| `cache_toplp.jsonl` | 本步自己的 API 缓存。每个 token 只存 token、logprob 和 5 个候选（保留 6 位小数），文件不大。 |

## 5. 怎么读终端表格

运行结束会打印两张小表，格式如下（下面的数字是占位，不是结果）：

```
PRIMARY subset: A and B answers unchanged vs Step 5   n=xx (improved xx, tie xx, degraded x not in AUC)
  signal (branch A)    role                        imp mean  tie mean     AUC  95% CI (B=5000)   n_imp/n_tie
  mean_margin_A        PRIMARY                        x.xxx     x.xxx   0.xxx  [0.xxx, 0.xxx]        xx/xx
  min_margin_A         secondary                      ...
  first_margin_A       secondary                      ...
  mean_entropy_A       secondary                      ...
  nli_entailment_A     comparison (Step 5 NLI)        ...
SENSITIVITY: all questions   ...
```

- **预先登记的主结果只有一个**：PRIMARY 子集里的 `mean_margin_A` 那一行。其余各行都是次要或描述性的。
- **AUC**：0.5 表示和随机一样；高于 0.5 表示「margin 越小（或熵越高、NLI 越低），越可能是改善题」，也就是门控能利用的方向。低于 0.5 表示方向相反。
- **置信区间**：下界高于 0.5，才能说这个信号在本批数据上有区分力。改善题只有 16 道左右，区间会比较宽。
- **和 NLI 对比**：`nli_entailment_A` 这一行和 margin 用的是同一批题，所以两者可以直接比较。它和第 5 步诊断时的 0.699 可能略有出入，因为主子集去掉了答案变化的题。
- `imp mean` / `tie mean` 是原始值（不翻转符号）的组均值。degraded 题只计数，不参与 AUC。

表格上方还有几行计数：

- **changed answers vs Step 5**：新答案和第 5 步答案（按 HotpotQA 规范化：小写、去标点、去冠词）不同的题数，分 A、B 统计，并逐条列出。
- **span fallback**：没在输出里找到答案片段、改用全部 token 的次数。
- **chosen!=top1**：被选中的 token 不是第一名候选的次数。temperature 0 下理论上应接近 0。
- **top1 alt == 0.0**：第一名候选的 logprob 恰好报成 0.0 的 token 数（见第 7 节）。

## 6. 答案变了是什么意思

temperature 0 加上相同的提示词，理论上应得到同样的答案，但 API 端并不保证完全可复现，加上 `top_logprobs` 也可能有细微影响。所以：

- **变了的题不进入主分析子集。** 这些题的标签来自第 5 步的旧答案，而 margin 来自新答案，两者对不上。
- **全部题的结果作为敏感性分析。** 如果两个子集的结论一致，说明答案变化没有影响结论。
- **不会用新答案重新判 GO / NO-GO。** 新 F1 只用来描述变化幅度（`consistency.csv` 里的 `F1_diff_new_minus_step5`）。
- 如果变了的题很多（比如超过十几题），主子集会变小、置信区间变宽，这一点要在论文里如实写明。

## 7. 需要在论文里说明的局限

- margin 是因为 API 在 temperature 0 时把选中 token 的 logprob 报成 0 而**改用的替代量**，和主实验本地 vLLM 模型直接给出的选中 token logprob **不是同一个量**。
- DeepSeek 的 logprob 分布不能迁移到主实验模型；这里的结果只能说明「这类信号是否有用」，不能直接作为门控输入。
- 探测中，temperature 0 时每个输出 token 的 5 个候选里有 1 个是 0.0（另外 4 个非零），这个 0.0 很可能就是被选中的 token，但探测没有直接核对。这时 margin 等于「0 − 第二名候选的 logprob」，归一化熵也会把第一名当作概率 1 来算。定义按预先登记的保留不改；脚本会统计这种情况出现了多少次（`top1_alternative_logprob_exactly_zero_tokens`），论文里要说明。
- 不在 pilot 上选任何门控阈值。

## 8. 本机测试（mock，数字是假的）

```bash
python3 test_step5b.py
```

测试内容包括：margin 和熵在已知数字上的计算、答案片段定位与 `compare_models` 规则一致、AUC 方向、新旧答案一致性判断、缓存隔离（不会改动第 5 步的 `cache.jsonl`）、断点续跑、`--analyze-only` 路径，以及对 mock 服务器（`test_mock_server.py --top-logprobs-mode deepseek_t0`：选中 token 报 0.0，其余候选非零，模仿 deepseek temperature 0）用 `testdata/mini_pilot.json` 前 4 题和一份**合成的** `per_question.csv` 做端到端运行。这些数字都**不是**实验结果。

跑完后，把终端里的两张表和计数行，或者 `step5b_toplp\toplp_summary.json` 发给我。

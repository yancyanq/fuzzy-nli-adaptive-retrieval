# 第 5 步：100 题预实验（作答 + 本地 NLI + 去留判断）

在完整的 `pilot.json`（100 道 bridge 题）上，用已锁定的检索设置（k=2、m=1）和作答模型 `deepseek-chat` 跑两个缓存分支，再用本地 DeBERTa 做 NLI 打分，并按第 4 步预先登记的标准给出 GO / NO-GO。

- **分支 A（首轮）**：只用 BM25 取出的前 k 段作答。
- **分支 B（补查后）**：用前 k 段，再加上规则改写查询后补的 m 段作答。
- **Oracle**：每题在事后取较好的那一支；F1 持平时选 A（不补查）。
- **NLI**：前提是按引用顺序拼接的被引段落（没有可用引用时，退回该分支检索到的段落，并在结果里标记）；假设句用固定模板，不用另一个大模型改写：

  `The answer to the question "{question}" is: {answer}.`

把 `run_pilot.py` 放到项目工作目录，和 `pilot.json`、`compare_models.py`、`bm25_topk.py` 放在同一文件夹（`compare_models.py` 会调用 `bm25_topk.py` 的分词，保证和第 2、3 步一致）。第 3 步的缓存可以直接复用，不必重跑前 30 题。

> 本目录里的 `testdata/mini_pilot.json` 只是 `pilot.json` 的前 4 题切片，供本机 mock 测试用。下面第 8 节的 mock 数字**不是**实验结果。

## 1. 安装依赖

作答阶段（和第 3 步相同）：

```bat
pip install openai rank_bm25
```

NLI 阶段还需要 PyTorch 和 Transformers。在带 CUDA 的 GPU 上，请安装带 CUDA 的 torch（到 https://pytorch.org 按提示选择），然后：

```bat
pip install transformers
python -c "import torch; print(torch.cuda.is_available())"
```

若打印 `False`，NLI 会落到 CPU（能跑但很慢）。可用 `--nli-device cuda` 强制检查。

**不要**在本机测试时下载 `DeBERTa-v3-large`。本机验证请用 `--nli-backend mock`（分数是假的）。

## 2. 设置 API Key（不要把 key 写进命令行，也不要发到聊天里）

脚本只从环境变量读取密钥，运行时只会打印变量名是否已设置（`DEEPSEEK_API_KEY=set`），不会打印密钥本身。

**cmd（仅当前窗口有效）：**

```bat
set DEEPSEEK_API_KEY=这里填你的key
```

**PowerShell（仅当前窗口有效）：**

```powershell
$env:DEEPSEEK_API_KEY = "这里填你的key"
```

**想长期保存（新开的窗口才生效，当前窗口还要用上面的命令再设一次）：**

```bat
setx DEEPSEEK_API_KEY "这里填你的key"
```

检查是否已设置（不要用 `echo %DEEPSEEK_API_KEY%` 把密钥打到屏幕上）：

```bat
echo %DEEPSEEK_API_KEY:~0,3%
```

PowerShell：

```powershell
if ($env:DEEPSEEK_API_KEY) { "DEEPSEEK_API_KEY=set" } else { "DEEPSEEK_API_KEY=MISSING" }
```

## 3. 进入目录

**cmd：**

```bat
cd /d <项目目录>
```

**PowerShell：**

```powershell
Set-Location <项目目录>
```

建议分成两段跑：先补全 100 题的作答（复用第 3 步缓存），再在 4060 上跑 NLI。这样 API 和本地推理可以分开，中途失败也不必重计费。

### （a）补全作答：复用第 3 步前 30 题的 60 次调用

第 3 步的缓存默认在 `step3_deepseek\cache.jsonl`。用 `--answer-cache` 读它，新的调用写到 `step5_pilot\cache.jsonl`。前 30 题命中缓存，只会对剩下 70 题 × 2 个分支发新请求。

**cmd：**

```bat
python run_pilot.py --data pilot.json --preset deepseek --n 100 --out step5_pilot --answer-cache step3_deepseek\cache.jsonl --skip-nli
```

**PowerShell：** 命令相同。

可选：加上单价后会估算本次和外推到 1600 题（每题两个分支）的费用。单价请到 DeepSeek 官网查看当前价格，单位是「每 100 万 token 的美元」，不要沿用过期数字。

```bat
python run_pilot.py --data pilot.json --preset deepseek --n 100 --out step5_pilot --answer-cache step3_deepseek\cache.jsonl --skip-nli --price-in 0.28 --price-out 0.42
```

（上面的 `0.28` / `0.42` 只是命令格式示例，不是报价。）

`--skip-nli` 时仍然会计算答案质量的 GO / NO-GO，并注明本次没有跑 NLI。

### （b）在 4060 上跑本地 NLI

作答都写进 `step5_pilot\` 之后，不再访问 API，只读已有答案并打分：

**cmd：**

```bat
python run_pilot.py --data pilot.json --preset deepseek --n 100 --out step5_pilot --nli-only --nli-backend hf --nli-device auto
```

**PowerShell：** 命令相同。

显存紧张时把 `--nli-batch-size` 改成 `1` 或 `2`（默认 4）。输入最长 512 token，脚本会统计被截断的条数。

如果希望作答和 NLI 一次跑完（4060 在线、密钥已设置），去掉 `--skip-nli` / `--nli-only` 即可：

```bat
python run_pilot.py --data pilot.json --preset deepseek --n 100 --out step5_pilot --answer-cache step3_deepseek\cache.jsonl --nli-backend hf
```

## 4. 输出文件在哪里

默认写到 `--out` 指定的文件夹（例如 `step5_pilot\`）：

| 文件 | 内容 |
|---|---|
| `per_question.csv` | 逐题结果：答案、F1 / EM、ΔF1 分类、Oracle、检索与引用覆盖、NLI 概率与截断标记。用 Excel 打开即可（UTF-8 with BOM）。 |
| `branches.jsonl` | 两个分支的完整记录（检索段落、解析结果、覆盖率、NLI 摘要）。 |
| `nli_scores.jsonl` | 每个（题，分支）的前提、假设句、三类概率、argmax、是否截断、是否退回检索段落。 |
| `summary.json` | 汇总数字，和终端表格、GO / NO-GO 一致。 |
| `audit_sample.csv` | 至多 20 条分层抽样，覆盖三类 NLI 差错，供人工检查。`human_label` 列为空，留给人工填写。 |
| `cache.jsonl` | 作答 API 缓存。按 `(model, _id, branch)` 去重；从 `--answer-cache` 命中的条目也会抄进来，使本目录自洽。 |

如果改了 `--k`、`--m` 或提示词，请删除对应的 `cache.jsonl` 后再跑，否则会读到旧答案。改 NLI 设置只需重跑 `--nli-only`，不必重调 API。

## 5. 怎么读终端表格和 GO / NO-GO

运行结束会打印答案质量表，以及一张去留判断表，例如：

```
Go / no-go (pre-registered criteria; not tuned on these results)
----------------------------------------------------------------------------------------
criterion                                    observed       threshold   result
headroom point (mean Oracle F1 - A F1)          0.xxx         >= 0.05     PASS
headroom 95% CI lower bound                     0.xxx             > 0     PASS
improved share                           12/100 = 12.0%          >= 10%     PASS
degraded / improved                       3/12 = 0.250          <= 0.5     PASS
----------------------------------------------------------------------------------------
OVERALL                                                    GO
```

三条标准（第 4 步已锁定，其中第 4、5、6 项是预先登记的主观阈值）必须全部通过才是总体 GO：

1. **Headroom**：`mean(Oracle F1 − A F1)` 的点估计 ≥ 0.05，且配对 bootstrap 95% 置信区间下界 > 0（默认 B=10000，种子 42）。
2. **Improved share**：F1_B > F1_A 的题数占比 ≥ 10%。
3. **Degraded ratio**：F1 下降的题数不超过上升题数的一半。

持平容差 ε 默认为 0：F1 必须严格更高才算 improved。Oracle 在持平时选 A。

其他数字的含义与第 3 步类似，并增加：

- **retrieval recall / both-gold**：与第 2 步相同。gold = `supporting_facts` 中出现过的不重复标题。A 看首轮 k 段，B 看首轮 + 补查。
- **citation recall / all-gold**：模型引用的标题里，命中了多少黄金标题。
- **official sentence-level SP F1**：当前提示只要求段落编号，没有句子下标，因此这项为 null，并在 `summary.json` 里说明。
- **NLI truncated / fallback**：被截断的输入条数；因没有可用引用而改用检索段落的条数。
- **cache hits / new API calls**：命中缓存的次数和新发起的调用次数。

## 6. 人工抽查 `audit_sample.csv`

自动打分后，脚本按种子 42 分层抽出至多 20 条（题，分支），三类目标大约各 6–7 条（7 / 7 / 6）：

- **(a) false_entailment**：NLI 判为 entailment，但答案错误（F1 = 0）或引用未命中任何黄金标题。
- **(b) false_non_entailment**：NLI 不是 entailment，但答案较强（EM = 1 或 F1 ≥ 0.5），且至少一个黄金标题出现在引用或检索段落中。
- **(c) truncated_or_disagreement**：被截断的输入，或其余「NLI 是否 entailment」与「前提段落是否覆盖黄金标题」不一致、且尚未归入 (a)(b) 的情况。一条记录只归入一类，优先级 a > b > c。

某类不足配额时，能抽几条就抽几条，并在 `summary.json` 的 `audit.shortfalls` 和 CSV 的 `shortfall_note` 里写明缺口。抽查是定性分析，不是差错率点估计。`human_label` 请留到人工阅读后再填。

## 7. 常用可选参数

```bat
python run_pilot.py --data pilot.json --preset deepseek --n 100 --out step5_pilot --answer-cache step3_deepseek\cache.jsonl --tie-eps 0.0 --sleep 0.2
```

- `--n`：取文件开头的 N 道题，默认 100。
- `--k` / `--m`：默认 2 和 1，应与已锁定的检索设置一致。
- `--temperature`：默认 0。
- `--max-tokens`：默认 128。
- `--tie-eps`：F1 持平容差，默认 0。
- `--sleep`：两次新的 API 调用之间的间隔（秒），遇到限流可以加大。
- `--no-cache`：不读写 `--out` 下的缓存；若同时给了 `--answer-cache`，仍会读取它。
- `--nli-backend {hf,mock}`：默认 `hf`。`mock` 只用于测试，分数是假的。
- `--nli-device {auto,cuda,cpu}`：默认 `auto`（有 CUDA 用 GPU，否则 CPU 并给出警告）。
- `--nli-batch-size`：默认 4。
- `--nli-max-length`：默认 512。
- `--skip-nli` / `--nli-only`：只作答，或只打 NLI。
- `--min-headroom` / `--min-improved-share` / `--max-degraded-ratio`：默认 0.05 / 0.10 / 0.5，与第 4 步锁定值一致；一般不要改。
- `--bootstrap-samples` / `--bootstrap-seed`：默认 10000 / 42。

## 8. 本机 mock 测试（数字不是实验结果）

在本仓库的 Linux 测试机上不要下载 DeBERTa，也不要调用真实 API。测试命令：

```bash
python /workspace/exp/step5/test_step5.py
```

测试包括：用已知 F1 做分类 / Oracle / bootstrap / GO 与 NO-GO 的单元测试；以及用第 3 步的 mock 聊天服务和 `--nli-backend mock` 做 4+1 题的端到端检查（缓存复用、`--skip-nli`、`--nli-only`、截断计数、抽查表）。这些分数全部是假的，不得写入论文或当作预实验结论。

## 9. 注意

- 必须使用种子 42 切出的那份 `pilot.json`（第 1 步）。
- 官方答案评分与 HotpotQA 的 `hotpot_evaluate_v1.py` 一致（小写、去标点、去冠词、yes/no/noanswer 特例）。
- NLI 的三类概率来自对 checkpoint 的 `id2label` 做 softmax，不假定 label 的下标顺序。加载模型时会把原始映射打印到 stderr。
- 遇到限流会自动退避重试；密钥只放在环境变量里，不要写进脚本、不要提交到 git、不要发到聊天。
- 若 100 题预实验未达到 GO 标准，按第 4 步第 7 项：补查改写规则只允许修改一次，并写入实验记录后再重跑。

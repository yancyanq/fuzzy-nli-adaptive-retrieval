# 第 3 步：比较作答模型（API 预实验）

在 `pilot.json` 的前 N 道题上，用同一套检索（k=2、m=1）给每个候选作答模型跑两个分支：

- **分支 A（首轮）**：只用 BM25 取出的前 k 段作答。
- **分支 B（补查后）**：用前 k 段，再加上规则改写查询后补的 m 段作答。

脚本会输出答案 F1 / EM、token 数、延迟，以及是否支持 logprobs，用来挑选主实验模型。

把 `compare_models.py` 放到项目工作目录，和 `pilot.json`、`bm25_topk.py` 放在同一文件夹（有 `bm25_topk.py` 时会直接调用它的分词函数，保证和第 2 步完全一致）。

## 1. 安装依赖

在 cmd 或 PowerShell 中：

```bat
pip install openai rank_bm25
```

## 2. 设置 API Key（不要把 key 写进命令行，也不要发到聊天里）

脚本只从环境变量读取密钥，运行时只会打印变量名是否已设置（`DEEPSEEK_API_KEY=set`），不会打印密钥本身。

**cmd（仅当前窗口有效）：**

```bat
set DEEPSEEK_API_KEY=这里填你的key
set OPENAI_API_KEY=这里填你的key
```

**PowerShell（仅当前窗口有效）：**

```powershell
$env:DEEPSEEK_API_KEY = "这里填你的key"
$env:OPENAI_API_KEY = "这里填你的key"
```

**想长期保存（新开的窗口才生效，当前窗口还要用上面的命令再设一次）：**

```bat
setx DEEPSEEK_API_KEY "这里填你的key"
```

```powershell
setx OPENAI_API_KEY "这里填你的key"
```

检查是否已设置（不要用 `echo %DEEPSEEK_API_KEY%` 把密钥打到屏幕上）：

```bat
echo %DEEPSEEK_API_KEY:~0,3%
```

PowerShell：

```powershell
if ($env:DEEPSEEK_API_KEY) { "DEEPSEEK_API_KEY=set" } else { "DEEPSEEK_API_KEY=MISSING" }
```

## 3. 进入目录并运行

**cmd：**

```bat
cd /d <项目目录>
```

**PowerShell：**

```powershell
Set-Location <项目目录>
```

### DeepSeek（`deepseek-chat`）

```bat
python compare_models.py --data pilot.json --preset deepseek --n 30 --out step3_deepseek
```

可选：加上单价后会估算 30 题和外推到 1600 题（每题两个分支）的费用。单价请到 DeepSeek 官网查看当前价格，单位是「每 100 万 token 的美元」，不要沿用过期数字。

```bat
python compare_models.py --data pilot.json --preset deepseek --n 30 --out step3_deepseek --price-in 0.28 --price-out 0.42
```

（上面的 `0.28` / `0.42` 只是命令格式示例，不是报价。）

### OpenAI（`gpt-4o-mini`）

```bat
python compare_models.py --data pilot.json --preset openai --n 30 --out step3_openai
```

同样可以加 `--price-in` 和 `--price-out`（到 OpenAI 官网查看当前价格）。

### 以后本地 vLLM（主实验）

vLLM 提供和 OpenAI 兼容的接口，换地址即可，脚本不用改。如果服务不需要真实密钥，可设一个占位变量：

**cmd：**

```bat
set LOCAL_API_KEY=EMPTY
python compare_models.py --data pilot.json --preset custom --base-url http://127.0.0.1:8000/v1 --model Qwen2.5-7B-Instruct --key-env LOCAL_API_KEY --n 30 --out step3_qwen
```

**PowerShell：**

```powershell
$env:LOCAL_API_KEY = "EMPTY"
python compare_models.py --data pilot.json --preset custom --base-url http://127.0.0.1:8000/v1 --model Qwen2.5-7B-Instruct --key-env LOCAL_API_KEY --n 30 --out step3_qwen
```

## 4. 输出文件在哪里

默认写到 `--out` 指定的文件夹（例如 `<项目目录>\step3_deepseek\`）：

| 文件 | 内容 |
|---|---|
| `per_question.csv` | 逐题结果：答案、F1_A / F1_B / delta、EM、token、延迟、logprob、引用标题。用 Excel 打开即可（UTF-8 with BOM）。 |
| `branches.jsonl` | 两个分支的完整记录（原文、解析结果、检索到的段落）。 |
| `summary.json` | 汇总数字，和终端表格一致。 |
| `cache.jsonl` | API 响应缓存。按 `(model, _id, branch)` 去重，重跑同一设置不会重复计费。 |

如果改了 `--k`、`--m` 或提示词，请删除对应的 `cache.jsonl` 后再跑，否则会读到旧答案。

## 5. 怎么读终端表格

运行结束会打印类似下面的表：

```
model=deepseek-chat  data=pilot.json  n=30  k=2  m=1
------------------------------------------------------------------------
                         A (round1)   B (round1+2)         Oracle
mean EM                       0.xxx          0.xxx              -
mean F1                       0.xxx          0.xxx          0.xxx
improved / tie / degraded (eps=0.0):  a / b / c
mean prompt tokens / call:     ...
mean completion tokens / call: ...
total tokens:                  ...
mean latency / call (s):       ...
logprobs_supported:            True 或 False
estimated cost (30 q x 2 branches): $...
extrapolated (1600 q x 2 branches):  $...
```

含义简要说明：

- **A**：只看首轮 2 段时的平均 EM / F1，也就是「不补查」的基线。
- **B**：补查后再作答的平均 EM / F1。
- **Oracle F1**：每道题在 A、B 里取较高的 F1 再平均，是当前补查策略能达到的提分上限。
- **improved / tie / degraded**：补查后 F1 升高、持平、下降的题数。持平容差由 `--tie-eps` 控制，默认 0。
- **token / latency**：两次调用的用量和耗时，用来估费用和速度。
- **logprobs_supported**：接口能否返回 token 概率。若支持，CSV 里会有该答案的平均 / 最小 logprob，后面做模型不确定性信号时用得上。
- **外推费用**：按这次 30 题（每题两个分支）的实际 token，线性放大到 1600 题 × 2 个分支。预实验和主实验的提示长度接近时，这个数字才有参考价值。

## 6. 怎么挑选作答模型

按下面四条一起看，不要只看平均分：

1. **首轮 F1（A 的 mean F1）最好落在中间**，大约 0.4–0.7。太高则补查空间很小，太低则补查也很难救回来。
2. **补查是否有收益**：看 B 相对 A 的 F1 是否上升，以及 `improved` 是否明显多于 `degraded`。Oracle 比 A 高出越多，说明越值得做门控。
3. **是否支持 logprobs**：两个模型质量接近时，能返回 logprobs 的更有利于后续加入不确定性信号。
4. **费用和速度**：用 30 题的实际 token 和外推到 1600 题的费用，结合平均延迟来判断是否负担得起。

如果两个模型在第 1、2 条上差不多，优先选更便宜、或能返回 logprobs 的那个。把终端表和 `summary.json` 发给我，我们一起定模型。

## 7. 常用可选参数

```bat
python compare_models.py --data pilot.json --preset deepseek --n 30 --out step3_deepseek --tie-eps 0.0 --sleep 0.2
```

- `--n`：取文件开头的 N 道题，默认 30。
- `--k` / `--m`：默认 2 和 1，应与已确定的检索设置一致。
- `--temperature`：默认 0。
- `--max-tokens`：默认 128。
- `--tie-eps`：F1 持平容差，默认 0。
- `--sleep`：两次新的 API 调用之间的间隔（秒），遇到限流可以加大。
- `--no-cache`：不读写缓存。
- `--cache 路径`：自定义缓存文件位置。

## 8. 注意

- 必须先完成第 2 步的数据切分，保证这里的 `pilot.json` 就是种子 42 切出的那 100 题。
- 官方评分与 HotpotQA 的 `hotpot_evaluate_v1.py` 一致（小写、去标点、去冠词、yes/no/noanswer 特例）。
- 遇到限流会自动退避重试；如果模型不支持 logprobs，会去掉该参数再请求一次，并在结果里记 `logprobs_supported=False`。
- 密钥只放在环境变量里，不要写进脚本、不要提交到 git、不要发到聊天。

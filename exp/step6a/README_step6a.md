# 第 6a 步：检查本地 vLLM 模型的 token logprob 是否退化

**为什么要做这一步。** [第 5b 步实测](../EXPERIMENT_LOG.md?plain=1#L218)表明：`deepseek-chat` 在 temperature 0 下，把被选中 token 的 logprob 一律报成 `0.0`，并把几乎全部其余候选报成占位值 `-9999.0`。按预注册定义算出的 margin 对 88 道主分析题全部是 `9999.0`，AUC 为 0.500，表示「没有信息」，不是「信号很弱」。因此，logprob 类信号要等到主实验的本地模型上，先确认没有这两种退化，再进入模糊门控。

**这一步只检查是否退化，不检查预测能力。** 只用 tune 集的前 30 题、只跑分支 A（首轮，k=2），共 30 次调用。这里**不算 AUC**，也不调门控阈值。通过只表示：在这个接口、这组设置下，可以把 logprob 信号纳入后续门控评估；不通过则不能把这类信号送进门控，直到接口给出非退化的 logprob。

> 本目录下的测试只用 mock 服务器和合成题目，其中的所有数字都是**假的**（由哈希生成），**不是**实验结果。还没有对真实的本地模型跑过，所以现在没有真实结果。

## 预先登记的通过标准（看到真实结果之前写定）

判定为 **PASS** 当且仅当下面四条全部成立，否则为 **FAIL**，并列出未通过的条。第 1、2、3、4 条中的具体数字是主观阈值，预先登记；论文里需要写明它们是事先定的，并给出下面的理由。命令行可以改这些阈值，但正式跑必须用默认值。

1. **答案片段上，被选中 token 的 logprob 恰好为 `0.0` 的比例不超过 50%。**  
   理由：temperature 0 的贪心解码里，特别有把握的 token 确实可能得到接近 0 的值（例如 `-1e-6` 四舍五入后变成 0），所以允许少量恰好为 0。若大多数都恰好是 0，就和 DeepSeek 那种「全部钳成 0」的情况同类。备选：「一条都不许为 0」过严，健康的 vLLM 也可能因四舍五入失败；「只要有方差就不管有多少个 0」又太松，会漏掉第 5b 步那种全面钳制。50% 是主观、预先登记的判断。

2. **占位候选（logprob ≤ -9000）占全部返回候选的比例低于 5%。**  
   理由：第 5b 步里 `-9999.0` 表示「概率小到不报告」，不是真实 logprob。截断取 -9000，是为了罩住这种整哨兵值，同时远低于 top-5 里通常会出现的真实对数概率。允许低于 5% 是为了容忍个别编码异常，又不至于把第 5b 那种几乎全是占位值的情况判成通过。备选：「一条占位都不许」更严一点；「只看被选中 token、不看候选」则会漏掉 margin 信号的退化。-9000 和 5% 都是主观、预先登记的判断。「低于 5%」是严格小于。

3. **30 道题上，每题答案片段（找不到片段时退回全部输出 token）的「被选中 token logprob 平均值」至少有 10 个不同取值，且方差不为 0。**  
   理由：即使单个 token 很少为 0，各题的平均值仍可能塌缩成同一个常数。30 题若报告的是真实概率，平均值应有分散。取 10（30 的三分之一）是为了说明没有塌成少数几个值，同时允许不同题因四舍五入或短答案而相同。备选：「只要方差非零」太弱（两个不同值也能过）；「30 个值全不相同」过严。10 是主观、预先登记的判断。

4. **对每题的平均 margin（第一名候选 logprob 减第二名候选 logprob，片段规则与第 5b 步相同）提出同样的要求。**  
   理由：第 5b 步里 margin 在主分析的 88 题上全部是 9999.0，就是因为候选是占位值。把平均 margin 的分散度单独检查，可以在「被选中 logprob 看起来还行、但候选是占位值」时仍然判失败，反过来也成立。10 同样是主观、预先登记的判断。

另外有一条程序性规则（不是主观阈值）：计划检查的题必须都拿到可用的 logprob。有题调用失败或没有 token 时，判定为 **FAIL**，失败项记为 `incomplete`，因为这时不能证明「非退化」。

## 1. 需要哪些文件

把 `check_logprobs.py` 复制到项目工作目录。同一文件夹里应该已经有：

- `tune.json`（第 1 步切出的 500 题调参集，格式与 `pilot.json` 相同）；
- `compare_models.py`、`bm25_topk.py`（提示词、检索、解析、打分从 `compare_models.py` 导入，和第 3、5 步完全一致）；
- `rerun_toplogprobs.py`（margin、熵、答案片段定位从这里导入，不复制实现）；
- `analyze_signals.py`（`rerun_toplogprobs.py` 在导入时会用到，本步本身不算 AUC）。

如果盒子上或当前目录没有 `tune.json`，必须显式给出数据路径，并可用 `--n`、`--offset` 取切片，例如：

```bat
python check_logprobs.py --data tune.json --n 30 --offset 0 --out step6a_check
```

依赖和第 3 步相同，不需要在客户端安装 torch 或 vLLM（vLLM 装在租用的 GPU 机器上）：

```bat
pip install openai rank_bm25
```

## 2. 在租用的 GPU 上启动 vLLM

官方命令行参数名以当前 vLLM 文档为准：[vllm serve](https://docs.vllm.ai/en/stable/cli/serve/) 与 [Engine Arguments](https://docs.vllm.ai/en/stable/configuration/engine_args/)。文档中的参数是 `--max-logprobs`（默认 20；`-1` 表示不封顶）。本步请求 `top_logprobs=5`，因此该上限必须 **≥ 5**。默认 20 已经够用；若要与请求对齐，也可以显式写成 5。不要发明其他参数名。

在 GPU 机器上（示例，模型名与脚本默认一致）：

```bash
vllm serve Qwen/Qwen2.5-7B-Instruct --host 127.0.0.1 --port 8000 --max-logprobs 5
```

说明：

- `--host 127.0.0.1` 表示只监听本机，避免把端口暴露到公网。
- 服务起来后，OpenAI 兼容地址是 `http://127.0.0.1:8000/v1`。
- 7B 指令模型需要能装下该模型的 GPU；具体显存、`--dtype` 等请按当前 vLLM 文档和机器配置设置，这里不写未经核验的数字。
- 多数本地 vLLM 不校验 API key。客户端在环境变量 `VLLM_API_KEY` 未设置时，会使用占位值 `EMPTY`，不会把密钥打印出来。

确认服务已好（在 GPU 本机，或隧道已经连通的客户端上）：

```bash
curl http://127.0.0.1:8000/v1/models
```

## 3. 如果在本地跑客户端、模型在远程 GPU 上：用 SSH 隧道，不要把端口公开

不要把 GPU 机器的 8000 端口映射到公网。在本地开一条到 GPU 本机端口的 SSH 隧道，然后客户端仍连接 `http://127.0.0.1:8000/v1`。

**Windows（系统自带的 OpenSSH）**，把 `user` 和 `gpu-host` 换成实际的登录名和主机：

```bat
ssh -N -L 8000:127.0.0.1:8000 user@gpu-host
```

这条命令会占着当前窗口，保持隧道。另开一个窗口再跑下面的 Python 命令。PowerShell 同样可以使用 `ssh`。若 GPU 上的 vLLM 不是监听 8000，把两边的端口改成实际端口。

隧道通了以后，脚本的 `--base-url` 用默认值即可（`http://localhost:8000/v1`），也可以写成 `http://127.0.0.1:8000/v1`。

## 4. 密钥（可选；不要写进命令行，也不要发到聊天里）

脚本只从环境变量 `VLLM_API_KEY` 读取密钥；未设置时自动用 `EMPTY`。终端只会显示 `VLLM_API_KEY=set` 或 `MISSING`，不会显示密钥本身。

如果租用机器上的 vLLM 配置了 `--api-key`，再在客户端设置同一值：

**cmd（只对当前窗口有效）：**

```bat
set VLLM_API_KEY=这里填你的key
```

**PowerShell（只对当前窗口有效）：**

```powershell
$env:VLLM_API_KEY = "这里填你的key"
```

检查是否设置成功（只显示 set / MISSING）：

```bat
python -c "import os; print('VLLM_API_KEY=' + ('set' if os.environ.get('VLLM_API_KEY') else 'MISSING'))"
```

## 5. 运行

**cmd：**

```bat
cd /d <项目目录>
python check_logprobs.py --data tune.json --out step6a_check
```

**PowerShell：**

```powershell
Set-Location <项目目录>
python check_logprobs.py --data tune.json --out step6a_check
```

默认值已经是本步锁定的设置：模型 `Qwen/Qwen2.5-7B-Instruct`、`--base-url http://localhost:8000/v1`、前 30 题（`--n 30 --offset 0`）、只跑分支 A、k=2、temperature 0、max_tokens 128、`logprobs=True`、`top_logprobs=5`。运行开始时会先打印四条通过标准，然后再发请求。

**会发多少次请求。** 这一步会新发 **30 次调用**（只跑分支 A）。中途断了，再执行同一条命令即可：已完成的调用从缓存读取，出错的会重试。缓存写在 `step6a_check\cache_logprob_check.jsonl`，**不会**使用或改写名为 `cache.jsonl` 的文件（第 3、5 步的缓存不受影响）。

**只重新判定、不调用接口：**

```bat
python check_logprobs.py --data tune.json --out step6a_check --analyze-only
```

若模型名或地址不是默认值，例如：

```bat
python check_logprobs.py --data tune.json --base-url http://127.0.0.1:8000/v1 --model Qwen/Qwen2.5-7B-Instruct --out step6a_check
```

## 6. 怎么读判定结果

结果在 `step6a_check\` 里：

| 文件 | 内容 |
|---|---|
| `logprob_check.json` | 汇总、四条标准的观测值与是否通过、总判定、每题的平均 logprob / margin，以及仅供参考的 EM / F1。 |
| `logprob_check_tokens.csv` | 逐 token：被选中 logprob、是否落在答案片段、第一名 / 第二名候选、margin、是否为占位值、被选中值是否等于第一名候选。用 Excel 打开即可（UTF-8 with BOM）。 |
| `cache_logprob_check.jsonl` | 可续跑的响应缓存。 |

终端末尾会打印一行 `VERDICT: PASS` 或 `VERDICT: FAIL`。失败时会列出未通过的项，名称与 JSON 里 `failed_criteria` 一致：

- `incomplete`：有题没有可用的 logprob（调用失败或缓存缺项）。
- `zero_chosen_frac`：答案片段上恰好为 0.0 的被选中 token 超过 50%。
- `placeholder_alt_frac`：占位候选（≤ -9000）达到或超过全部候选的 5%。
- `mean_chosen_logprob_spread`：各题平均被选中 logprob 的不同值少于 10 个，或方差为 0。
- `mean_margin_spread`：各题平均 margin 同样不满足分散要求。

JSON 里还可以看到（这些不是判定条件，但写报告时要用）：

- 全部 token 与答案片段上，被选中 logprob 恰好为 0.0 的比例；
- 被选中 token 的 logprob 是否等于第一名候选的 logprob（健康的 vLLM / OpenAI 风格接口通常相等）；
- 各题平均被选中 logprob、平均 margin 的最小 / 中位数 / 最大、不同值个数、方差；
- 相对黄金答案的平均 EM / F1（**只作信息，不参与判定**）。

把 `logprob_check.json` 发给我即可。通过之后，再在后续步骤里评估 logprob 对门控的预测能力；不通过就不要把 logprob 送进门控。

## 7. 常用可选参数

```bat
python check_logprobs.py --data tune.json --n 30 --offset 0 --out step6a_check --sleep 0.1
```

- `--n` / `--offset`：取文件里从 offset 起的 N 道题，默认 0 和 30，即 tune 集前 30 题。
- `--k`：首轮 BM25 top-k，默认 2。本步只跑分支 A。
- `--temperature` / `--max-tokens` / `--top-logprobs`：默认 0、128、5。
- `--timeout`：单次请求超时，默认 120 秒（本地模型有时比 API 慢）。
- `--sleep`：两次新调用之间的间隔（秒）。
- `--max-zero-chosen-frac`、`--max-placeholder-alt-frac`、`--placeholder-threshold`、`--min-distinct-values`：覆盖预先登记的阈值。正式实验请不要改默认值。

## 8. 注意

- 必须先完成第 1 步的数据切分，这里的 `tune.json` 应是种子 42 切出的那 500 题，且与 `pilot.json`、`test.json` 的 `_id` 不相交。
- 提示词、检索和解析与第 3、5 步相同，从 `compare_models.py` 导入，不另写一份。
- 密钥只放在环境变量里，不要写进脚本、不要提交到 git、不要发到聊天，也不要写在命令行。
- mock 测试通过不代表本地模型通过。只有在租用 GPU 上对真实模型跑完，并以默认阈值得到的 `VERDICT` 才是本步的结果。

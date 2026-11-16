# 运行环境与可复现性

## 客户端环境

用独立 Python 虚拟环境，从包根目录运行 [INDEX](../INDEX.md) 中的命令。Windows PowerShell 可用 `py -m venv .venv`，随后运行 `.venv\Scripts\Activate.ps1`。macOS/Linux 可用 `python3 -m venv .venv`，随后运行 `source .venv/bin/activate`。命令里的正斜杠路径可作为 Python 文件参数在 Windows 上使用。

```bash
python -m pip install openai==1.76.2 rank-bm25==0.2.2
python -m pip check
```

这是本次客户端测试采用的两个直接依赖版本，与 [Step 6a 客户端安装决策](../exp/EXPERIMENT_LOG.md?plain=1#L296)一致。Step 2–5b 在 YangQS 的完整环境锁记录中未给出。Step 2 只需 `rank-bm25`，其 pip 依赖包含 NumPy。没有项目级 requirements 或 lock 随包提供。

## 各脚本与测试依赖

| 脚本 / 测试 | 导入的本地代码 | pip、数据与运行模式 | 环境变量 |
| --- | --- | --- | --- |
| Step 1 数据切分 | 切分脚本未收到 | 11-14 选源条目提到用 `datasets`；实际下载、切分及转 JSON 脚本和精确依赖版本记录中未给出。V2 已归档固定版本 `hotpot_evaluate_v1.py` | 记录中未给出 |
| `step2/bm25_topk.py` | 无 | `rank-bm25`；官方式 `pilot.json` 输入，标准库读写 | 无 |
| `step3/compare_models.py` | 优先动态加载 `step2/bm25_topk.py` 的分词与段落拼接，也内置回退 | 导入 `rank-bm25`；需要调用时加载 `openai`；先做输入与缓存核对 | DeepSeek 默认 `DEEPSEEK_API_KEY`，OpenAI 默认 `OPENAI_API_KEY`，custom 默认 `LOCAL_API_KEY`，可用 `--key-env` 指定变量名；无鉴权的 custom 端点允许未设置 |
| `step3/test_mock_server.py` | 无 | 标准库 HTTP 服务；可传 `--answers-from` 读取题目，输出为测试值；支持拒绝 logprobs 和不同假 top-logprobs 模式 | 无 |
| `step5/run_pilot.py` | 动态加载 `step3/compare_models.py`，间接复用 Step 2 | 导入时需要 `rank-bm25`；新作答调用需要 `openai`；HF NLI 另需 pip 包 `torch`、`transformers` 与 checkpoint/tokenizer；`--nli-only` 从原缓存读答案；`--nli-backend mock` 使用测试值 | 作答沿用 Step 3；本地 HF NLI 无脚本明确要求的环境变量 |
| `step5/audit_helper.py` | 无 | 标准库；读 `audit_sample.csv`、`nli_scores.jsonl`，写待填 `audit_review.csv` | 无 |
| `step5/analyze_signals.py` | 无 | 标准库；读 Step 5 `per_question.csv`，离线计算 AUC、分组统计与 bootstrap CI | 无 |
| `step5/test_step5.py` | 导入 `run_pilot.py`；子进程启动 `step3/test_mock_server.py` | `unittest`（标准库）、`rank-bm25`、`openai`、本地回环端口、`step5/testdata/mini_pilot.json`；用 mock NLI 并测试缺少 HF 依赖时的报错 | 套件在进程内注入本地占位配置 |
| `step5/test_analyze_signals.py` | 导入 `analyze_signals.py` | 标准库 `unittest`；临时构造合成 CSV | 无 |
| `step5/probe_logprobs.py` | 无 | `openai`；请求四次短提示；写探测 JSON | DeepSeek / OpenAI 默认同 Step 3；custom 默认 `OPENAI_API_KEY`，可改 `--key-env`，脚本要求所选变量非空 |
| `step5b/rerun_toplogprobs.py` | 动态加载 `step3/compare_models.py` 与 `step5/analyze_signals.py` | `rank-bm25`；新调用需 `openai`；输入 pilot 和 Step 5 `per_question.csv`；`--analyze-only` 从 `cache_toplp.jsonl` 回算 | 新调用沿用 Step 3 |
| `step5b/test_step5b.py` | 导入 `rerun_toplogprobs.py`、`step3/test_mock_server.py`，并启动 mock 子进程 | 标准库 `unittest`、`rank-bm25`、`openai`、本地回环、`mini_pilot.json`、临时合成 Step 5 标签文件 | 套件注入测试占位值 |
| `step6a/check_logprobs.py` | 动态加载 `step3/compare_models.py` 和 `step5b/rerun_toplogprobs.py`；后者还加载 `step5/analyze_signals.py` | `rank-bm25`；请求需 `openai` 和另起的 vLLM 兼容服务；`--analyze-only` 读隔离的 `cache_logprob_check.jsonl`，仍需数据 | `VLLM_API_KEY` 可选且可改名；无鉴权端点可不设 |
| `step6a/test_step6a.py` | 导入 `check_logprobs.py`；启动 `step3/test_mock_server.py` 子进程 | 标准库 `unittest`、`rank-bm25`、`openai`、本地回环、代码生成的合成题 | 套件注入测试占位值 |

`--key-env` 接收变量名。真实凭据通过本地受控环境变量提供。包中凭据常见格式的扫描只发现测试代码原有的假值；测试进程未继承真实凭据。测试本身无需付费 API、GPU、PyTorch、Transformers 或 vLLM。

运行 Step 5 的实际 NLI 时，安装与 YangQS 驱动匹配的 CUDA 版 `torch` 和 `transformers`，准备 `MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli` 模型与 tokenizer 快照。用 `python -c "import torch; print(torch.cuda.is_available())"` 检查设备，`--nli-device auto` 可在 CUDA 不可用时选 CPU。发生 tokenizer 依赖问题时应记录并冻结所需包及版本，实际版本以设备 lock 为准。日志记录正式 pilot 对引用段落按顺序拼接，无可用引用时回退并计数，假设采用固定模板 `The answer to the question "{question}" is: {answer}.`，NLI 标签映射取模型配置中的 `id2label`。标题级引用可算段落覆盖，官方 SP F1 需要句索引。 [Pilot 实现](../exp/EXPERIMENT_LOG.md?plain=1#L134) · [Pilot 实测](../exp/EXPERIMENT_LOG.md?plain=1#L146)

## Step 6a 服务端的历史记录

日志记载远端准备环境为 Python 3.10.12、Tesla T4（计算能力 7.5），vLLM 0.8.5、PyTorch 2.6.0+cu124、CUDA 12.4、xFormers 0.0.29.post2、Transformers 4.51.3。启动时为 Triton 补装 setuptools 80.9.0 后重新生成 lock 并重启。采用 vLLM V0 和 xFormers、原始未量化 Qwen/Qwen2.5-7B-Instruct 权重，记录的 HF revision 为 `a09a35458c702b33eeacc393d103063234e8bc28`。日志确认配套文件与权重校验符合该 revision。实测条目记录了客户端命令、服务器启动封装和 lock 的路径；远端启动封装、lock 与服务原始日志待归档。 [服务端准备](../exp/EXPERIMENT_LOG.md?plain=1#L296) · [启动记录](../exp/EXPERIMENT_LOG.md?plain=1#L321) · [实测](../exp/EXPERIMENT_LOG.md?plain=1#L326)

按 [Step 6a README](../exp/step6a/README_step6a.md) 配置单独的服务进程。若复现日志中的 T4 设置，按[服务端配置](../exp/EXPERIMENT_LOG.md?plain=1#L308)使用 `--dtype half --cpu-offload-gb 4 --enforce-eager --max-model-len 4096 --max-num-seqs 1`、`--max-logprobs 5`，保持原模型名与生成配置。绑定 `127.0.0.1:8000`，从客户端跨机访问时使用 README 里的 SSH 本地转发。确认服务健康并指向正确模型后，再运行索引中的检查命令。包内不含模型权重和远端 Python 环境。

## 运行边界

- 在整理包根目录运行，保留 `exp/step2`、`exp/step3`、`exp/step5`、`exp/step5b`、`exp/step6a` 的相对位置。若使用历史平铺结构，部分脚本会优先载入当前目录的同名模块。使用整理包时从包根运行可核对脚本打印的导入来源。
- Step 3/5 复用历史回答前，确认数据顺序、模型、提示和解码设置一致。复现命令把新输出写到 `runs/`。有历史 Step 3 缓存时按索引传入 `--answer-cache`，若无缓存则先确认新增调用范围。变更检索或提示时使用新的输出目录来保留旧缓存。
- Step 5b 和 Step 6a 可用 `--analyze-only` 从各自缓存离线回算。Step 5b 依赖原 Step 5 逐题表，Step 6a 仍依赖相同的 tune 文件和样本范围。两步均拒绝将缓存写到文件名为 `cache.jsonl` 的路径。
- 归档的 README 中仍是原机器路径、示例价格和历史操作方式。包内复现路径以 [INDEX](../INDEX.md) 为准，历史实际费用记录中未给出。

## 测试与核查

在包根目录可分别运行这些 `unittest` 套件。Step 3 的 `test_mock_server.py` 启动后持续监听，是测试服务入口；检查它需要先启动本地服务，再运行客户端测试。测试覆盖假回答与假 logprobs 的处理。

```bash
python exp/step5/test_step5.py
python exp/step5/test_analyze_signals.py
python exp/step5b/test_step5b.py
python exp/step6a/test_step6a.py
```

本次在 macOS arm64 的临时环境中实际验证。Python 为 3.13.3，OpenAI 客户端 1.76.2，rank-bm25 0.2.2，NumPy 2.2.5。依赖从 PyPI 获取并核对 wheel SHA-256，`pip check` 通过。下表数字是本地测试计数。

| 检查 | 本次结果 | 验证范围 |
| --- | --- | --- |
| `test_step5.py` | 23/23 通过 | Mock API / NLI、评分、GO、bootstrap、缓存与截断 |
| `test_analyze_signals.py` | 6/6 通过 | 合成数据上的诊断和 AUC |
| `test_step5b.py` | 17/17 通过 | Mock top_logprobs、同题诊断和缓存隔离 |
| `test_step6a.py` | 16/16 通过 | Mock PASS/FAIL、判定边界、缓存和命令行选项 |
| `test_mock_server.py` | 支持 logprobs 和拒绝后回退，两次联调通过 | 两次各以同一条 pilot 输入测试 A/B；验证无调用错误、正确标记支持状态和生成预期文件。回答及分数为测试值 |
| Step 2 两组离线复跑 | 两组逐题 CSV 都与随包字节一致；汇总除整理后的输入路径字段外完全一致 | 真实 pilot 输入和本地 BM25，直接复核随包召回产物 |
| Step 1 可见切分与原始文件 | pilot 与 tune 的 bridge 类型、ID 唯一性和互不相交通过；tune 的 SHA-256 与[输入核验记录](../exp/EXPERIMENT_LOG.md?plain=1#L289)一致 | 此次早期复核覆盖 pilot 和 tune；V2 的正式 test 已归档 |
| Step 6a 真实缓存离线回算 | 四项判定、样本顺序和 PASS 一致，逐 token CSV 字节一致 | 使用随包原始缓存和相同 tune 切片运行 `--analyze-only`，无新推理 |
| 付费 API、真实 DeBERTa NLI、租用 GPU 与 vLLM | 本次整理未重新发起模型调用 | 真实执行以日志和随附产物为准 |

Step 6a 回算时，单题 `mean_chosen_logprob` 的 JSON 展示值出现一次末位舍入差异，影响到第六位小数。四条判定的零值比例、占位比例、不同值数量和记录所列精度下的方差均一致。归档保留远端原始输出。

复现 Step 3 的 mock 联调时，先在另一终端启动以下服务，然后执行客户端命令。切换 logprob 拒绝路径时，重启服务并增加 `--reject-logprobs`，客户端改用新输出目录。

```bash
python exp/step3/test_mock_server.py --host 127.0.0.1 --port 8765 --answers-from exp/step1/pilot.json
python exp/step3/compare_models.py --data exp/step1/pilot.json --preset custom --base-url http://127.0.0.1:8765/v1 --model mock-qa --n 1 --out runs/step3_mock_smoke
```

## V2 环境和验证入口

正式阶段的代码在 [exp/v2](../exp/v2/README.md)。`analyze_pilot_signals_v2.py` 复用 `compare_models.py` 和 `analyze_signals.py`。门控校准额外复用该信号实现。正式生成与评估共用校准、信号与 `run_pilot.py`，回放使用固定版 `hotpot_evaluate_v1.py`。`analyze_step6_v2.py` 复用生成模块与原配对 bootstrap，图表使用 ReportLab。离线命令和版本核验见 [V2 可复现性清单](../exp/v2/step6_v2/Reproducibility_Checklist.md)。

仓库中的 V2 测试使用 Python 3.12.14、OpenAI 客户端 1.76.2、rank-bm25 0.2.2、NumPy 2.5.4、ReportLab 4.4.9。测试数字来自合成用例。真实运行使用 V2 清单所列的 GPU 环境。

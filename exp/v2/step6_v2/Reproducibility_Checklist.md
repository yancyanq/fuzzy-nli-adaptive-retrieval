# V2 §10.2 可复现性清单

对应 [《实验方案 V2》第 10.2 节](../../../docs/Experiment_Protocol_v2.docx)的七项。此次用已归档的答题、引用、NLI 和计时记录重新计算。开发集锁定产物、正式集预测和分数、配对置信区间、错误分析样本和质量–成本图均与归档一致。验证范围是**从已保存的模型输出复现结果**。从权重重新推理和重新实测延迟属于另一层验证。

| V2 项目 | 填报结果 |
|---|---|
| **随机种子（抽样／解码）** | 数据划分 seed **42**。使用 HotpotQA distractor 公开 validation 中的 bridge 题，固定 100 / 500 / 1,000 个互斥 ID 对应 pilot / dev / test。计时样本按 UTF-8 字符串 `42:<题目 ID>` 的 SHA-256 升序取前 32。门控同分处理和错误分析抽样也使用这个固定哈希键。配对 bootstrap 使用 seed **42**，有放回抽样 10,000 次。生成温度 **0**，最大输出 **128 tokens**。归档客户端请求及 vLLM 启动命令均未显式传解码 seed，因此解码 seed 栏记为「未显式设置」。 |
| **正式实验重复次数** | ☑ **单次生成**。每个正式题各有一条 A、B 和 Full-context 输出。九组策略的质量从共享缓存回放，含两项消融和 A/B Oracle。每种真实策略在共用的 32 道题上各测一次延迟，另用 8 道 dev 题预热，并发 8。 |
| **硬件与软件环境** | **原始运行**使用 Tesla T4，15,360 MiB，驱动 535.216.01，主机内存约 30 GiB，Python 3.10.12，vLLM 0.8.5 V0，PyTorch 2.6.0+cu124，CUDA 12.4，xFormers 0.0.29.post2，Transformers 4.51.3，OpenAI 客户端 1.76.2，rank-bm25 0.2.2。Qwen 使用 FP16、4 GiB CPU offload、eager 模式、4,096 token 上下文和最多 8 并发序列。离线 NLI 使用 CUDA、batch 4、512 token 上限。实时计时使用 GPU 上的 Qwen 与 CPU 上的 NLI，后者为四线程、batch 1，使用串行调用。**此次 Mac 回放**使用 Darwin arm64、Python 3.12.14、NumPy 2.5.4、rank-bm25 0.2.2、ReportLab 4.4.9。 |
| **代码版本** | 本次正式运行的代码以项目根目录脚本归档为准。现有早期 Git 仓库未包含当次正式生成、评分和分析脚本。正式运行的 Git commit 栏记为「无对应归档 commit」。代码与配置身份由原始输入清单、锁文件和下面的本地 SHA-256 清单追溯。 |
| **双分支与日志** | 每题的答案、段落引用、生成耗时及 token 在答题缓存，句级证据和选择器调用在证据缓存，NLI 三分类概率在 NLI 缓存，官方分数、桥接信号与各策略选支在逐题表。实测端到端时间和各类 token 按 32 题计时子集归档。各文件和数量见下表。 |
| **缓存策略** | ☑ 首轮 A、☑ 再检索 B、☑ NLI。同时归档 Full-context、句级证据与实测计时。A/B/Full 答题和证据的缓存键为 `(答题模型名, _id, 分支)`，A/B NLI 沿用该键并另存 NLI 模型身份。计时缓存键为 `(NLI 设备, _id, 策略)`。正式入口按清单核对数据、代码、锁和权重。**失效规则**为数据、权重、生成设置、提示词、BM25／改写或 NLI 配置改变时，从受影响的最早阶段使用新缓存。只改变门控策略时，可用原答题和 NLI 缓存重新回放。 |
| **失败重试** | 答题及证据选择器设置 **120 秒**请求 timeout。共享请求函数对连接／超时／限流或指定的临时 HTTP 错误按退避重试，应用层允许最多 **3 次尝试**。不支持 logprobs 时，可关闭该字段立即再试，此回退单独计。应用层次数与 SDK 自身重试各自计算。缓存逐条写入，读取时截掉未完整写入的末行，拒绝重复或意外的缓存键。使用同一脚本恢复时复用已完成记录。原始运行的 SSH 断连、tmux 窗格定位修复和 NLI 缓存身份字段修复均已记录。两份 NLI 缓存逐条核对，2,000 条评分数值均一致。 |

**版本文件**

- Qwen 答题与句级证据选择使用 **Qwen/Qwen2.5-7B-Instruct**，revision `a09a35458c702b33eeacc393d103063234e8bc28`。四个权重分片的 SHA-256 写在 [vLLM 启动脚本](../step4_dev/.serve-step4.sh)。
- NLI 使用 **MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli**，revision `b3546ea6b0346eb6f8d5d68b13c7dc6d0376b3d7`。NLI 权重哈希、相关源码哈希、检索设置及门控边界见 [门控锁](../step4_dev/gates/locked_gates.json)。
- HotpotQA 官方评分器固定在 commit `fa3a36370899e1d85822de61e58c85ea19993154`。归档评分器与正式输入清单的 SHA-256 一致。服务端安装日志记录完整依赖锁位于 `~/nlp/logs/requirements-step6a.lock`。本地环境栏依据已归档的版本记录和启动脚本填写。 [评分器原件](../step5_v2/hotpot_evaluate_v1.py) · [服务端输入清单](../step5_v2/inputs.sha256) · [本地可复现性校验清单](reproducibility.sha256)

| 文件 | 覆盖范围 |
|---|---|
| [正式答题缓存](../step5_v2/answers_test_v2.jsonl) | **3,000** 条，A、B、Full-context 各 1,000 条，含检索位置、答案、段落引用、耗时及输入／输出 token。 |
| [正式句级证据缓存](../step5_v2/evidence_test_v2.jsonl) | **3,000** 条，按分支保存原文标题和零起始句子编号，以及选择器调用状态、耗时和 token。 |
| [正式 NLI 缓存](../step5_v2/nli_test_v2.jsonl) | **2,000** 条，A/B 各 1,000 条，含三分类概率与两种模型身份。保留[元数据修复前的缓存](../step5_v2/nli_test_v2.original.jsonl)供比对。 |
| [正式逐题表](../step5_v2/per_question.csv)和[质量汇总](../step5_v2/quality_summary.json) | **1,000** 题的评分、桥接信号、NLI 及各策略决策。九组官方预测在 `step5_v2/predictions/`。 |
| [真实路径计时](../step5_v2/latency_test_v2.jsonl)和[成本汇总](../step5_v2/latency_summary.json) | **192** 条计时记录，六种策略各 32 题。均值、P50/P90/P95、答题及选择器 LLM 输入／输出 token、NLI token 和调用次数。 |
| [任务日志](../step5_v2/run.log)和[实验日志](../../EXPERIMENT_LOG.md) | 启动、恢复、缓存修复、计时预检和归档。 |

## 从原始缓存复现

从仓库根目录进入 `exp/v2`，用含上述分析依赖的 Python 环境运行。复现生成的文件写入临时目录。GPU 目录与启动命令见[步骤 4 README](../README_step4_v2.md)和[步骤 5 README](../README_step5_v2.md)。

```bash
set -e
shasum -a 256 -c step6_v2/reproducibility.sha256
(cd step4_dev && shasum -a 256 -c results.sha256)
shasum -a 256 -c step5_v2/archive.sha256

repro_dir=$(mktemp -d)
python3 calibrate_gates_v2.py \
  --tune tune.json --branches step4_dev/nli/branches.jsonl \
  --serve-script step4_dev/.serve-step4.sh --out "$repro_dir/gates"
for f in locked_gates.json dev_summary.json dev_selection.csv; do
  cmp "$repro_dir/gates/$f" "step4_dev/gates/$f"
done

mkdir "$repro_dir/replay"
for f in answers_test_v2.jsonl evidence_test_v2.jsonl nli_test_v2.jsonl latency_summary.json; do
  cp "step5_v2/$f" "$repro_dir/replay/"
done
python3 evaluate_test_v2.py evaluate --data test.json --out "$repro_dir/replay" \
  --scorer step5_v2/hotpot_evaluate_v1.py --serve-script step4_dev/.serve-step4.sh
for f in quality_summary.json per_question.csv; do
  cmp "$repro_dir/replay/$f" "step5_v2/$f"
done
for f in step5_v2/predictions/*.json; do
  cmp "$repro_dir/replay/predictions/$(basename "$f")" "$f"
done

python3 analyze_step6_v2.py --test test.json \
  --results "$repro_dir/replay" --out "$repro_dir/step6"
for f in paired_bootstrap.csv step6_summary.json error_audit_cases.json quality_cost.pdf; do
  cmp "$repro_dir/step6/$f" "step6_v2/$f"
done
```

此次通过了 23 项本地身份校验、12 项 dev 归档校验、27 项正式归档校验。复现了 3 个 dev 锁定产物、9 个官方预测文件、正式逐题表、质量汇总，以及 4 个步骤 6 分析产物，全部与归档逐字节一致。另将 192 条原始计时记录按六种策略和共用的 32 个题目 ID 分组，重新计算均值、时间分位数和调用／token 汇总，核对结果与归档一致。

## 从计时日志重算成本

```bash
python3 - <<'PY'
import json
from math import isclose
from pathlib import Path
from statistics import mean, quantiles

folder = Path("step5_v2")
summary = json.loads((folder / "latency_summary.json").read_text(encoding="utf-8"))
rows = [json.loads(line) for line in (folder / "latency_test_v2.jsonl").read_text(encoding="utf-8").splitlines()]
assert len(rows) == 192
assert {r["method"] for r in rows} == set(summary["methods"])
for method, recorded in summary["methods"].items():
    group = [row for row in rows if row["method"] == method]
    assert len(group) == recorded["n"] == 32
    assert {row["_id"] for row in group} == set(summary["sample_ids"])
    assert {row["nli_device"] for row in group} == {summary["nli_device"]}
    seconds = [row["elapsed_seconds"] for row in group]
    assert isclose(mean(seconds), recorded["seconds_mean"], abs_tol=1e-12)
    p = quantiles(seconds, n=100, method="inclusive")
    for n in (50, 90, 95):
        assert isclose(p[n-1], recorded[f"seconds_p{n}"], abs_tol=1e-12)
    for field in ("llm_calls", "nli_calls", "answer_calls", "selector_calls",
                  "prompt_tokens", "completion_tokens", "nli_input_tokens", "triggered"):
        assert isclose(mean(r[field] for r in group), recorded[field + "_mean"], abs_tol=1e-12)
print("Verified timing and token summaries for 192 archived live records.")
PY
```

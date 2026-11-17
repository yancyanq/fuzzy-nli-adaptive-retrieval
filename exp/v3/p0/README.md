# Group 13 V3.1 · P0 审计交付

**状态：P0 离线审计和 GPU 实机验收均已完成。** 参见[实机验收](gpu_runtime.md)、[实验日志](../EXPERIMENT_LOG.md)、[源码映射](source_map.md)、[数据审计](data_audit.md)、[长度逐题记录](length_audit.csv)、[资源与成本](resource_estimate.md)、[历史 ID 和测量清单](manifest.json)、[数据划分草案](split_plan.json)。本目录至 P0 为止。新最终集未抽取。

## 复跑离线审计

在仓库根运行。Kaggle 预检输入位于 exp/v3/preflight。历史副本通过可选的 --other-history 参数指定。脚本只读取归档，复跑输出写到新临时目录。示例使用 Python 3.13。依赖固定版本见下方命令。

```bash
set -e
p0_tmp=$(mktemp -d)
python3.13 -m venv "$p0_tmp/venv"
"$p0_tmp/venv/bin/pip" install 'transformers==4.51.3' 'tokenizers==0.21.4' \
  'pyarrow==21.0.0' 'rank_bm25==0.2.2' 'numpy==2.5.5' 'Jinja2==3.1.6'

qwen_base=https://huggingface.co/Qwen/Qwen2.5-7B-Instruct/resolve/a09a35458c702b33eeacc393d103063234e8bc28
for file in tokenizer.json tokenizer_config.json; do
  curl -fLsS "$qwen_base/$file" -o "$p0_tmp/$file"
done
curl -fLsS 'https://huggingface.co/datasets/hotpotqa/hotpot_qa/resolve/refs%2Fconvert%2Fparquet/distractor/validation/0000.parquet' \
  -o "$p0_tmp/hotpot-validation.parquet"
(
  cd "$p0_tmp"
  shasum -a 256 -c <<'CHECKSUMS'
c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539  tokenizer.json
5b5d4f65d0acd3b2d56a35b56d374a36cbc1c8fa5cf3b3febbbfabf22f359583  tokenizer_config.json
c20b638ca82b21d04fe12e14ff417ad05153d4d215a65de54497fca4e972f7c6  hotpot-validation.parquet
CHECKSUMS
)

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 "$p0_tmp/venv/bin/python" -B exp/v3/p0/audit.py \
  --tokenizer "$p0_tmp" --validation "$p0_tmp/hotpot-validation.parquet" \
  --preflight exp/v3/preflight --out "$p0_tmp/output"
cmp exp/v3/p0/length_audit.csv "$p0_tmp/output/length_audit.csv"
```

两份 Qwen tokenizer 文件按固定 Hub revision 下载。Parquet 的 Hub 转换分支可能更新，SHA-256 不一致时保留差异并核对快照后再复跑。复跑的清单包含实际扫描范围，可能因历史副本和目录结构而变化。V2 归档身份与评分回放命令见[原复现清单](../../v2/step6_v2/Reproducibility_Checklist.md)。若系统需要使用系统证书访问 PyPI，可按本次运行改用 `uv --native-tls pip install`。

## GPU 容量复跑

`pack_capacity_cases.py` 从 P1 已锁定的长度和池工件中为 4096、8192、16384 分别重建 10、30、60 段档最长的 8 条完整问答提示。组内按总长降序、题号升序，逐条检查有序池及提示词哈希。该工件只带问题、原文及追溯 ID。

```bash
# 在有固定 rank_bm25 的本地仓库根导出
python3 -B exp/v3/p0/pack_capacity_cases.py --out /tmp/group13-p0-capacity-cases.json

# 在具有固定 vLLM 环境的 GPU 主机运行，以下文件从本地复制
python3 -B run_capacity.py --model "$P0_QWEN_SNAPSHOT" \
  --cases capacity-cases.json --out live-p0 \
  --caps 4096 8192 16384 --cpu-offload 4
```

执行器运行 loopback 服务，每个档位保存一个真实最长提示、一个满长合成请求及一组 8 条真实提示的同时提交。每条运行核对服务返回的实际输入 token，保留峰值显存和调度器采样。每个档位只终止执行器自己启动的服务。16384 用 4 GiB 启动失败后，按 `--caps 16384 --cpu-offload 6` 在新输出目录复测通过。比较质量和完整管线成本由 P1.5 另测。[实际配置及原始证据](gpu_runtime.md)

### 单项探测

依照[归档启动脚本](../../v2/step4_dev/.serve-step4.sh)核对四个权重分片。服务以 loopback 启动，保留原版 FP16 模型。分别对测试档位设置 `--max-model-len`，锁定其余启动条件并记录 `--max-num-seqs`、硬件和软件身份。先测 4096 和 8192，需覆盖 8192 容纳不了的 60 段全文时再测 16384。若转用 Kaggle Transformers，单独登记跨卡布局、显存与同步计时，不沿用 vLLM 并发约定。

在 GPU 机器上，启动前记录一次 `nvidia-smi`，然后在另一个终端持续采样。下面的探测只发合成 token，覆盖 128 token 输出预算，核对服务报告的输入输出和墙钟。示例以已在 loopback 运行的 8192 配置为例。

```bash
nvidia-smi --query-gpu=timestamp,index,name,memory.total,memory.used \
  --format=csv -lms 200 > p0-gpu-8192.csv
```

```bash
python3 -B exp/v3/p0/probe_vllm.py --tokenizer "$verified_tokenizer_path" \
  --context 8192 --parallel 1 > p0-vllm-8192-1.json
python3 -B exp/v3/p0/probe_vllm.py --tokenizer "$verified_tokenizer_path" \
  --context 8192 --parallel 8 > p0-vllm-8192-8.json
```

`verified_tokenizer_path` 指上述固定版本的 `tokenizer.json`。采样时同时从本地 `/metrics` 记录 scheduler running/waiting 和 GPU cache usage，并保留服务日志。对 30 段、60 段另验证真实开发题问答输入，按 P1 锁定池的最长值可分别用 **5420**、**10828** 个输入 token 加 **128** 个输出 token 做容量参照。客户端并发 8 表示同批提交，正在执行的请求数以调度器为准。按[在线测量复核口径](resource_estimate.md#在线测量复核口径)更新共同范围。

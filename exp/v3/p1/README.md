# V3.1 · P1 数据交付

2026-11-16。**P1 候选池、金标隔离、证据位置和离线长度检查已完成。** 后续 [P0 实机验收](../p0/gpu_runtime.md) 已在所供 GPU 上通过，基于本候选池的 [P1.5 策略对照](../p1_5/REPORT.md) 也已完成。

| 产物 | 内容 |
|---|---|
| [data_audit.md](data_audit.md) | 50 题选取口径、语料来源、近重复和答案短语审计、证据位置与数据划分。 |
| [resource_estimate.md](resource_estimate.md) | 实际模板下的共同题集、排除条件、共享生成工作量和 GPU 验证范围。 |
| [pools.jsonl](artifacts/pools.jsonl) | 已锁定的 150 个在线输入，包含按固定顺序排列的资料和定位 ID。 |
| [provenance.jsonl](artifacts/provenance.jsonl) · [pool_manifest.json](artifacts/pool_manifest.json) | 段落来源和入池方式、输入与产物 SHA-256、跳过的归档题。 |
| [split_plan.json](artifacts/split_plan.json) | 50 道工程开发题和条件性门控训练／验证题 ID。最终集仍待确定。 |
| [length_audit.csv](artifacts/length_audit.csv) · [length_manifest.json](artifacts/length_manifest.json) | 1,050 条完整提示长度、输入和池哈希、各上限适用和排除的题号。 |
| [evaluation_only/](artifacts/evaluation_only) | 答案、HotpotQA 支持句、位置记录和匹配案卷。由离线评价器单独读取。 |

在线程序从 `pools.jsonl` 取 `row["input"]`。该层只有 `question` 和 `contexts`，每段含 `chunk_id`、标题和带 `sentence_id` 的原句；`qid`、池规模和有序池哈希是外层实验元数据。每个实验策略使用相同的 `(qid, pool_size, pool_sha256)`。用于复核的出处和金标分别读取对应的本地文件。

## 复建

在仓库根运行。准备 [P0 的 tokenizer 和环境](../p0/README.md#复跑离线审计)（Python 3.13、PyArrow 21.0.0、rank_bm25 0.2.2、Transformers 4.51.3、tokenizers 0.21.4）。`P1_PYTHON` 指向该环境解释器，`P1_TOKENIZER_DIR` 指向经 P0 验证、含 `tokenizer.json` 与 `tokenizer_config.json` 的目录。抓取固定版本的训练分片和只用于 ID 审计的验证分片，由构建脚本核对输入哈希。

```bash
set -e
p1_download=$(mktemp -d)
p1_hub='https://huggingface.co/datasets/hotpotqa/hotpot_qa/resolve/14f0ace3c3fac7bd86149c616b5b05d8282e5c6a/distractor'
for shard in 0000.parquet 0001.parquet; do
  curl -fLsS --retry 2 "$p1_hub/train/$shard" -o "$p1_download/$shard"
done
curl -fLsS "$p1_hub/validation/0000.parquet" -o "$p1_download/validation.parquet"

"$P1_PYTHON" -B exp/v3/p1/build_pools.py \
  --train-dir "$p1_download" --validation "$p1_download/validation.parquet" \
  --out "$p1_download/output"
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 "$P1_PYTHON" -B exp/v3/p1/audit_lengths.py \
  --tokenizer "$P1_TOKENIZER_DIR" --artifacts "$p1_download/output"
diff -qr exp/v3/p1/artifacts "$p1_download/output"
```

源码身份与历史 V2 归档见 [P0 源码映射](../p0/source_map.md)。输入资料为 HotpotQA，使用 CC BY-SA 4.0；发布或另行分发时保留 [HotpotQA 归属与许可证](https://hotpotqa.github.io/)。

# Group 13 V3.1 · P1.5 能力与成本预检

本阶段在 P1 冻结的 50 道历史开发题上验证基础检索与补查分支的空间。8192／4 GiB 服务用于 10、30 段主比较，16384／6 GiB 服务用于 60 段诊断。方法质量及成本在各自服务内比较。**全部 1,200 条路径已生成、回收并评分。** 见 [P1.5 结果与下一阶段决策](REPORT.md)、[运行日志](../EXPERIMENT_LOG.md)、[锁定协议](protocol.json)及 [原始工件清单](remote-evidence/evidence.sha256)。

| 路径 | 实际生成顺序 |
|---|---|
| 固定 BM25 top-2、top-4、top-6 | 按问题检索，一次生成 |
| Full | 在 P1 固定顺序下读完整池，一次生成 |
| V2 直读 2+1 | 按原规则补检索，把合并的三段交给模型一次生成 |
| 两阶段 2+1、2+2、2+4 | 先按 top-2 实际生成草稿，再根据 V2 原查询规则补检索一次，合并资料再生成 |

V2 的二次查询使用问题、首段标题和首句，在未读段落上重建 BM25。它无需读草稿，单次和两阶段的最终 2+1 提示具有同一哈希。两条路径各自真实运行，以分别记录开销与偶发输出差异。A/B Oracle 的 A 为共享固定 top-2，B 为相应路径的最终回答。另用该路径自己首轮回答作敏感性参考。NLI、Fuzzy、句级选择器和封存测试集均不属于本次运行。

## 复跑

GPU 只接收 P1 的 `pools.jsonl` 和 `length_audit.csv`、本目录的 `protocol.json` 与 `run.py`、V2 的 `compare_models.py` 和 `bm25_topk.py`。服务器端使用 P0 验证的 vLLM 包和权重，监听 `127.0.0.1:18081`。实跑 shell 记录在原始归档。检测到途中失败时，可在与原运行一致的服务上用同一命令继续，日志保留失败，并跳过已完成的同一哈希路径。

```bash
python3 -B bundle/run.py --v2 bundle/v2 --pools bundle/pools.jsonl \
  --lengths bundle/length_audit.csv --cap 8192 --out results/8192
# 使用对应的 16384／6 GiB 服务，再运行 60 段
python3 -B bundle/run.py --v2 bundle/v2 --pools bundle/pools.jsonl \
  --lengths bundle/length_audit.csv --cap 16384 --out results/16384
```

本地离线评价命令使用 P0 的 Python 依赖环境在仓库根运行。只有该步骤读取 P1 的独立 gold 文件。输出包含官方 EM/F1、逐题标题检索及引用召回、真实路径的累计模型输入／输出 token、时延分位数、A/B Oracle 和对 Full 的配对差值。

```bash
bash exp/v3/p1_5/collect.sh "$P15_CONTROL_SOCKET" "$P15_SSH_TARGET" \
  exp/v3/p1_5/remote-evidence
python3 -B exp/v3/p1_5/evaluate.py --raw exp/v3/p1_5/remote-evidence/results \
  --out exp/v3/p1_5/analysis
Rscript --vanilla exp/v3/p1_5/plot_quality_cost.R \
  exp/v3/p1_5/analysis/strategy_metrics.csv exp/v3/p1_5/analysis/quality_cost.png
```

会话断开后，先检查远端 `results/8192/complete.json`、`results/16384/complete.json`、`status` 和正在运行的 tmux 会话。回收器要求两档已完整结束。若只缺少部分路径，按相同的服务配置和已有结果目录调用执行器，避免覆盖成功记录或跨配置复用时间。

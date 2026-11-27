# 后续实验

这些实验沿用 HotpotQA 的桥接题，候选池构造、基础模型和评分器见 [V3.1](../exp/v3/README.md)。原题与原文来源见 [第三方实验材料](../docs/THIRD_PARTY.md)。

| 实验 | 范围 | 结果 |
| --- | --- | --- |
| 逐条件 NLI 核验 | 30 道开发题。对比整题核验与逐条件核验 | [条件核验](nli-condition-pilot-20261122/summary.json) · [自动抽取](nli-condition-pilot-20261122/auto/summary.json) |
| 约束信号与门控 | 对比含约束信号的 Sugeno 和线性收益回归，并做固定阈值预检 | [开发结果](constraint-aware-gate-20261122/summary.json) · [早期验证](constraint-aware-gate-20261122/fresh/summary.json) |
| 日期规则修正与独立校准 | 40 题校准阈值，60 道新题使用固定阈值 | [方案](constraint-gate-calibrated-20261122/protocol.json) · [验证结果](constraint-gate-calibrated-20261122/test/summary.json) · [引用评测](constraint-gate-calibrated-20261122/citation-audit/summary.json) |
| 桥接实体定向补查 | 在既有测试集回放检索，对已触发补查的 8 题重新生成与提取引用 | [检索回放](evidence-retrieval-diagnosis-20261122/summary.json) · [重新推理结果](evidence-retrieval-diagnosis-20261122/answer_summary.json) |

在 60 道独立验证题上，修正版与旧版 Sugeno 的答案 F1 均为 42.27%，支持句 F1 均为 49.30%。补查从 11 次降至 8 次。计入 Qwen 作答与引用提取，平均输入从 781.67 降至 724.07 token，减少 7.37%。三道题的决策发生变化。桥接实体补查的 8 次实际重跑中，答案 F1 持平。

## 从归档结果复算

在仓库根目录运行下列命令。复算以记录的模型输出和证据为输入，并更新各目录的统计文件。

```sh
python3 experiments/constraint-gate-calibrated-20261122/score.py calibration
python3 experiments/constraint-gate-calibrated-20261122/score.py test
python3 experiments/constraint-gate-calibrated-20261122/citation-audit/score_citations.py
python3 experiments/evidence-retrieval-diagnosis-20261122/replay.py
python3 experiments/evidence-retrieval-diagnosis-20261122/score_bridges.py
```

检索回放需要 `rank-bm25==0.2.2` 和 NumPy。重新拟合门控需要 NumPy。若需要重新抽样，将 [P1 固定版本的 Parquet 文件](../exp/v3/p1/README.md) 放到 `experiments/constraint-aware-gate-20261122/data/`，再在单独的工作副本运行 `prepare.py`。重新生成模型输出需要 [P5 运行环境](../exp/v3/RUNBOOK.md) 和各实验方案锁定的模型快照。

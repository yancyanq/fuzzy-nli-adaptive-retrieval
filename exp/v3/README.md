# V3.1 扩展候选池实验

V3.1 扩展每题候选段落数，测量补查路径的收益和成本，验证关系级证据核验，并试训预测逐题补查收益的 Sugeno 门控。P0 至 P5 已完成；60 道引用充分性盲审（其中 20 道双人复核）尚未回收。

**[实验方案](protocol/README.md) · [实验过程与复现](RUNBOOK.md) · [阶段结果总表](RESULTS.md) · [参数索引](PARAMETERS.md) · [实验日志](../EXPERIMENT_LOG.md)**

| 阶段 | 内容 | 主要材料 |
| --- | --- | --- |
| 早期 Kaggle 预检 | 10 题短答、CPU NLI 冒烟，以及 50 题检索压力测试 | [Notebook 与导出](preflight/) · [预检报告](preflight/运行结果与开发交接.md) |
| P0 | V2 复用审计、数据身份、提示长度与 4,096／8,192／16,384 token 容量试验 | [说明](p0/README.md) · [实机验收](p0/gpu_runtime.md) |
| P1 | 50 道开发题各构建 10／30／60 段嵌套候选池，离线记录金标与出处 | [数据说明](p1/README.md) · [数据工件](p1/artifacts/) |
| P1.5 | 八种路径在三个池规模上的 1,200 条开发测量 | [正式预检报告](p1_5/REPORT.md) · [逐题与策略结果](p1_5/analysis/) |
| P2 | 关系抽取、整题与局部 NLI、约束复测、直读对照和人工复核 | [核验报告](p2/REPORT.md) · [复核与复算](p2/review-guided/) |
| P3 | 基于原查询的 100 训练／50 验证题 A/B 试跑、特征、增量和成本 | [试跑报告](p3/REPORT.md) · [离线结果](p3/analysis/) |
| P4 | 18 组拟合的权重与轨迹、验证预算曲线、配对区间 | [验证报告](p4/validation_report.md) · [离线结果](p4/analysis/) |
| P5 | 300 道封存题的正式评估、配对区间、质量–成本曲线、盲审材料与实测计时 | [正式报告](p5/REPORT.md) · [配对区间](p5/analysis/paired_intervals.csv) · [盲审](p5/blind-review/) |

[项目首页](../../README.md) · [V2 正式结果](../../docs/RESULTS.md) · [下载 V3.1 完整材料 ZIP](../../sources/NLP_Experiment_Materials_V3_1_Public.zip)

数据及补充候选段落来自 HotpotQA distractor。归档按题保留来源和句子编号。 [数据来源与许可](../../docs/THIRD_PARTY.md) · [公有数据来源与候选池清单](p1/artifacts/pool_manifest.json)

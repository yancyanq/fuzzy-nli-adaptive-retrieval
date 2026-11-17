# V3.1 阶段参数与版本索引

| 阶段 | 归档设置 | 精确来源 |
| --- | --- | --- |
| P0 容量 | Qwen2.5-7B-Instruct 固定 revision、FP16、vLLM 0.8.5、最大并发序列 8。4,096／8,192 使用 4 GiB CPU offload，16,384 通过配置使用 6 GiB。 | [运行环境与容量证据](p0/gpu_runtime.md) · [数据与 tokenizer 清单](p0/manifest.json) |
| P1 候选池 | 50 道历史开发题。保留原始段落，新增词法和随机干扰各半。输入池、出处和 gold 分文件。 | [构建配置](p1/config.json) · [池清单](p1/artifacts/pool_manifest.json) |
| P1.5 策略 | 10／30／60 段池。固定 top-2／4／6、Full、V2 直读 2+1 及两阶段 2+1／2+2／2+4。作答温度 0，每次预留 128 输出 token。 | [预检协议](p1_5/protocol.json) |
| P2 核验 | 50 道 30 段池开发题。关系级 NLI 每题最多 4 次，每次 512 token。排序预算 10/50，人工关系忠实率门槛 90%。 | [核验协议](p2/protocol.json) · [核验报告](p2/REPORT.md) |
| P3 回退 | 100 道训练题和 50 道验证题。A 用 BM25 top-2，B 沿用 V2 查询追加 4 段。特征取首轮整题 NLI 风险和桥接缺失。 | [试跑协议](p3/protocol.json) · [题号清单](p3/input/cohorts.json) |
| P4 试训 | CPU 单线程，float32，Adam，batch 32，学习率 0.01，最多 300 轮，早停耐心 30。两种变体、三档 L2、三个种子，共 18 组拟合。 | [训练协议](p4/protocol.json) · [模型规范](p4/remote-evidence/output/model_spec.json) |

预定的扩大规模与最终比较写在[训练规范](protocol/TRAINING_SPEC.md)中。已执行的配置及偏离方案的回退依据见各阶段报告和[实验日志](EXPERIMENT_LOG.md)。

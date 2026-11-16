# Protocol V2 正式实验归档

本目录覆盖 V2 §7.3 补充 pilot 和 §10.1 步骤 4–6。阶段状态见[实验日志](../EXPERIMENT_LOG.md)，论文数字见[结果总表](../../docs/RESULTS.md)。

| 位置 | 内容 |
| --- | --- |
| [pilot_signals_v2/](pilot_signals_v2/) | 补充信号比较的 [摘要](pilot_signals_v2/summary.json)和[逐题选题](pilot_signals_v2/per_question_selection.csv) |
| [step4_dev/](step4_dev/) | 500 题 A/B 答案、NLI 评分、[门控锁](step4_dev/gates/locked_gates.json)、[校准摘要](step4_dev/gates/dev_summary.json)、逐题选择、启动配置和校验清单 |
| [step5_v2/](step5_v2/) | 正式 1,000 题的 A/B/Full-context 答案、句级证据、NLI 缓存、九组预测、[质量汇总](step5_v2/quality_summary.json)、[真实路径成本](step5_v2/latency_summary.json)与运行记录 |
| [step6_v2/](step6_v2/) | [正式报告](step6_v2/Experiment_Report.md)、[配对区间](step6_v2/paired_bootstrap.csv)、[错误分析](step6_v2/Error_Analysis.md)、[可复现性清单](step6_v2/Reproducibility_Checklist.md)、图表、论文预览与 LaTeX、[中文结果册](step6_v2/NLP_V2_Section11_Results_Booklet.docx) |
| [case_review/](case_review/) | 代表案例的空白复核模板和含填写内容的副本。[实验日志](../EXPERIMENT_LOG.md?plain=1#L653)记录返表核对，意见用于三例定性复核 |
| [test.json](test.json)、[tune.json](tune.json) | 锁定的正式集及 dev 输入。`tune.json` 与早期归档版本逐字节相同。Pilot 输入位于 [step1/pilot.json](../step1/pilot.json) |

历史校验清单使用同目录脚本及相对路径。这里保留正式运行依赖的四份早期模块（`bm25_topk.py`、`compare_models.py`、`run_pilot.py`、`analyze_signals.py`）和 `tune.json` 的原样副本，便于逐字节验证锁文件。GPU 端输入清单保留当时的部署路径，离线回放使用[本地可复现性清单](step6_v2/Reproducibility_Checklist.md)中的命令。

[实验过程手册](step6_v2/NLP_V2_Experiment_Process_Handbook.md)覆盖从准备到复算的各步骤。[完整结论](step6_v2/NLP_V2_Experiment_Conclusions.md)对应 RQ1–RQ3。[关键参数与选择依据](step6_v2/NLP_V2_Experiment_Parameters.md)列出实际设置及其取舍。Word 原件与 Markdown 对照见[实验文档](../../docs/DOCUMENTS.md)。

## 本地验证

从仓库根目录进入 `exp/v2`。使用 Python 3.10 或以上及独立虚拟环境。测试使用合成数据或本地 HTTP mock，复用仓库中的 Step 3 mock。

```bash
cd exp/v2
python -m pip install openai==1.76.2 rank-bm25==0.2.2 numpy reportlab
python -m unittest -v
shasum -a 256 -c step6_v2/reproducibility.sha256
(cd step4_dev && shasum -a 256 -c results.sha256)
shasum -a 256 -c step5_v2/archive.sha256
```

- [补充 pilot](README_pilot_signals_v2.md)离线读取早期 pilot 导出；[步骤 4](README_step4_v2.md)记录 GPU 生成与门控校准；[步骤 5](README_step5_v2.md)记录正式运行和 GPU 环境。
- [步骤 6](README_step6_v2.md)给出离线统计与 LaTeX 复编译命令。[可复现性清单](step6_v2/Reproducibility_Checklist.md)演示如何把回放输出写入临时目录并与归档逐项比对。
- GPU 工作流另用固定 Qwen、DeBERTa、vLLM、PyTorch 和 Transformers。启用 vLLM 鉴权时通过环境提供 `VLLM_API_KEY`，本次归档的 loopback 配置无需鉴权。模型权重和服务器虚拟环境由运行设备管理。

原始缓存、技术运行日志、哈希清单和结果产物按原样归档，便于核验。实验日志的网页展示版隐藏执行日期和时刻。

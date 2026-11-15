# 记录进度与归档产物

## 实验负责人

1. 在仓库外的原始实验日志末尾追加实验、决定或复核记录。准备、实测和后续决定分别写成二级标题，既有记录保留原文。
2. 在日志记下数据切分、命令和版本、实验指标、结论、输出文件及尚待确认的事项。设置必须注明实际决定时间。真实运行完成后，将已复核的输出复制到相应步骤的目录，并更新 [INDEX](../INDEX.md)、[结果表](RESULTS.md) 或 [缺口清单](GAPS.md) 中受影响的内容。
3. 将日志、已复核材料和受影响的文档一并提交。原始密钥、令牌、环境配置和模型下载缓存留在本机。需要提交 API 缓存时，先核对它属于已批准的记录，检查授权头、异常响应和凭据字段。

## 进度页

同步脚本从仓库外的原始日志生成[实验日志](../exp/EXPERIMENT_LOG.md)和[进度页](../PROGRESS.md)，展示条目保留实验顺序和出处。用 `--source-log` 指向原始日志。两份日志出现分叉时，先人工核对再同步。

```bash
python tools/sync_progress.py --source-log "/path/to/local-project/exp/EXPERIMENT_LOG.md"
git diff -- exp/EXPERIMENT_LOG.md PROGRESS.md
git add exp/EXPERIMENT_LOG.md PROGRESS.md
git commit -m "docs: record experiment progress"
git push
```

自动同步的范围为仓库展示的实验日志与进度页。实验数据、缓存、报告和文档由负责人复核后提交；文件写入期间先等待产物完整。本地同步依赖 Mac 上的工作区、GitHub 登录和网络。

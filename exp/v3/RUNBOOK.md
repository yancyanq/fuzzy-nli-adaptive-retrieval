# V3.1 实验过程与离线复现

1. **审计容量和已有数据。** 用固定 tokenizer 读回 V2 和早期预检的长度记录。分别验证三档 vLLM 上限，从 P0 取得已验证的服务配置。 [P0 过程](p0/README.md)
2. **冻结扩展候选池。** P1 构建 10／30／60 段池，锁定题号、顺序和材料哈希。在线路径使用问题和候选段落，标准答案及支持信息供事后评分。 [P1 过程](p1/README.md)
3. **测量补查空间和调用成本。** P1.5 对同一批题运行八种路径，记录答案质量、累计 token 和实际延迟。P2 追加同材料单次直读、关系抽取、自检和人工复核。 [P1.5 过程](p1_5/README.md) · [P2 过程](p2/README.md)
4. **复用可运行的回退路径。** P2 未达到忠实率门槛后，P3 使用 V2 原查询、整题 NLI 与桥接特征完成 100／50 题试跑。P4 用 P3 首轮特征及离线收益试训，比较完整 Sugeno、仅训练后件、线性收益回归与固定策略。 [P3 过程](p3/REPORT.md) · [P4 过程](p4/validation_report.md)

## 从归档复算

从仓库根目录运行。离线评分使用 Python 3.13 与 [P0 固定的依赖](p0/README.md#复跑离线审计)。下面的命令从已保存响应重算，并把新输出放在临时目录。

```bash
replay_dir=$(mktemp -d)
python3.13 -B exp/v3/p1_5/evaluate.py \
  --raw exp/v3/p1_5/remote-evidence/results --out "$replay_dir/p15"
python3.13 -B exp/v3/p2/evaluate.py \
  --raw exp/v3/p2/remote-evidence --out "$replay_dir/p2-first"
python3.13 -B exp/v3/p2/evaluate.py \
  --raw exp/v3/p2/remote-evidence --guided exp/v3/p2/guided-evidence \
  --example-free exp/v3/p2/example-free-evidence --out "$replay_dir/p2-guided"
python3.13 -B exp/v3/p2/check_human.py \
  --template exp/v3/p2/review-guided/human_ratings.tsv \
  --ratings exp/v3/p2/review-guided/human_ratings_AI_assisted.tsv \
  --nli exp/v3/p2/guided-evidence/live-nli/nli.jsonl > "$replay_dir/p2-human.json"
python3.13 -B exp/v3/p3/evaluate.py --out "$replay_dir/p3-dev"
python3.13 -B exp/v3/p3/evaluate.py \
  --raw exp/v3/p3/remote-evidence --out "$replay_dir/p3-smoke"
python3.13 -B exp/v3/p4/evaluate.py \
  --raw exp/v3/p4/remote-evidence/output --out "$replay_dir/p4"
```

P1.5 的 5 份评分文件、P2 的 6 份、P3 的 6 份和 P4 的 3 份与归档逐字节一致。P2 人工复核脚本的输出对应 assessment.json 里的 assessment 字段。P4 此处回放保存的预测，训练权重的独立重跑情况见[验证报告](p4/validation_report.md#训练与复现)。

阶段目录中的证据清单用于核对原始运行记录。完整版 ZIP 另有根目录 SHA-256 文件，覆盖 ZIP 中的 V3.1 材料及复跑所借用的 V2 文件。

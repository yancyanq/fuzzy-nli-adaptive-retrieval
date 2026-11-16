# V2 第 7.3 节 · Pilot 信号比较

这一步读取 Step 5 的同一批 100 道 pilot 题及缓存。两种方法各选 20 题，比较实际选中的 `improved`、`tie` 和 `degraded` 题数。20% 与等权组合是查看原 pilot 汇总后、在本次补充比较前确认的设置。正式门控参数在 dev 阶段确定。

## 文件和运行环境

将 `analyze_pilot_signals_v2.py`、`compare_models.py`、`analyze_signals.py` 和 `bm25_topk.py` 放在同一目录。输入是原始 `pilot.json` 和同一次真实 Step 5 运行的 `branches.jsonl`、`per_question.csv`。三个文件必须包含同一批 100 个唯一标识。

本步使用 Python 3.10 或更高版本。复用的 `compare_models.py` 导入时需要 `rank_bm25`。安装依赖后，本步离线读取数据，无需设置 API key 或连接 GPU。

```bash
python -m pip install rank-bm25==0.2.2
```

## 运行命令

在本仓库的 `exp/v2` 目录执行，选择一个尚不存在的输出目录

```bash
python3 analyze_pilot_signals_v2.py --pilot ../step1/pilot.json --branches ../step5/step5_pilot/branches.jsonl --per-question ../step5/step5_pilot/per_question.csv --out ../../runs/v2_pilot_signals
```

YangQS 工作区根目录（PowerShell）

```powershell
Set-Location G:\NLP_project
python analyze_pilot_signals_v2.py --pilot pilot.json --branches step5_pilot/branches.jsonl --per-question step5_pilot/per_question.csv --out pilot_signals_v2
```

如需重新核对，指定一个新输出目录。脚本在已有输出路径上会退出，避免覆盖既有记录。

## 判定与结果

NLI 排序以较低的 A 支 entailment 为更高风险。桥接信号检查首轮两个段落，双向判定一段正文句子是否含另一段完整标题。文本统一用 Unicode NFKC、大小写折叠及整词匹配。组合排序等权平均两个风险百分位，同分取平均名次。桥接信号缺失时用该题的 NLI 风险百分位。选题边界同分按固定种子 42 与题目 ID 的 SHA-256 顺序处理。

- `summary.json` 保存实际再检索率、各方法选题类别数、组合减去 NLI 的差值、均匀随机抽取 20 题时的理论期望，以及输入文件的校验和。
- `per_question_selection.csv` 保存每题的两个排序分数和选题结果。`bridge_link` 为 1 表示命中，为 0 表示未命中，空值表示无可用桥接信号。`bridge_matches` 的每个三元组依次是源段落、目标段落及源句的索引，索引从 0 开始。

## 测试

在本仓库的 `exp/v2` 目录执行，测试复用 `../step3/test_mock_server.py`。

```bash
python3 -m unittest -v test_pilot_signals_v2
```

测试用原 Step 3 mock 生成合成答案，在本地构造测试缓存。测试中的数字都是假数据。

# V2 步骤 6

步骤 6 从本仓库的 `exp/v2` 目录离线读取步骤 5 的原始答题、证据、逐题分数、质量和成本文件。运行需要 Python 3.10 或以上，以及 `rank-bm25`、`numpy`、`reportlab`。不需要设置 API 环境变量。

```bash
cd exp/v2
shasum -a 256 -c step5_v2/archive.sha256
python3 -m unittest -v test_analyze_step6_v2
python3 analyze_step6_v2.py --test test.json --results step5_v2 --out ../../runs/v2_analysis
```

- `step6_summary.json` 和 `paired_bootstrap.csv` 保存五组预登记对比、估计值和区间端点。CSV 的 F1 单位为 0–1，乘 100 即得到百分点。
- `error_audit_cases.json` 保存固定哈希抽得的 22 题和两支证据。与 `Error_Analysis.md` 一起使用。正式集案例是主结果可见后的探索性审读，预实验的人工标签记录在实验日志。
- `quality_cost.pdf` 是 §11.5 三面板图。 `Experiment_Report.md` 汇总 V2 §11–§12、原始预实验、结论及局限。
- `Methodology_and_Experimental_Results.pdf` 是 10 pt IEEEtran 双栏预览。合并时将 `paper_sections.tex` 接在论文第 II 节之后，并带上 `paper_tables.tex` 和 `quality_cost.pdf`。将预览入口的参考文献条目按全稿的引用顺序合并。

若本机的 TeX 已包含 IEEEtran，以下命令可在论文预览目录复编译。

```bash
cd step6_v2
latexmk -pdf -interaction=nonstopmode -halt-on-error Methodology_and_Experimental_Results.tex
```

本次使用 CTAN 的 IEEEtran 1.8b 文档类，通过临时目录中的 `TEXINPUTS` 加入搜索路径。分析和版面核验信息见 `exp/EXPERIMENT_LOG.md`。

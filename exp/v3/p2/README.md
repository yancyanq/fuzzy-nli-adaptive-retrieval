# Group 13 V3.1 · P2 关系与证据核验

同一组 30 段池的 50 道开发题复用 P1.5 真实的 top-2 草稿、引用及 A/B 输出。核验阶段传入问题、首轮两段原文、草稿和引用。独立直读 2+2／2+4 的 Qwen 执行器读取同一冻结池。 [P2 固定协议](protocol.json) · [结果报告](REPORT.md) · [实验日志](../EXPERIMENT_LOG.md)

## 信号口径

- **旧整题**复用 V2 的文本拼接、草稿命题和锁定的桥接代理。核验结果保留原输入长度、实际输入长度、截断和 E/N/C。
- **关系级**校验 1–4 条必要关系，以句子 ID 锁定原文。模型输出歧义与缺失，程序拒绝不可定位的编号。每题至多 4 次 CPU NLI，每次 512 token。局部证据超限按句界分束，整条关系需要共同支撑时，只用覆盖判定所需锚点的完整证据束。整题回退和无局部可用关系的原因另存。
- **相同预算对照**统一选 10/50 题，使用冻结的实际 `F1(B)−F1(A)` 做离线诊断。Qwen 自检是预先规定的 0–3 风险序数。关系风险、缺口、平均合成信号与旧整题风险和桥接代理分别报告。没有调整选择比例、拟合权重或接触正式集。
- **修正完整保留**。首次自由生成与第二次约束生成采用独立目录。API 请求 XGrammar，vLLM 日志显示该 schema 转由 Outlines 执行。第二次允许的原文 ID 由该题实际两段生成，关系编号由列表顺序分配，重复引用按出现顺序去重。保留原始响应，原直读对照只跑一次。去示例自检单独保存，分数范围及相同预算口径沿用首轮。

## 人工抽查

盲审包包含原文、首答、V2 整题命题、结构化候选和局部证据束，隐藏金标、B 分支、选择结果及机器分数。例子是开发题。保留原始空白表，在副本填写：

- `whole` 行填写 `support`，选 entailment、neutral、contradiction、unknown。
- `question` 行填写 `coverage`，选 complete、incomplete、unknown。
- `relation` 行填写 `faithful`，选 yes、no、unknown，并对完整的局部证据束填写同一组 `support` 标签。如果证据束被分开、无可评证据或无法判定，则填写 `support=unknown`。判断 `faithful` 时仍可独立评价结构化关系是否表达了问题所需的一步。
- 写上 `reviewer` 和有用的 `notes`。若出现跳错实体、改写不忠实或覆盖不完整，请说明对应关系或原文编号。正式判定需至少 20 道完整人工评审，并单列未知和未评数。

评价程序接收人工填写表和固定模板后核对题号，计算确定性标注的忠实率。整题基线发生截断的条目保留为人工记录，单独排除出同输入一致性分母。

```bash
python3 -B exp/v3/p2/check_human.py --template exp/v3/p2/review-guided/human_ratings.tsv \
  --ratings "$P2_COMPLETED_REVIEW" --nli exp/v3/p2/guided-evidence/live-nli/nli.jsonl
```

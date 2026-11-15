# Experiment Log — Fuzzy-NLI QA Chatbot (Adaptive Retrieval)

Protocol: /workspace/lr/Experiment_Protocol_v2.docx (status: 通过预实验，正式方案待锁定)
Times in Asia/Shanghai (UTC+8).

## 2026-11-14 — Step 1: Data source decided
- Decision: use Hugging Face `hotpotqa/hotpot_qa`, config `distractor`, split `validation` (official dev set; test answers not public).
- Reason (user choice): easy loading/splitting with `datasets`; will convert to official JSON format for `hotpot_evaluate_v1.py`.
- Planned processing: filter `type == "bridge"`, shuffle with fixed seed (42, proposed), split into disjoint pilot / tune / test; sizes 【待确认】(example: 100 / 500 / 1000).
- Alternatives considered: official site JSON (`hotpot_dev_distractor_v1.json`); BEIR/KILT/FlashRAG versions rejected (no per-question 10-paragraph distractor pool).
- Status: guidance given to user (load, filter, split, convert code). Not yet executed.

## 2026-11-14 21:30 — Step 1 executed: Data split (run by user on device YangQS)
- Source: HF `hotpotqa/hotpot_qa`, config `distractor`, split `validation`; Parquet downloaded via mirror, SHA-256 verified.
- Validation total: 7,405 questions; bridge: 5,918.
- Filter type == bridge, shuffle seed 42, sequential split:
  - pilot.json — 100 (pre-experiment) — G:/NLP_project/pilot.json
  - tune.json — 500 (tuning) — G:/NLP_project/tune.json
  - test.json — 1,000 (formal test) — G:/NLP_project/test.json
- Format: official HotpotQA JSON (UTF-8), for hotpot_evaluate_v1.py.
- Checks: re-read all three files; all bridge; 1,600 `_id` unique (disjoint).
- Note: some questions have fewer than 10 context paragraphs; kept as original (affects top-k / unused-paragraph pool in round 2 — handle in retrieval code and report in paper).
- Sizes follow the example values; formal test size still subject to protocol 7.4 (budget / effect size).

## 2026-11-14 21:40 — Step 2 prepared: BM25 top-k recall script (verification run on my box)
- Script: /workspace/exp/step2/bm25_topk.py (rank_bm25 BM25Okapi; lowercase alnum tokens, small stopword list).
- Round 1: query = question; rank the question's own context paragraphs (title + sentences); take top-k.
- Round 2 rule rewrite: query = question + title + first sentence of round-1 top-1 paragraph; rank only unused paragraphs; add top-m.
- Gold = titles in supporting_facts. Metrics: mean gold-paragraph recall, both-gold rate, % questions where round 2 adds a gold paragraph, % with no unused paragraphs.
- Box verification run: rebuilt pilot (bridge, seed 42, first 100) from HF; same procedure as user's — expected identical to G:/NLP_project/pilot.json but NOT yet confirmed against user's file.
- Box results (100 pilot questions), m=1:
  k=2: R1 recall .635, both .310 | R2 recall .785, both .590, gain 30%
  k=3: R1 recall .710, both .450 | R2 recall .830, both .670, gain 24%
  k=4: R1 recall .755, both .540 | R2 recall .885, both .770, gain 26%
  m=2: k=2 R2 .845/.700 gain 42%; k=3 R2 .880/.770 gain 33%; k=4 R2 .920/.840 gain 31%
- Status: awaiting user's official run on YangQS to confirm; k and m not yet decided.

## 2026-11-14 21:41 — Step 2 executed on YangQS (official run)
- User ran original bm25_topk.py on G:/NLP_project/pilot.json, m=1 and m=2.
- Results identical to box verification run (all metrics match) → box pilot == user pilot confirmed.
- Outputs: G:/NLP_project/step2_m1/{summary.json,per_question.csv}, G:/NLP_project/step2_m2/{...}; each 300 rows (100 q × 3 k), checked.
- No question lacked unused paragraphs at k≤4.
- Decision on k, m: pending.

## 2026-11-14 21:43 — Decision: k=2, m=1 (user approved)
- Round 1 top-k = 2; round 2 adds m = 1 paragraph from unused pool via rule rewrite.
- Rationale: lowest R1 both-gold (31%) → most headroom; highest R2-gain share (30%); equal-budget check: k=2+m=1 (3 paras) both-gold 59% vs k=3 single-shot 45% → rewrite adds value beyond extra paragraph; m=1 keeps re-retrieval cost small so gating vs Always/Full-context comparison stays meaningful (m=2 approaches k=4/full-context).
- Caveats: retrieval recall only, not answer F1; n=100 (1 q = 1 pt); optional re-check on tune.json.
- Next: Step 3 — choose answer LLM and NLI model, estimate budget.

## 2026-11-14 21:50 — Decision: compute plan (user approved)
- Hardware: YangQS = NVIDIA RTX 4060 Laptop (8GB) → suitable for NLI only.
- Pilot (pre-experiment): answer model via API (candidates DeepSeek-V3 deepseek-chat, GPT-4o-mini); NLI local on 4060.
- Main experiment: rent GPU, deploy local answer model (e.g., Qwen2.5-7B-Instruct via vLLM, OpenAI-compatible endpoint) for reproducibility, logprobs (uncertainty), stable latency.
- Scripts must support both API and OpenAI-compatible local endpoint.

## 2026-11-14 21:57 — Step 3 prepared: answer-model comparison script
- Script: /workspace/exp/step3/compare_models.py (+ README_step3.md). OpenAI-compatible API; presets deepseek (deepseek-chat), openai (gpt-4o-mini), custom (for later vLLM).
- Retrieval identical to step 2 (verified 0 mismatches on 100 pilot q). k=2, m=1, first n=30 pilot questions, temperature 0, max_tokens 128.
- Two branches per question: A = round-1 paras; B = round-1 + round-2 para. Output JSON {answer, citations}; official HotpotQA EM/F1 normalization.
- Logs tokens, latency, logprobs (mean/min over answer tokens; fallback if unsupported); cache.jsonl by (model,_id,branch).
- Summary: mean EM/F1 A and B, oracle F1, improved/tie/degraded counts, tokens, latency, optional cost extrapolation to 1600 q × 2.
- Tested only against a mock server (mock numbers are NOT results). Real API runs pending on YangQS.
- Selection criteria: branch-A F1 ≈ 0.4–0.7; B−A gain; logprobs support; cost.

## 2026-11-14 22:07 — Step 3 executed: deepseek-chat on pilot first 30 (YangQS)
- k=2, m=1; 60 calls all succeeded; logprobs returned for all; 0 parse failures.
- EM: A 0.433, B 0.600. F1: A 0.565, B 0.733, Oracle 0.767. Mean ΔF1 (B−A) = +0.169.
- Per-question: improved 7, tie 22, degraded 1 (n=30, tie eps 0).
- Tokens: 26,713 total (in 25,639, out 1,074); mean latency 0.697 s/call. Cost not estimated (no price passed).
- Interpretation: A-F1 in target 0.4–0.7; re-retrieval helps; Oracle − B = 0.034 and Oracle − A = 0.202 → headroom exists for gating; but Always (B) already near Oracle, so gate must mainly save cost on the 22 tie questions while keeping the 7 improved.
- Outputs: G:/NLP_project/step3_deepseek/{summary.json, per_question.csv}.
- OpenAI comparison not run yet.

## 2026-11-15 09:40 — Decision: Step 4 pre-registered parameters (user approved)

These nine values are locked before the 100-question pilot (Step 5). Items 4, 5, 6, and 9 are subjective, pre-registered thresholds; the paper must state that they were set in advance and give the reasons below. No value was chosen after seeing the 100-question results.

### 1. Tie tolerance ε = 0
- Decision: a question is a tie iff F1_B = F1_A (no slack).
- Reason: official HotpotQA F1 is deterministic, and generation temperature is 0, so the same question yields the same F1 on a rerun. Any F1 difference is therefore a real change from the extra paragraph, not measurement noise, and does not need a tolerance band.
- Alternative considered: ε > 0 (e.g. 0.1). Small wording changes (one extra word in the answer) would be counted as ties, shrinking the improved set and the positive class the gate can learn from. The 30-question API run already has only 7 improved questions.
- Sensitivity plan: if later inspection shows that most small F1 changes are wording-only and semantically equivalent, report ε = 0.1 as a sensitivity analysis; the primary definition stays ε = 0.

### 2. Positive class: F1_B > F1_A
- Decision: the gate's positive label is "re-retrieval is worth it on this question", defined as official F1 after the second-round paragraph being strictly higher than first-round F1.
- Reason: the gate's job is to decide whether a second retrieval is worthwhile; the most direct criterion is whether the answer itself improves. This matches the protocol and the external reviewer's advice to label from per-question official F1 change.
- Alternative rejected (1): "round 2 retrieved a new gold paragraph". This is a retrieval event, not an answer event. Step 2 already showed that obtaining a gold paragraph does not imply a correct answer.
- Alternative rejected (2): "EM changes from 0 to 1". This is too strict: partial F1 gains would be discarded and the already small positive class would shrink further.

### 3. Oracle chooses A on a tie
- Decision: when F1_B = F1_A, the oracle (best of A and B with hindsight) selects branch A (no re-retrieval).
- Reason: a tie means the extra retrieval brought no quality gain, so its cost is wasted. The oracle is "the best choice if the outcome were known"; the best choice is then not to retrieve again.
- Alternative rejected: choose B on a tie. That would inflate the oracle re-retrieval rate. In the 30-question run, 22 questions tied; the oracle rate would rise from 7/30 to nearly 29/30, and the cost-saving upper bound of any gate would become invisible.

### 4. Go/no-go on headroom: Oracle − A point estimate ≥ 0.05 F1, and the 95% bootstrap CI lower bound > 0
- Decision (revised from a point-threshold only): after the 100-question pilot, compute a paired bootstrap 95% confidence interval for mean(Oracle F1 − A F1). The pilot proceeds to gating work only if the lower bound is greater than 0 and the point estimate is at least 0.05.
- Reason for the CI condition: a confidence-interval lower bound above 0 is direct evidence that headroom is not a sampling artefact. This is more convincing than a fixed point threshold alone.
- Reason for the 0.05 point-estimate floor (subjective, pre-registered): 0.05 is our own "minimum effect worth pursuing", not a number taken from a paper. The reasoning is that the standard error of mean F1 on 100 questions is expected to be about 0.03–0.04 (an estimate; the 100-question bootstrap will give the exact figure). If headroom is smaller than roughly one standard error, later comparisons among gates will be dominated by noise. 0.05 is about 1.5 standard errors under that estimate.
- Alternative considered and rejected: use only "point estimate ≥ 0.05". That ignores uncertainty. Use only "CI lower bound > 0": a statistically real but tiny gain (e.g. 0.01) would still pass, yet would leave little room for a gate to beat Always or Never in a way that is visible above noise.

### 5. Improved share ≥ 10% of questions (subjective, pre-registered)
- Decision: the pilot is a go for gating only if at least 10% of the 100 pilot questions are improved (F1_B > F1_A).
- Reason: the gate is tuned on the 500-question tune set and evaluated on the 1,000-question test set. A 10% improved rate implies about 100 positive examples on test, enough for reasonably stable precision, recall, and F1. A 3% rate would be about 30 positives; one misclassified question would move recall by about 3 points, and conclusions would be unstable.
- Margin: the 30-question API run had 23% improved, so 10% is a floor with slack, not a target.
- This threshold is a sample-size / stability judgement, not a literature constant, and must be described as pre-registered in the paper.

### 6. Degraded count ≤ half of the improved count (subjective, pre-registered)
- Decision: the re-retrieval procedure itself is acceptable only if the number of degraded questions (F1_B < F1_A) is at most half the number of improved questions.
- Reason: if degradations are as frequent as improvements, Always-retrieve has near-zero average gain and the rewrite-and-retrieve procedure is itself flawed; the rewrite should be fixed before any gate is trained. Capping degradations at half the improvements keeps the net effect of re-retrieval clearly positive.
- Role of this check: it audits the quality of the re-retrieval procedure, not the quality of the gate. A higher degraded share would make the gate more necessary (it would have to avoid harmful retrievals) but would also mean the retrieval step is unreliable.
- This ratio is a pre-registered judgement, not a literature constant.

### 7. If the pilot fails, the re-retrieval rule may be revised only once
- Decision: should the 100-question pilot miss any of the go/no-go criteria above, the second-round query rewrite may be changed once, the two branches recomputed, and the same criteria reapplied. A second revision on the same pilot is not allowed.
- Reason: repeatedly rewriting the rule and re-inspecting results on the same 100 questions would fit the rule to this pilot (overfitting). A one-revision cap, with the change and its rationale written in this log, is a standard safeguard.
- If the single revision still fails: report in the paper that, under the HotpotQA distractor setting, the gain from one extra retrieval is limited. That is itself a result, not a reason to keep tuning.

### 8. NLI model and input construction
- Model: `MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli`, run locally on the YangQS RTX 4060 Laptop (8GB).
- Reason for this model: it is trained on MNLI, FEVER, ANLI, LingNLI, and WANLI, so it is better suited to long, complex premises than an MNLI-only model; our premise is two or three paragraphs concatenated. It is also a widely downloaded NLI model on Hugging Face, so reviewers are likely to recognise it. The large checkpoint has about 400 million parameters and fits 8GB for inference.
- Premise: the cited paragraphs, concatenated in citation order. Hypothesis: the question plus the model answer, rewritten as a declarative sentence.
- Reason for concatenation (not sentence-level max or min): this follows the external reviewer's advice. Taking the max over sentences would treat a sentence that supports only one hop as full support; taking the min would treat an answer that is only supported by two paragraphs together as unsupported.
- Truncation: DeBERTa's maximum input length is 512 tokens. With k=2 and m=1 the premise is at most three paragraphs, so most questions should fit. The script must count how many inputs are truncated. If the truncated share is high, a later option is to use only the cited sentences rather than whole paragraphs; that change would be logged before being used as the primary setting.

### 9. Manual audit of 20 questions, three error types (subjective, pre-registered)
- Decision: after automatic NLI scoring, draw 20 questions for manual review, covering three error types (target: about 6–7 questions each). The audit is qualitative.
- Reason: the aim is to discover systematic NLI failure modes, not to estimate an error rate precisely. Twenty questions, roughly 6–7 per type, are enough to see whether a failure mode is common. If one type is frequent, the sample for that type can be enlarged.
- Limitation: an error rate estimated from 20 questions has a large sampling error; the paper may report this only as a qualitative analysis, not as a precise figure.
- This sample size is a pre-registered judgement, not a literature constant.

Next: Step 5 — 100-question pilot script (both cached branches, local DeBERTa NLI, supporting-fact coverage, improved/tie/degraded, Oracle vs Never, go/no-go readout).

## 2026-11-15 09:50 — Step 5 prepared: 100-question pilot script
- Script: /workspace/exp/step5/run_pilot.py (+ README_step5.md, test_step5.py). Imports retrieval / scoring / API / cache from compare_models.py (same BM25 as Steps 2–3).
- Locked defaults: n=100, k=2, m=1, preset deepseek (deepseek-chat), temperature 0, max_tokens 128, tie ε=0, Oracle chooses A on a tie.
- Reuses Step 3 answers via --answer-cache (e.g. G:/NLP_project/step3_deepseek/cache.jsonl); new calls are written to <out>/cache.jsonl. --skip-nli fills answers first; --nli-only runs or re-runs NLI from existing branches/cache with no new API calls.
- NLI default: MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli, max_length 512, device auto. Premise = cited paragraphs in citation order (fallback to retrieved paragraphs if no usable citations, flagged). Hypothesis template (not an LLM rewrite): The answer to the question "{question}" is: {answer}. Label probabilities use the checkpoint id2label (order is not assumed). Truncations are counted per branch and overall.
- Go/no-go (pre-registered): paired bootstrap 95% CI (B=10000, seed=42) for mean(Oracle F1 − A F1) — GO only if CI lower bound > 0 AND point estimate ≥ 0.05; improved share ≥ 10%; degraded count ≤ half of improved. All three must pass. Also reports retrieval/citation coverage; official sentence-level SP F1 is null unless citations include sentence indices.
- Outputs under --out (default step5_pilot): per_question.csv, branches.jsonl, nli_scores.jsonl, summary.json, audit_sample.csv (up to 20 stratified rows, types a/b/c, seed 42, human_label left blank), cache.jsonl.
- Box tests: python /workspace/exp/step5/test_step5.py — 23 tests passed, including known-F1 classification/oracle/bootstrap/GO and NO-GO fixtures, and an end-to-end run against the Step 3 mock chat server with --nli-backend mock (4-question slice of pilot.json plus one synthetic long-paragraph item for the truncation path). Mock numbers are NOT results. The DeBERTa-v3-large checkpoint was not downloaded. Real API + 4060 NLI run pending on YangQS.
- --nli-backend mock prints a warning that scores are fake; --nli-backend hf without transformers/torch exits with a pip install message.

Next: user runs Step 5 on YangQS — (a) fill the remaining answers with DeepSeek, reusing the Step 3 cache; (b) run local NLI on the RTX 4060.

## 2026-11-15 10:33 — Step 5 executed: 100-question pilot on YangQS (deepseek-chat + local DeBERTa NLI on RTX 4060) — verdict GO
- Settings: pilot.json n=100, k=2, m=1, deepseek-chat, temperature 0, max_tokens 128, tie ε=0, Oracle chooses A on tie. Step 3 cache reused; NLI-only pass made no new API calls (as reported by user).
- Answer quality: EM A 0.520, B 0.650; F1 A 0.628, B 0.752, Oracle 0.765. Mean ΔF1 (B−A) = +0.124.
- Per-question: improved 16, tie 82, degraded 2. Degraded/improved = 0.125.
- Headroom: mean(Oracle F1 − A F1) = 0.137; paired bootstrap 95% CI [0.077, 0.203] (B=10000, seed 42).
- NLI (MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli): 200 inputs (A 100, B 100) scored; truncated 0/200 (0%); fallback to retrieved paragraphs 0. Mean entailment probability A 0.876, B 0.923.
- Go/no-go vs pre-registered criteria (Step 4): headroom point 0.137 ≥ 0.05 PASS; CI lower bound 0.077 > 0 PASS; improved share 16% ≥ 10% PASS; degraded/improved 0.125 ≤ 0.5 PASS → OVERALL GO. Item 7 (one-time rule revision) not triggered.
- Interpretation: Oracle − B = 0.013, so Always (B) is already close to Oracle; with 82% ties, the gate's value lies mainly in cutting re-retrieval cost on tie questions while retaining the 16 improved ones. Main claim should be "near-B F1 at a clearly lower re-retrieval rate", not "F1 above B". Consistent with the 30-question Step 3 result.
- Caveat: round-1 entailment is already high on average (0.876); whether NLI separates improved from tie questions is not yet shown. Planned check: offline, descriptive comparison of round-1 entailment / logprob distributions for improved vs tie (e.g. AUC) on pilot — diagnostic only; no gate parameters are tuned on pilot (tuning on tune.json).
- Outputs (YangQS): G:/NLP_project/step5_pilot/{summary.json, per_question.csv, branches.jsonl, nli_scores.jsonl, audit_sample.csv, cache.jsonl}.
- Pending: manual audit of 20 rows in audit_sample.csv (human_label).

## 2026-11-15 10:40 — Step 5 audit helper prepared
- Script: /workspace/exp/step5/audit_helper.py. Reads <dir>/audit_sample.csv + <dir>/nli_scores.jsonl (joined on _id, branch); writes <dir>/audit_review.csv (UTF-8 BOM for Excel) with full premise text and rule-based hints: yes/no question, answer vs gold (exact / substring / different, after HotpotQA-style normalization), answer string in premise, gold answer in premise, gold titles in premise (x/y), suggested checks.
- Hints are aids only; human columns left blank: human_answer_correct, human_premise_supports, human_label (codes: nli_correct, nli_wrong_multihop, nli_wrong_lexical, nli_wrong_hypothesis, nli_wrong_other), note. Labels are assigned by a person, not by the script.
- Box test on a 2-row synthetic fixture only (no real data on box).

## 2026-11-15 10:48 — Step 5 manual audit received (20 rows)
- File from user: G:/NLP_project/step5_pilot/audit_review.csv (copy: /workspace/exp/step5/audit_review_yangqs.csv). All 20 rows have human_answer_correct, human_premise_supports, human_label, and note filled. human_answer_correct: yes 7, no 13. human_premise_supports: yes 2, no 18. human_label: nli_correct 11, nli_wrong_lexical 6, nli_wrong_multihop 2, nli_wrong_other 1, nli_wrong_hypothesis 0.
- 20 rows are (question, branch) pairs covering 15 unique questions (5 questions appear as both A and B).
- Cross-tab of automatic error_type vs human_label:
  - false_entailment (7): 6 nli_wrong_lexical, 1 nli_wrong_other (NLI assigned entailment to the abstention "Unknown").
  - false_non_entailment (7): 5 nli_correct, 2 nli_wrong_multihop (same question, branches A and B; SpongeBob episode dates).
  - truncated_or_disagreement (6): all nli_correct (consistent with 0% truncation; NLI correctly withheld entailment when the premise did not support the answer).
- Interpretation (qualitative only, n=20, not an error-rate estimate): the automatic "false entailment" bucket largely tracks real NLI errors, mainly lexical overlap. The automatic "false non-entailment" and "disagreement" buckets are mostly false alarms: the model answer can match the gold answer while the cited premise still does not support it (the model may have used parametric knowledge). True multi-hop misses appeared twice, both on one question. No hypothesis-template errors were labelled in this sample.
- Labels follow the pre-registered five-code scheme. A possible refinement not yet applied: some nli_correct rows have argmax=contradiction when the human note describes missing evidence (neutral may be more appropriate than contradiction); this does not change the codebook decision, which treats any non-entailment as agreeing with "premise does not support".

## 2026-11-15 10:51 — Step 5 signal diagnostic script prepared
- Script: /workspace/exp/step5/analyze_signals.py (+ test_analyze_signals.py). Offline only: reads step5_pilot/per_question.csv, no API or NLI calls, no threshold selection.
- Compares branch-A nli_entailment, mean_logprob, and min_logprob across improved / tie / degraded. Primary contrast is improved vs tie (the 16 vs 82 split). AUC uses the oriented score (−signal), so AUC>0.5 means a *lower* round-1 value tends to mark improved questions (the expected direction for a re-retrieval gate). Bootstrap 95% CI (default B=5000, seed 42) for AUC and for mean(improved)−mean(tie).
- Also prints illustrative rules "re-retrieve if nli_entailment_A < t" at pre-set t ∈ {0.50, 0.80, 0.90, 0.95}. These are descriptive only and must not be reused as the gate; tuning remains on tune.json.
- Outputs: signal_summary.json, signal_by_class.csv. Box unit tests (6) passed on synthetic data; real pilot numbers pending the user's run on YangQS.

## 2026-11-15 11:04 — Step 5 signal diagnostic executed on YangQS (pilot, descriptive only)
- n=100: improved 16, tie 82, degraded 2.
- Branch-A NLI entailment mean: improved 0.798, tie 0.888, degraded 0.989 (n=2, not interpretable). AUC improved vs tie (low entailment → improved) = 0.699, bootstrap 95% CI [0.579, 0.812] (B=5000, seed 42). Lower bound above 0.5 → NLI carries a moderate, directionally correct signal; not strong enough alone, which supports combining signals in the fuzzy gate rather than a single NLI threshold.
- mean_logprob_A / min_logprob_A: all class means 0.000, AUC 0.500 [0.500, 0.500]. User checked the answer cache: every recorded token logprob in all 100 round-1 responses is 0.0.
- Code check (compare_models.py `_token_logprob_list`): per-token values are copied directly from `choice.logprobs.content[i].logprob` via float(); no default 0 is filled. So the zeros are what the deepseek-chat API returned with temperature 0, not a span-matching bug in summarize_logprobs (which only averages those values). Root cause on the vendor side is not confirmed.
- Consequence: logprob signals from this API batch are INVALID (degenerate), not evidence that logprob lacks discriminative power. Must be reported as such. The main experiment's local vLLM model is expected to return real logprobs; verify on first run before relying on them.
- Illustrative entailment thresholds written to signal_summary.json; none selected. Outputs: G:/NLP_project/step5_pilot/{signal_summary.json, signal_by_class.csv}.

## 2026-11-15 11:20 — Logprob probe script prepared
- Script: /workspace/exp/step5/probe_logprobs.py. Purpose: check whether deepseek-chat returns non-zero token logprobs, and whether the all-zero values seen in Step 5 depend on temperature.
- Design: 2 short prompts (one low-uncertainty factual, one open-ended) × temperatures {0, 1} = 4 calls, max_tokens 8, logprobs=True, top_logprobs=5. Reports per call: token count, count of logprob exactly 0.0, min/mean logprob, non-zero top-5 alternatives. Raw token logprobs saved to probe_logprobs.json (no key).
- Box test against the Step 3 mock server only (mock values are not results). Real probe pending on YangQS.

## 2026-11-15 11:48 — Logprob probe executed on YangQS (deepseek-chat, 4 calls)
- temperature 0: prompt 0 ("Paris", 1 token) and prompt 1 ("Kiwi", 2 tokens) — all output-token logprobs = 0; top-5 alternatives non-zero 4/5 and 8/10.
- temperature 1: prompt 0 min/mean −0.000001073 (1 token, non-zero); prompt 1 min −0.4549, mean −0.2275 (1 of 2 tokens = 0); top alternatives non-zero 5/5 and 9/10.
- Conclusion: the all-zero output-token logprobs in Step 5 are tied to how deepseek-chat scores the chosen token under temperature 0, not to our extraction code. Alternatives (top_logprobs) remain informative at temperature 0.
- Options recorded: (1) use top-1 vs top-2 alternative margin from top_logprobs at temperature 0 (requires re-running 200 pilot calls with top_logprobs; API-driven workaround, must be disclosed); (2) temperature 1 (real logprobs but breaks locked temperature 0 / reproducibility — not recommended); (3) pilot evaluates NLI only; logprob signals evaluated on the main-experiment local vLLM model, verified non-degenerate on first run. Recommended: (3). Decision pending user.
- Raw: G:/NLP_project/probe_logprobs.json.

## 2026-11-15 11:51 — Decision: logprob handling = Option 1 (user choice)
- Re-run all 200 pilot calls (100 q × branches A/B) with deepseek-chat, temperature 0, max_tokens 128, same prompts and retrieval (k=2, m=1), adding logprobs=True and top_logprobs=5. New calls go to a separate cache; the Step 5 cache and results are not overwritten.
- Uncertainty measure (defined before seeing results): for each output token, margin = logprob(top-1 alternative) − logprob(top-2 alternative) from top_logprobs. Primary signal = mean margin over answer-span tokens of branch A (fallback to all output tokens if the answer span cannot be located; count fallbacks). Secondary (descriptive): min margin over the answer span, margin of the first answer token, mean top-5 entropy (renormalised over the returned alternatives). Lower margin / higher entropy = more uncertain = expected to mark improved questions.
- Consistency check: compare each re-run answer with the Step 5 cached answer (HotpotQA-normalised string equality; also F1 vs gold). Report the number of changed answers per branch. Labels (improved/tie/degraded) stay those from Step 5 per_question.csv. Primary AUC is computed on questions whose A and B answers are both unchanged; an all-questions AUC is reported as sensitivity. The Step 5 GO verdict is not re-decided on re-run answers.
- Comparison: report NLI AUC on the same question subset so the two signals are compared on identical data.
- Known limitations to disclose: the margin is a workaround for the API reporting 0 for the chosen token at temperature 0; it is not the same quantity as the chosen-token logprob planned for the local vLLM model. DeepSeek logprob distributions do not transfer to the main-experiment model; the pilot result is evidence about the signal type, not a tuned gate input.

## 2026-11-15 11:57 — Step 5b prepared: top_logprobs re-run + margin-signal analysis (not yet run)
- Script: /workspace/exp/step5b/rerun_toplogprobs.py (+ README_step5b.md, test_step5b.py). Implements the 11:51 pre-registration as written: deepseek-chat, temperature 0, max_tokens 128, k=2, m=1, same prompts/retrieval/parsing (imports compare_models.py), logprobs=True, top_logprobs=5. 200 new calls; none reused from Step 5.
- Separate resume-safe cache <out>/cache_toplp.jsonl keyed (model, _id, branch, top_logprobs), also checked on k/m/temperature/max_tokens; errored calls are retried on resume. The script refuses any cache file named cache.jsonl, so Step 5 caches cannot be written.
- Metrics per branch: answer-span tokens located with the compare_models.summarize_logprobs rule (fallback to all tokens, counted); margin = top-1 − top-2 alternative logprob (alternatives sorted; <2 → missing); mean_margin (PRIMARY, branch A), min_margin, first-answer-token margin, mean entropy over renormalised alternatives; counts of chosen≠top-1, top-1 alternative exactly 0.0, chosen logprob exactly 0.0.
- Consistency vs Step 5 per_question.csv: HotpotQA-normalised equality per branch, new F1; consistency.csv lists CHANGED rows first. Labels = Step 5 delta_class; GO not re-decided.
- Analysis: improved vs tie AUC, bootstrap 95% CI (B=5000, seed 42) via analyze_signals.auc_score/bootstrap_ci. PRIMARY subset = A and B both unchanged; sensitivity = all. Every subset also requires a margin value and an NLI value, so NLI entailment_A AUC is computed on exactly the same questions. No gate threshold is selected.
- Implementation choices not fixed by the pre-registration: entropy also needs ≥2 alternatives (same rule as margin); the margin/entropy definitions are kept even when the top-1 alternative is reported as 0.0, and such tokens are counted for disclosure; if the endpoint rejects logprobs the script stops rather than falling back.
- Mock server step3/test_mock_server.py gained an opt-in --top-logprobs-mode deepseek_t0 (FAKE alternatives; chosen token 0.0 at T=0). Default behaviour is unchanged; Step 5 tests still pass (23/23).
- Box tests: python3 /workspace/exp/step5b/test_step5b.py — 17 passed (margin/entropy on known numbers, span rule matches compare_models, AUC orientation, same-subset NLI, consistency, cache isolation/resume, analyze-only, mock end-to-end on mini_pilot.json with a SYNTHETIC per_question.csv, key not printed). All mock numbers are FAKE, not results.

Next: user runs on YangQS: python rerun_toplogprobs.py --data pilot.json --step5-dir step5_pilot --out step5b_toplp

## 2026-11-15 12:08 — Step 5b executed (re-run with top_logprobs=5)

**Run (by user on YangQS):** `python rerun_toplogprobs.py --data pilot.json --step5-dir step5_pilot --out step5b_toplp`; all 200 calls succeeded. Output: G:/NLP_project/step5b_toplp/toplp_summary.json.

**Results reported by the user:**

| Analysis | n | mean_margin_A AUC (95% CI) | NLI AUC, same questions (95% CI) |
|---|---:|---:|---:|
| Primary: A and B answers unchanged | 88 | 0.500 [0.500, 0.500] | 0.724 [0.593, 0.844] |
| Sensitivity: all questions | 100 | 0.482 [0.457, 0.500] | 0.699 [0.579, 0.812] |

- Answer consistency (HotpotQA normalisation): 9 changed in A, 4 in B, 12 distinct questions in total. Labels stay those of Step 5; the GO verdict is not re-evaluated.
- Of 3,482 output tokens (A 1,703, B 1,779), the top-1 alternative logprob is reported as 0.0 for all of them.
- 3,477 tokens have the top-2 alternative reported as -9999.0, so mean_margin_A = 9999.0 for all 88 primary questions.

**Interpretation:**
1. -9999.0 is a placeholder value meaning "probability negligible / not reported", not a real log-probability. At temperature 0, deepseek-chat therefore reports the chosen token at 0 and nearly all alternatives at the placeholder value. The pre-registered margin signal is degenerate, and AUC 0.500 means "no information", not "a weak signal".
2. Correction to the 11:48 probe entry: "alternatives non-zero" counted -9999.0 as non-zero. The probe should have checked for placeholder values. This is a limitation of the probe check, recorded so the report does not cite that count as evidence of usable alternatives.
3. No post-hoc rescue: secondary signals computed from the same alternatives (min margin, first-token margin, entropy) rest on the same placeholder values, so they are not used as a substitute. Switching to temperature 1, or treating -9999 as a numeric value, would be a new, unregistered analysis and is not done.
4. The NLI signal is stable across subsets (0.699 on all 100, 0.724 on the 88 unchanged), so the Step 5 finding that NLI is a moderate signal holds.

**Conclusion for the paper:** in the pilot, the DeepSeek API at temperature 0 provides no usable token-level confidence signal (neither the chosen-token logprob nor the top-k margin). Logprob-based signals for the gate will be assessed only on the main-experiment local model (vLLM), after checking on the first 30 tune questions that its logprobs are non-degenerate: no all-zero chosen tokens and no placeholder alternatives.

## 2026-11-15 12:13 — Step 6a prepared: local vLLM logprob degeneracy check (not yet run)

- Script: /workspace/exp/step6a/check_logprobs.py (+ README_step6a.md, test_step6a.py). Purpose: on the first 30 questions of the tune split, check whether a local model served by vLLM returns non-degenerate token logprobs. This gates whether logprob-based signals may enter the fuzzy gate in the main experiment. Prompt, BM25 retrieval (k=2), answer parsing and the OpenAI-compatible client are imported from compare_models.py; margin, entropy, answer-span location and the top_logprobs call helper are imported from rerun_toplogprobs.py (not copied). Branch A only, temperature 0, max_tokens 128, logprobs=True, top_logprobs=5. 30 calls.
- Default endpoint: model Qwen/Qwen2.5-7B-Instruct, base_url http://localhost:8000/v1, key from env var VLLM_API_KEY (optional; unset → placeholder EMPTY, never printed). If tune.json is not in the current directory, pass --data and optionally --n 30 --offset 0. There is no tune.json on this box; the official file is G:/NLP_project/tune.json (500 questions, seed-42 split).
- Separate resume-safe cache <out>/cache_logprob_check.jsonl, keyed (model, _id, branch, top_logprobs) and checked on k/temperature/max_tokens; errored calls are retried on resume. The script refuses any cache file named cache.jsonl, so Step 3/5 caches cannot be written.
- Outputs: logprob_check.json (summary, per-criterion observations, verdict) and logprob_check_tokens.csv (one row per output token). Also reported, but not used in the verdict: fraction of chosen tokens whose logprob equals the top-1 alternative; min/median/max, n_distinct and variance of the two per-question means; EM/F1 vs gold (informational only).
- This step tests degeneracy only, not predictive power. No AUC is computed, and no gate threshold is selected.

**Pre-registered PASS criteria** (defaults locked before any real local-model run; CLI-overridable; verdict is PASS only if all four hold, otherwise FAIL listing which failed). Items 1–4 use subjective thresholds; the paper must state that they were set in advance and give the reasons below.

1. At most 50% of answer-span chosen tokens have logprob exactly 0.0.
   - Rationale: under greedy decoding (temperature 0), a very confident token can legitimately have a logprob that rounds to 0 (e.g. -1e-6). A minority of exact zeros is therefore allowed. If most tokens are exactly 0.0, the API is clamping, as deepseek-chat did in Step 5b (every chosen token reported as 0.0).
   - Alternatives considered: "zero exact zeros allowed" is too strict and could fail a healthy server that rounds a few confident tokens; "ignore the zero fraction if any variance exists" is too loose and would miss a full clamp.
   - Effect of 50%: a DeepSeek-style clamp (100% zeros) FAILs; a server with only occasional rounded zeros can still PASS.
   - The 50% cutoff is a subjective, pre-registered judgment call.

2. Placeholder alternatives (logprob ≤ -9000) are under 5% of all reported alternatives ("under" = strictly less than).
   - Rationale: Step 5b found -9999.0 used as "probability negligible / not reported", not a real log-probability (3,477 tokens had the top-2 alternative at -9999.0). The cutoff -9000 is intended to catch that sentinel while remaining far below ordinary top-5 logprobs. A small fraction is tolerated for possible encoding glitches; a large share means the alternatives are unusable for a margin signal.
   - Alternatives considered: "zero placeholders allowed" is slightly stricter; "inspect only chosen-token logprobs" would miss the exact failure mode of the Step 5b margin signal.
   - Effect: a DeepSeek-like endpoint (nearly all alternatives at -9999) FAILs; a vLLM endpoint returning ordinary top-5 logprobs PASSes.
   - Both the -9000 cutoff and the 5% rate are subjective, pre-registered judgment calls.

3. The per-question mean chosen-token logprob (answer span; fallback: all output tokens if the span is not found, same rule as Step 5b) takes at least 10 distinct values across the 30 questions and has nonzero variance.
   - Rationale: even if per-token zeros are rare, the per-question means could still collapse to one constant. Thirty questions should show spread if the model emits real token probabilities. 10 is one-third of 30: enough to show the values are not collapsing to a handful of bins, without requiring all 30 means to be unique (ties from rounding or short answers are legitimate).
   - Alternatives considered: "any nonzero variance" is too weak (two distinct values would pass); "all 30 unique" is too strict.
   - Effect: a clamp that reports the same mean (e.g. 0.0) on every question FAILs; a healthy model with varying confidence across questions PASSes.
   - The number 10 is a subjective, pre-registered judgment call.

4. The same requirement on the per-question mean margin (top-1 minus top-2 alternative logprob, same span rule).
   - Rationale: in Step 5b, mean_margin_A was 9999.0 on all 88 primary questions because alternatives were placeholders. Checking mean-margin spread independently of chosen-token logprob catches a server that reports usable chosen logprobs but placeholder alternatives (or the reverse).
   - Alternatives considered: checking only chosen-token logprobs would miss that failure mode.
   - Effect: a collapsed margin (all 9999.0, or any single constant) FAILs criterion 4 even if criterion 3 passes.
   - The number 10 is a subjective, pre-registered judgment call.

Procedural rule (not a subjective threshold): all scheduled questions must have usable logprobs. If any call fails or returns no tokens, the verdict is FAIL with failed item `incomplete`, because non-degeneracy cannot be certified on a partial run.

**Implementation notes / design choices not fixed above:**
- Default per-request timeout is 120 s (local 7B models can be slower than the API; overridable).
- Criterion 2 uses a strict inequality (fraction < 0.05); criterion 1 uses "at most" (fraction ≤ 0.50), matching the wording of each rule.
- Distinct values are counted after rounding to 6 decimal places (same precision as the Step 5b token cache). Variance is the population variance; with 10 distinct values it is necessarily > 0, but both conditions are checked as written.
- vLLM CLI: the official flag on current docs (https://docs.vllm.ai/en/stable/cli/serve/ and Engine Arguments) is `--max-logprobs` (default 20, which already allows top_logprobs=5). README tells the user to start with `vllm serve Qwen/Qwen2.5-7B-Instruct --host 127.0.0.1 --port 8000 --max-logprobs 5`, and to reach a remote GPU from YangQS via an SSH tunnel (`ssh -N -L 8000:127.0.0.1:8000 user@gpu-host`) rather than publishing the port.
- Mock server step3/test_mock_server.py gained an opt-in `--top-logprobs-mode vllm_healthy` (FAKE ordinary negative chosen logprobs, never exactly 0.0, no placeholder alternatives; chosen equals top-1). Default remains `empty`; `deepseek_t0` is unchanged (chosen=0.0 at T=0, non-placeholder alternatives) so existing Step 5b tests keep their fixture. Step 6a uses `vllm_healthy` → PASS and `deepseek_t0` → FAIL (zero_chosen_frac and mean_chosen_logprob_spread; the current deepseek_t0 fixture does not emit -9999, so placeholder_alt_frac is not the failing item in that mock).

- Box tests: python3 /workspace/exp/step6a/test_step6a.py — 16 passed (criteria on known numbers, including the four default thresholds, strict "under 5%", inclusive "at most 50%", incomplete runs, CLI overrides, cache isolation, key not printed, offset slice, analyze-only, and mock end-to-end on 30 SYNTHETIC questions). Existing tests still pass: step5 23/23, analyze_signals 6/6, step5b 17/17. All mock numbers are FAKE, not results. No real vLLM run has been made.

Next: user starts vLLM on the rented GPU (or tunnels to it from YangQS) and runs:
  python check_logprobs.py --data tune.json --out step6a_check

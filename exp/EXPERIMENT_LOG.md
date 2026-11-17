# Experiment Log — Fuzzy-NLI QA Chatbot (Adaptive Retrieval)

Protocol: /workspace/lr/Experiment_Protocol_v2.docx (status: 通过预实验，正式方案待锁定)
Entries are listed in recording order.

## Step 1: Data source decided
- Decision: use Hugging Face `hotpotqa/hotpot_qa`, config `distractor`, split `validation` (official dev set; test answers not public).
- Reason: easy loading/splitting with `datasets`; will convert to official JSON format for `hotpot_evaluate_v1.py`.
- Planned processing: filter `type == "bridge"`, shuffle with fixed seed (42, proposed), split into disjoint pilot / tune / test; sizes 【待确认】(example: 100 / 500 / 1000).
- Alternatives considered: official site JSON (`hotpot_dev_distractor_v1.json`); BEIR/KILT/FlashRAG versions rejected (no per-question 10-paragraph distractor pool).
- Status: procedure specified for the load, filter, split and convert code. Not yet executed.

## Step 1 executed: Data split
- Source: HF `hotpotqa/hotpot_qa`, config `distractor`, split `validation`; Parquet downloaded via mirror, SHA-256 verified.
- Validation total: 7,405 questions; bridge: 5,918.
- Filter type == bridge, shuffle seed 42, sequential split:
  - pilot.json — 100 (pre-experiment)
  - tune.json — 500 (tuning)
  - test.json — 1,000 (formal test)
- Format: official HotpotQA JSON (UTF-8), for hotpot_evaluate_v1.py.
- Checks: re-read all three files; all bridge; 1,600 `_id` unique (disjoint).
- Note: some questions have fewer than 10 context paragraphs; kept as original (affects top-k / unused-paragraph pool in round 2 — handle in retrieval code and report in paper).
- Sizes follow the example values; formal test size still subject to protocol 7.4 (budget / effect size).

## Step 2 prepared: BM25 top-k recall script (verification run)
- Script: /workspace/exp/step2/bm25_topk.py (rank_bm25 BM25Okapi; lowercase alnum tokens, small stopword list).
- Round 1: query = question; rank the question's own context paragraphs (title + sentences); take top-k.
- Round 2 rule rewrite: query = question + title + first sentence of round-1 top-1 paragraph; rank only unused paragraphs; add top-m.
- Gold = titles in supporting_facts. Metrics: mean gold-paragraph recall, both-gold rate, % questions where round 2 adds a gold paragraph, % with no unused paragraphs.
- Verification run: rebuilt pilot (bridge, seed 42, first 100) from HF; same procedure as the official run — expected identical to pilot.json but NOT yet confirmed against the official file.
- Verification results (100 pilot questions), m=1:
  k=2: R1 recall .635, both .310 | R2 recall .785, both .590, gain 30%
  k=3: R1 recall .710, both .450 | R2 recall .830, both .670, gain 24%
  k=4: R1 recall .755, both .540 | R2 recall .885, both .770, gain 26%
  m=2: k=2 R2 .845/.700 gain 42%; k=3 R2 .880/.770 gain 33%; k=4 R2 .920/.840 gain 31%
- Status: awaiting the official run to confirm; k and m not yet decided.

## Step 2 executed: official run
- The original bm25_topk.py was run on pilot.json, m=1 and m=2.
- Results identical to the verification run (all metrics match) → the rebuilt pilot matches the original pilot.
- Outputs: step2_m1/{summary.json,per_question.csv}, step2_m2/{...}; each 300 rows (100 q × 3 k), checked.
- No question lacked unused paragraphs at k≤4.
- Decision on k, m: pending.

## Decision: k=2, m=1
- Round 1 top-k = 2; round 2 adds m = 1 paragraph from unused pool via rule rewrite.
- Rationale: lowest R1 both-gold (31%) → most headroom; highest R2-gain share (30%); equal-budget check: k=2+m=1 (3 paras) both-gold 59% vs k=3 single-shot 45% → rewrite adds value beyond extra paragraph; m=1 keeps re-retrieval cost small so gating vs Always/Full-context comparison stays meaningful (m=2 approaches k=4/full-context).
- Caveats: retrieval recall only, not answer F1; n=100 (1 q = 1 pt); optional re-check on tune.json.
- Next: Step 3 — choose answer LLM and NLI model, estimate budget.

## Decision: compute plan
- Hardware: an 8GB GPU → suitable for NLI only.
- Pilot (pre-experiment): answer model via API (candidates DeepSeek-V3 deepseek-chat, GPT-4o-mini); NLI local on the 8GB GPU.
- Main experiment: rent GPU, deploy local answer model (e.g., Qwen2.5-7B-Instruct via vLLM, OpenAI-compatible endpoint) for reproducibility, logprobs (uncertainty), stable latency.
- Scripts must support both API and OpenAI-compatible local endpoint.

## Step 3 prepared: answer-model comparison script
- Script: /workspace/exp/step3/compare_models.py (+ README_step3.md). OpenAI-compatible API; presets deepseek (deepseek-chat), openai (gpt-4o-mini), custom (for later vLLM).
- Retrieval identical to step 2 (verified 0 mismatches on 100 pilot q). k=2, m=1, first n=30 pilot questions, temperature 0, max_tokens 128.
- Two branches per question: A = round-1 paras; B = round-1 + round-2 para. Output JSON {answer, citations}; official HotpotQA EM/F1 normalization.
- Logs tokens, latency, logprobs (mean/min over answer tokens; fallback if unsupported); cache.jsonl by (model,_id,branch).
- Summary: mean EM/F1 A and B, oracle F1, improved/tie/degraded counts, tokens, latency, optional cost extrapolation to 1600 q × 2.
- Tested only against a mock server (mock numbers are NOT results). Real API runs pending.
- Selection criteria: branch-A F1 ≈ 0.4–0.7; B−A gain; logprobs support; cost.

## Step 3 executed: deepseek-chat on pilot first 30
- k=2, m=1; 60 calls all succeeded; logprobs returned for all; 0 parse failures.
- EM: A 0.433, B 0.600. F1: A 0.565, B 0.733, Oracle 0.767. Mean ΔF1 (B−A) = +0.169.
- Per-question: improved 7, tie 22, degraded 1 (n=30, tie eps 0).
- Tokens: 26,713 total (in 25,639, out 1,074); mean latency 0.697 s/call. Cost not estimated (no price passed).
- Interpretation: A-F1 in target 0.4–0.7; re-retrieval helps; Oracle − B = 0.034 and Oracle − A = 0.202 → headroom exists for gating; but Always (B) already near Oracle, so gate must mainly save cost on the 22 tie questions while keeping the 7 improved.
- Outputs: step3_deepseek/{summary.json, per_question.csv}.
- OpenAI comparison not run yet.

## Decision: Step 4 pre-registered parameters

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
- Reason for the 0.05 point-estimate floor (subjective, pre-registered): 0.05 is a self-set "minimum effect worth pursuing", not a number taken from a paper. The reasoning is that the standard error of mean F1 on 100 questions is expected to be about 0.03–0.04 (an estimate; the 100-question bootstrap will give the exact figure). If headroom is smaller than roughly one standard error, later comparisons among gates will be dominated by noise. 0.05 is about 1.5 standard errors under that estimate.
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
- Model: `MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli`, run locally on the 8GB GPU.
- Reason for this model: it is trained on MNLI, FEVER, ANLI, LingNLI, and WANLI, so it is better suited to long, complex premises than an MNLI-only model; the premise is two or three paragraphs concatenated. It is also a widely downloaded NLI model on Hugging Face, so reviewers are likely to recognise it. The large checkpoint has about 400 million parameters and fits 8GB for inference.
- Premise: the cited paragraphs, concatenated in citation order. Hypothesis: the question plus the model answer, rewritten as a declarative sentence.
- Reason for concatenation (not sentence-level max or min): this follows the external reviewer's advice. Taking the max over sentences would treat a sentence that supports only one hop as full support; taking the min would treat an answer that is only supported by two paragraphs together as unsupported.
- Truncation: DeBERTa's maximum input length is 512 tokens. With k=2 and m=1 the premise is at most three paragraphs, so most questions should fit. The script must count how many inputs are truncated. If the truncated share is high, a later option is to use only the cited sentences rather than whole paragraphs; that change would be logged before being used as the primary setting.

### 9. Manual audit of 20 questions, three error types (subjective, pre-registered)
- Decision: after automatic NLI scoring, draw 20 questions for manual review, covering three error types (target: about 6–7 questions each). The audit is qualitative.
- Reason: the aim is to discover systematic NLI failure modes, not to estimate an error rate precisely. Twenty questions, roughly 6–7 per type, are enough to see whether a failure mode is common. If one type is frequent, the sample for that type can be enlarged.
- Limitation: an error rate estimated from 20 questions has a large sampling error; the paper may report this only as a qualitative analysis, not as a precise figure.
- This sample size is a pre-registered judgement, not a literature constant.

Next: Step 5 — 100-question pilot script (both cached branches, local DeBERTa NLI, supporting-fact coverage, improved/tie/degraded, Oracle vs Never, go/no-go readout).

## Step 5 prepared: 100-question pilot script
- Script: /workspace/exp/step5/run_pilot.py (+ README_step5.md, test_step5.py). Imports retrieval / scoring / API / cache from compare_models.py (same BM25 as Steps 2–3).
- Locked defaults: n=100, k=2, m=1, preset deepseek (deepseek-chat), temperature 0, max_tokens 128, tie ε=0, Oracle chooses A on a tie.
- Reuses Step 3 answers via --answer-cache (e.g. step3_deepseek/cache.jsonl); new calls are written to <out>/cache.jsonl. --skip-nli fills answers first; --nli-only runs or re-runs NLI from existing branches/cache with no new API calls.
- NLI default: MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli, max_length 512, device auto. Premise = cited paragraphs in citation order (fallback to retrieved paragraphs if no usable citations, flagged). Hypothesis template (not an LLM rewrite): The answer to the question "{question}" is: {answer}. Label probabilities use the checkpoint id2label (order is not assumed). Truncations are counted per branch and overall.
- Go/no-go (pre-registered): paired bootstrap 95% CI (B=10000, seed=42) for mean(Oracle F1 − A F1) — GO only if CI lower bound > 0 AND point estimate ≥ 0.05; improved share ≥ 10%; degraded count ≤ half of improved. All three must pass. Also reports retrieval/citation coverage; official sentence-level SP F1 is null unless citations include sentence indices.
- Outputs under --out (default step5_pilot): per_question.csv, branches.jsonl, nli_scores.jsonl, summary.json, audit_sample.csv (up to 20 stratified rows, types a/b/c, seed 42, human_label left blank), cache.jsonl.
- Tests: python /workspace/exp/step5/test_step5.py — 23 tests passed, including known-F1 classification/oracle/bootstrap/GO and NO-GO fixtures, and an end-to-end run against the Step 3 mock chat server with --nli-backend mock (4-question slice of pilot.json plus one synthetic long-paragraph item for the truncation path). Mock numbers are NOT results. The DeBERTa-v3-large checkpoint was not downloaded. Real API + GPU NLI run pending.
- --nli-backend mock prints a warning that scores are fake; --nli-backend hf without transformers/torch exits with a pip install message.

Next: run Step 5 — (a) fill the remaining answers with DeepSeek, reusing the Step 3 cache; (b) run local NLI on the 8GB GPU.

## Step 5 executed: 100-question pilot (deepseek-chat + local DeBERTa NLI on the 8GB GPU) — verdict GO
- Settings: pilot.json n=100, k=2, m=1, deepseek-chat, temperature 0, max_tokens 128, tie ε=0, Oracle chooses A on tie. Step 3 cache reused; NLI-only pass made no new API calls.
- Answer quality: EM A 0.520, B 0.650; F1 A 0.628, B 0.752, Oracle 0.765. Mean ΔF1 (B−A) = +0.124.
- Per-question: improved 16, tie 82, degraded 2. Degraded/improved = 0.125.
- Headroom: mean(Oracle F1 − A F1) = 0.137; paired bootstrap 95% CI [0.077, 0.203] (B=10000, seed 42).
- NLI (MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli): 200 inputs (A 100, B 100) scored; truncated 0/200 (0%); fallback to retrieved paragraphs 0. Mean entailment probability A 0.876, B 0.923.
- Go/no-go vs pre-registered criteria (Step 4): headroom point 0.137 ≥ 0.05 PASS; CI lower bound 0.077 > 0 PASS; improved share 16% ≥ 10% PASS; degraded/improved 0.125 ≤ 0.5 PASS → OVERALL GO. Item 7 (one-time rule revision) not triggered.
- Interpretation: Oracle − B = 0.013, so Always (B) is already close to Oracle; with 82% ties, the gate's value lies mainly in cutting re-retrieval cost on tie questions while retaining the 16 improved ones. Main claim should be "near-B F1 at a clearly lower re-retrieval rate", not "F1 above B". Consistent with the 30-question Step 3 result.
- Caveat: round-1 entailment is already high on average (0.876); whether NLI separates improved from tie questions is not yet shown. Planned check: offline, descriptive comparison of round-1 entailment / logprob distributions for improved vs tie (e.g. AUC) on pilot — diagnostic only; no gate parameters are tuned on pilot (tuning on tune.json).
- Outputs: step5_pilot/{summary.json, per_question.csv, branches.jsonl, nli_scores.jsonl, audit_sample.csv, cache.jsonl}.
- Pending: manual audit of 20 rows in audit_sample.csv (human_label).

## Step 5 audit helper prepared
- Script: /workspace/exp/step5/audit_helper.py. Reads <dir>/audit_sample.csv + <dir>/nli_scores.jsonl (joined on _id, branch); writes <dir>/audit_review.csv (UTF-8 BOM for Excel) with full premise text and rule-based hints: yes/no question, answer vs gold (exact / substring / different, after HotpotQA-style normalization), answer string in premise, gold answer in premise, gold titles in premise (x/y), suggested checks.
- Hints are aids only; human columns left blank: human_answer_correct, human_premise_supports, human_label (codes: nli_correct, nli_wrong_multihop, nli_wrong_lexical, nli_wrong_hypothesis, nli_wrong_other), note. Labels are assigned by a person, not by the script.
- Tested on a 2-row synthetic fixture only (no real data).

## Step 5 manual audit received (20 rows)
- File: audit_review.csv. All 20 rows have human_answer_correct, human_premise_supports, human_label, and note filled. human_answer_correct: yes 7, no 13. human_premise_supports: yes 2, no 18. human_label: nli_correct 11, nli_wrong_lexical 6, nli_wrong_multihop 2, nli_wrong_other 1, nli_wrong_hypothesis 0.
- 20 rows are (question, branch) pairs covering 15 unique questions (5 questions appear as both A and B).
- Cross-tab of automatic error_type vs human_label:
  - false_entailment (7): 6 nli_wrong_lexical, 1 nli_wrong_other (NLI assigned entailment to the abstention "Unknown").
  - false_non_entailment (7): 5 nli_correct, 2 nli_wrong_multihop (same question, branches A and B; SpongeBob episode dates).
  - truncated_or_disagreement (6): all nli_correct (consistent with 0% truncation; NLI correctly withheld entailment when the premise did not support the answer).
- Interpretation (qualitative only, n=20, not an error-rate estimate): the automatic "false entailment" bucket largely tracks real NLI errors, mainly lexical overlap. The automatic "false non-entailment" and "disagreement" buckets are mostly false alarms: the model answer can match the gold answer while the cited premise still does not support it (the model may have used parametric knowledge). True multi-hop misses appeared twice, both on one question. No hypothesis-template errors were labelled in this sample.
- Labels follow the pre-registered five-code scheme. A possible refinement not yet applied: some nli_correct rows have argmax=contradiction when the human note describes missing evidence (neutral may be more appropriate than contradiction); this does not change the codebook decision, which treats any non-entailment as agreeing with "premise does not support".

## Step 5 signal diagnostic script prepared
- Script: /workspace/exp/step5/analyze_signals.py (+ test_analyze_signals.py). Offline only: reads step5_pilot/per_question.csv, no API or NLI calls, no threshold selection.
- Compares branch-A nli_entailment, mean_logprob, and min_logprob across improved / tie / degraded. Primary contrast is improved vs tie (the 16 vs 82 split). AUC uses the oriented score (−signal), so AUC>0.5 means a *lower* round-1 value tends to mark improved questions (the expected direction for a re-retrieval gate). Bootstrap 95% CI (default B=5000, seed 42) for AUC and for mean(improved)−mean(tie).
- Also prints illustrative rules "re-retrieve if nli_entailment_A < t" at pre-set t ∈ {0.50, 0.80, 0.90, 0.95}. These are descriptive only and must not be reused as the gate; tuning remains on tune.json.
- Outputs: signal_summary.json, signal_by_class.csv. Verification unit tests (6) passed on synthetic data; real pilot numbers pending the official run.

## Step 5 signal diagnostic executed (pilot, descriptive only)
- n=100: improved 16, tie 82, degraded 2.
- Branch-A NLI entailment mean: improved 0.798, tie 0.888, degraded 0.989 (n=2, not interpretable). AUC improved vs tie (low entailment → improved) = 0.699, bootstrap 95% CI [0.579, 0.812] (B=5000, seed 42). Lower bound above 0.5 → NLI carries a moderate, directionally correct signal; not strong enough alone, which supports combining signals in the fuzzy gate rather than a single NLI threshold.
- mean_logprob_A / min_logprob_A: all class means 0.000, AUC 0.500 [0.500, 0.500]. The answer cache was checked: every recorded token logprob in all 100 round-1 responses is 0.0.
- Code check (compare_models.py `_token_logprob_list`): per-token values are copied directly from `choice.logprobs.content[i].logprob` via float(); no default 0 is filled. So the zeros are what the deepseek-chat API returned with temperature 0, not a span-matching bug in summarize_logprobs (which only averages those values). Root cause on the vendor side is not confirmed.
- Consequence: logprob signals from this API batch are INVALID (degenerate), not evidence that logprob lacks discriminative power. Must be reported as such. The main experiment's local vLLM model is expected to return real logprobs; verify on first run before relying on them.
- Illustrative entailment thresholds written to signal_summary.json; none selected. Outputs: step5_pilot/{signal_summary.json, signal_by_class.csv}.

## Logprob probe script prepared
- Script: /workspace/exp/step5/probe_logprobs.py. Purpose: check whether deepseek-chat returns non-zero token logprobs, and whether the all-zero values seen in Step 5 depend on temperature.
- Design: 2 short prompts (one low-uncertainty factual, one open-ended) × temperatures {0, 1} = 4 calls, max_tokens 8, logprobs=True, top_logprobs=5. Reports per call: token count, count of logprob exactly 0.0, min/mean logprob, non-zero top-5 alternatives. Raw token logprobs saved to probe_logprobs.json (no key).
- Tested against the Step 3 mock server only (mock values are not results). Real probe pending.

## Logprob probe executed (deepseek-chat, 4 calls)
- temperature 0: prompt 0 ("Paris", 1 token) and prompt 1 ("Kiwi", 2 tokens) — all output-token logprobs = 0; top-5 alternatives non-zero 4/5 and 8/10.
- temperature 1: prompt 0 min/mean −0.000001073 (1 token, non-zero); prompt 1 min −0.4549, mean −0.2275 (1 of 2 tokens = 0); top alternatives non-zero 5/5 and 9/10.
- Conclusion: the all-zero output-token logprobs in Step 5 are tied to how deepseek-chat scores the chosen token under temperature 0, not to the extraction code. Alternatives (top_logprobs) remain informative at temperature 0.
- Options recorded: (1) use top-1 vs top-2 alternative margin from top_logprobs at temperature 0 (requires re-running 200 pilot calls with top_logprobs; API-driven workaround, must be disclosed); (2) temperature 1 (real logprobs but breaks locked temperature 0 / reproducibility — not recommended); (3) pilot evaluates NLI only; logprob signals evaluated on the main-experiment local vLLM model, verified non-degenerate on first run. Recommended: (3). Decision pending.
- Raw: probe_logprobs.json.

## Decision: logprob handling = Option 1
- Re-run all 200 pilot calls (100 q × branches A/B) with deepseek-chat, temperature 0, max_tokens 128, same prompts and retrieval (k=2, m=1), adding logprobs=True and top_logprobs=5. New calls go to a separate cache; the Step 5 cache and results are not overwritten.
- Uncertainty measure (defined before seeing results): for each output token, margin = logprob(top-1 alternative) − logprob(top-2 alternative) from top_logprobs. Primary signal = mean margin over answer-span tokens of branch A (fallback to all output tokens if the answer span cannot be located; count fallbacks). Secondary (descriptive): min margin over the answer span, margin of the first answer token, mean top-5 entropy (renormalised over the returned alternatives). Lower margin / higher entropy = more uncertain = expected to mark improved questions.
- Consistency check: compare each re-run answer with the Step 5 cached answer (HotpotQA-normalised string equality; also F1 vs gold). Report the number of changed answers per branch. Labels (improved/tie/degraded) stay those from Step 5 per_question.csv. Primary AUC is computed on questions whose A and B answers are both unchanged; an all-questions AUC is reported as sensitivity. The Step 5 GO verdict is not re-decided on re-run answers.
- Comparison: report NLI AUC on the same question subset so the two signals are compared on identical data.
- Known limitations to disclose: the margin is a workaround for the API reporting 0 for the chosen token at temperature 0; it is not the same quantity as the chosen-token logprob planned for the local vLLM model. DeepSeek logprob distributions do not transfer to the main-experiment model; the pilot result is evidence about the signal type, not a tuned gate input.

## Step 5b prepared: top_logprobs re-run + margin-signal analysis (not yet run)
- Script: /workspace/exp/step5b/rerun_toplogprobs.py (+ README_step5b.md, test_step5b.py). Implements the [pre-registration](?plain=1#L199) as written: deepseek-chat, temperature 0, max_tokens 128, k=2, m=1, same prompts/retrieval/parsing (imports compare_models.py), logprobs=True, top_logprobs=5. 200 new calls; none reused from Step 5.
- Separate resume-safe cache <out>/cache_toplp.jsonl keyed (model, _id, branch, top_logprobs), also checked on k/m/temperature/max_tokens; errored calls are retried on resume. The script refuses any cache file named cache.jsonl, so Step 5 caches cannot be written.
- Metrics per branch: answer-span tokens located with the compare_models.summarize_logprobs rule (fallback to all tokens, counted); margin = top-1 − top-2 alternative logprob (alternatives sorted; <2 → missing); mean_margin (PRIMARY, branch A), min_margin, first-answer-token margin, mean entropy over renormalised alternatives; counts of chosen≠top-1, top-1 alternative exactly 0.0, chosen logprob exactly 0.0.
- Consistency vs Step 5 per_question.csv: HotpotQA-normalised equality per branch, new F1; consistency.csv lists CHANGED rows first. Labels = Step 5 delta_class; GO not re-decided.
- Analysis: improved vs tie AUC, bootstrap 95% CI (B=5000, seed 42) via analyze_signals.auc_score/bootstrap_ci. PRIMARY subset = A and B both unchanged; sensitivity = all. Every subset also requires a margin value and an NLI value, so NLI entailment_A AUC is computed on exactly the same questions. No gate threshold is selected.
- Implementation choices not fixed by the pre-registration: entropy also needs ≥2 alternatives (same rule as margin); the margin/entropy definitions are kept even when the top-1 alternative is reported as 0.0, and such tokens are counted for disclosure; if the endpoint rejects logprobs the script stops rather than falling back.
- Mock server step3/test_mock_server.py gained an opt-in --top-logprobs-mode deepseek_t0 (FAKE alternatives; chosen token 0.0 at T=0). Default behaviour is unchanged; Step 5 tests still pass (23/23).
- Tests: python3 /workspace/exp/step5b/test_step5b.py — 17 passed (margin/entropy on known numbers, span rule matches compare_models, AUC orientation, same-subset NLI, consistency, cache isolation/resume, analyze-only, mock end-to-end on mini_pilot.json with a SYNTHETIC per_question.csv, key not printed). All mock numbers are FAKE, not results.

Next: python rerun_toplogprobs.py --data pilot.json --step5-dir step5_pilot --out step5b_toplp

## Step 5b executed (re-run with top_logprobs=5)

**Run:** `python rerun_toplogprobs.py --data pilot.json --step5-dir step5_pilot --out step5b_toplp`; all 200 calls succeeded. Output: step5b_toplp/toplp_summary.json.

**Results:**

| Analysis | n | mean_margin_A AUC (95% CI) | NLI AUC, same questions (95% CI) |
|---|---:|---:|---:|
| Primary: A and B answers unchanged | 88 | 0.500 [0.500, 0.500] | 0.724 [0.593, 0.844] |
| Sensitivity: all questions | 100 | 0.482 [0.457, 0.500] | 0.699 [0.579, 0.812] |

- Answer consistency (HotpotQA normalisation): 9 changed in A, 4 in B, 12 distinct questions in total. Labels stay those of Step 5; the GO verdict is not re-evaluated.
- Of 3,482 output tokens (A 1,703, B 1,779), the top-1 alternative logprob is reported as 0.0 for all of them.
- 3,477 tokens have the top-2 alternative reported as -9999.0, so mean_margin_A = 9999.0 for all 88 primary questions.

**Interpretation:**
1. -9999.0 is a placeholder value meaning "probability negligible / not reported", not a real log-probability. At temperature 0, deepseek-chat therefore reports the chosen token at 0 and nearly all alternatives at the placeholder value. The pre-registered margin signal is degenerate, and AUC 0.500 means "no information", not "a weak signal".
2. Correction to the [probe entry](?plain=1#L192): "alternatives non-zero" counted -9999.0 as non-zero. The probe should have checked for placeholder values. This is a limitation of the probe check, recorded so the report does not cite that count as evidence of usable alternatives.
3. No post-hoc rescue: secondary signals computed from the same alternatives (min margin, first-token margin, entropy) rest on the same placeholder values, so they are not used as a substitute. Switching to temperature 1, or treating -9999 as a numeric value, would be a new, unregistered analysis and is not done.
4. The NLI signal is stable across subsets (0.699 on all 100, 0.724 on the 88 unchanged), so the Step 5 finding that NLI is a moderate signal holds.

**Conclusion for the paper:** in the pilot, the DeepSeek API at temperature 0 provides no usable token-level confidence signal (neither the chosen-token logprob nor the top-k margin). Logprob-based signals for the gate will be assessed only on the main-experiment local model (vLLM), after checking on the first 30 tune questions that its logprobs are non-degenerate: no all-zero chosen tokens and no placeholder alternatives.

## Step 6a prepared: local vLLM logprob degeneracy check (not yet run)

- Script: /workspace/exp/step6a/check_logprobs.py (+ README_step6a.md, test_step6a.py). Purpose: on the first 30 questions of the tune split, check whether a local model served by vLLM returns non-degenerate token logprobs. This gates whether logprob-based signals may enter the fuzzy gate in the main experiment. Prompt, BM25 retrieval (k=2), answer parsing and the OpenAI-compatible client are imported from compare_models.py; margin, entropy, answer-span location and the top_logprobs call helper are imported from rerun_toplogprobs.py (not copied). Branch A only, temperature 0, max_tokens 128, logprobs=True, top_logprobs=5. 30 calls.
- Default endpoint: model Qwen/Qwen2.5-7B-Instruct, base_url http://localhost:8000/v1, key from env var VLLM_API_KEY (optional; unset → placeholder EMPTY, never printed). If tune.json is not in the current directory, pass --data and optionally --n 30 --offset 0. The official file is tune.json (500 questions, seed-42 split).
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
- vLLM CLI: the official flag on current docs (https://docs.vllm.ai/en/stable/cli/serve/ and Engine Arguments) is `--max-logprobs` (default 20, which already allows top_logprobs=5). README describes starting with `vllm serve Qwen/Qwen2.5-7B-Instruct --host 127.0.0.1 --port 8000 --max-logprobs 5`, and reaching a remote GPU via an SSH tunnel (`ssh -N -L 8000:127.0.0.1:8000 gpu-host`) rather than publishing the port.
- Mock server step3/test_mock_server.py gained an opt-in `--top-logprobs-mode vllm_healthy` (FAKE ordinary negative chosen logprobs, never exactly 0.0, no placeholder alternatives; chosen equals top-1). Default remains `empty`; `deepseek_t0` is unchanged (chosen=0.0 at T=0, non-placeholder alternatives) so existing Step 5b tests keep their fixture. Step 6a uses `vllm_healthy` → PASS and `deepseek_t0` → FAIL (zero_chosen_frac and mean_chosen_logprob_spread; the current deepseek_t0 fixture does not emit -9999, so placeholder_alt_frac is not the failing item in that mock).

- Tests: python3 /workspace/exp/step6a/test_step6a.py — 16 passed (criteria on known numbers, including the four default thresholds, strict "under 5%", inclusive "at most 50%", incomplete runs, CLI overrides, cache isolation, key not printed, offset slice, analyze-only, and mock end-to-end on 30 SYNTHETIC questions). Existing tests still pass: step5 23/23, analyze_signals 6/6, step5b 17/17. All mock numbers are FAKE, not results. No real vLLM run has been made.

Next: start vLLM on the rented GPU (or tunnel to it) and run:
  python check_logprobs.py --data tune.json --out step6a_check

## Step 6a prepared: remote execution handoff

- Step 6a was to be operated on the existing GPU rental. The five project Python files required by Step 6a were verified byte-for-byte against the handoff archive.
- Local tune.json: 500 bridge questions, 500 unique IDs, no overlap with the 100 pilot IDs from the handoff archive. SHA-256: `478f6b2f4d7506a0b8d804de5aa077eacdd3ef20d90f127ac8d22999453ea53b`. The test split was outside this check.
- Direct batch-mode SSH reached the host, but the server requires authentication. A temporary SSH ControlMaster session was used to reuse the existing authenticated connection without handling passwords or changing remote authentication settings.
- No model calls were made during preparation. Step 6a settings and criteria follow the [entry](?plain=1#L241).

## Step 6a prepared: server environment and model provenance

- GPU server: NVIDIA Tesla T4, compute capability 7.5, 15,360 MiB total and 14,928 MiB free at takeover, driver 535.216.01. Host RAM 30 GiB; home filesystem had 78 GiB available. Python 3.10.12 and tmux were present; no vLLM on PATH, no running GPU compute workload, and port 8000 was free.
- Copied the five original Step 6a scripts and tune.json to ~/nlp. All six SHA-256 checks passed on the server. Existing experiment scripts were not edited.
- Deployment decision before inference: install vLLM 0.8.5 in an isolated project environment, with Transformers 4.51.3, OpenAI client 1.76.2 and rank_bm25 0.2.2. This vLLM release documents T4 support and provides CUDA 12.4 binaries. A clean, pinned install is reproducible and isolates package changes. An unpinned install could select a newer CUDA build that requires a newer driver; changing the system GPU driver would expand the setup and disrupt the existing rental image. Reference: https://docs.vllm.ai/en/v0.8.5/getting_started/installation/gpu.html
- Model delivery decision: Hugging Face was unreachable from the server; the Qwen-published ModelScope repository was reachable. Use that repository to obtain the original, unquantized checkpoint and verify shard SHA-256 hashes and Git blob IDs for supporting files against Qwen's Hugging Face revision a09a35458c702b33eeacc393d103063234e8bc28. The model name alone cannot establish that two downloads are identical. The seven supporting files matched the Hugging Face Git blobs. Weight verification is pending.
- Started the environment install and model download under separate tmux sessions. No model inference or threshold changes.

## Step 6a decision: package mirror for this host

- The first package install stalled on the pip wheel. A one-MiB range test against the official PyPI wheel reached only about 19 kB/s before timing out. The Tencent Cloud internal mirror completed the same range. Restarted the isolated install through that mirror, identified by https://mirrors.tencentyun.com/pypi/simple, with the existing version pins. Preserved the original install log and requested a package download report. This changes delivery only. No experimental outputs were available.

## Step 6a prepared: serving parameters before model calls

- Successful GPU smoke test: vLLM 0.8.5, PyTorch 2.6.0+cu124, CUDA 12.4, xFormers 0.0.29.post2, Tesla T4 compute capability 7.5. `pip check` reported no broken requirements.
- Use vLLM V0 with xFormers attention, FP16 (`--dtype half`), and the original unquantized Qwen/Qwen2.5-7B-Instruct weight files. Use `--cpu-offload-gb 4 --enforce-eager --max-model-len 4096 --max-num-seqs 1`. FP16 fits T4's supported precision. CPU offload and eager mode reduce peak GPU memory while preserving the checkpoint; weight quantization or a smaller checkpoint could change the logprob distributions being measured. CPU offload can increase latency. The client sends one request at a time, so limiting concurrent sequences to one does not reduce the requested workload. Reference: https://docs.vllm.ai/en/v0.8.5/serving/engine_args.html
- Offline length preflight rebuilt the same first 30 branch-A prompts and applied the verified Qwen chat template without truncation: 247–608 prompt tokens. Longest prompt plus 128 output tokens is 736, under the 4,096-token service limit. No generation was requested in this preflight.
- Server binds 127.0.0.1:8000 and advertises the original model name; max logprobs is 5, with the original model generation config. The client uses the existing script, first 30 rows of the input already verified on the server, branch A, temperature 0, max_tokens 128, top_logprobs 5, and default decision thresholds.
- To reduce transfer time, switched shards 1 and 4 to independently verified HTTP range downloads after observing slower single-transfer speeds. Retained both existing partial prefixes. Final acceptance requires all four full-file SHA-256 hashes to match Qwen's published Hugging Face hashes.

## Step 6a prepared: confirm existing logprob precision

- Code review before seeing Step 6a outputs: the reused Step 5b extractor rounds returned token logprobs to six decimal places before writing the cache. The shipped Step 6a implementation therefore counts exact zero at that retained precision, consistent with the threshold rationale allowing sufficiently small values to round to zero. A sufficiently small nonzero raw value can contribute to the reported zero fraction. For criterion 1, this is conservative relative to counting exact zeros on the unrounded response. Per-question means are compared at six decimal places for the distinct-value criteria per the [entry](?plain=1#L241).
- Retained the shipped implementation and original criteria. Any request for a different raw precision would be a separate analysis, not a substitute for the registered result.

## Step 6a prepared: fixed server startup dependency

- Confirmed all four safetensors shard SHA-256 hashes matched Qwen's Hugging Face revision. Match of the seven supporting file Git blob IDs had already been confirmed. The installed vLLM, PyTorch, xFormers, Transformers, OpenAI and rank_bm25 wheel hashes also matched official PyPI metadata.
- The first vLLM startup exited during Triton import because the isolated environment was missing setuptools. The health check prevented any model calls; the Step 6a cache had not been created. Added setuptools 80.9.0 in the same isolated environment, ran `pip check`, and regenerated the environment lock. Preserved the first-launch logs and restarted with the same model, serving flags and Step 6a arguments. Completing the missing runtime dependency preserves the registered protocol.

## Step 6a executed on the rented GPU server — verdict PASS

- Real inference ran over the authenticated SSH connection. Verified 30 HTTP 200 completion requests, 30 new responses, 0 cache hits, and 0 errors/unusable questions. 30/30 scheduled questions had usable logprobs.
- Model: Qwen/Qwen2.5-7B-Instruct, original unquantized checkpoint, Hugging Face revision a09a35458c702b33eeacc393d103063234e8bc28 verified by full-file hashes, served by vLLM 0.8.5 in V0/XFormers mode with FP16 and 4 GiB CPU offload on Tesla T4. Verified listening only at 127.0.0.1:8000. Client: `.venv_step6a/bin/python -u check_logprobs.py --data tune.json --out step6a_check --base-url http://127.0.0.1:8000/v1`. First 30 tune questions, branch A, k=2, temperature 0, max_tokens 128, top_logprobs 5.
- Pre-registered criterion 1 PASS. Chosen-token zero fraction on the answer span (including the pre-registered fallback): 28/127 = 22.05%, threshold ≤ 50%. Zero means zero at the six-decimal precision of the reused token extractor.
- Pre-registered criterion 2 PASS. Alternatives at logprob ≤ −9000: 0/2595 = 0.00%, threshold < 5%.
- Pre-registered criterion 3 PASS. Per-question mean chosen-token logprob: 30 distinct rounded values across 30 questions, population variance 0.023727663329. Required ≥ 10 and > 0.
- Pre-registered criterion 4 PASS. Per-question mean top-1 minus top-2 margin: 30 distinct rounded values across 30 questions, population variance 15.391864434601. Required ≥ 10 and > 0.
- Descriptive only: 519 output tokens, with 209 zero chosen-token logprobs across all output tokens. Answer-span fallback on 1 question. 30/30 answers parsed, EM 0.400000, F1 0.537460. No AUC and no threshold selection in this step. Client request latency on this setup: median 7.471 s, min 6.190 s, max 11.190 s. The service reported 247–608 prompt tokens, matching the offline preflight.
- Artifacts on the server: `~/nlp/step6a_check/` contains `logprob_check.json`, `logprob_check_tokens.csv`, and `cache_logprob_check.jsonl`. Mirrored to the local `step6a_check/` directory. All three output SHA-256 hashes matched after transfer. Independently recomputed the four criteria from the cached compacted token values and CSV span flags and confirmed the JSON verdict, sample order, and settings.
- Server retained in tmux session `nlp6a-vllm` with the verified local model. Serving wrapper and package lock are under `~/nlp/.serve-step6a.sh` and `~/nlp/logs/requirements-step6a.lock`.

## Decision: logprob-based features are eligible for tune-stage evaluation

- Step 6a establishes non-degeneracy under this checkpoint, engine and configuration. Mean chosen-token logprob and mean margin can be evaluated as candidate features on the tune split. Their ability to identify questions improved by re-retrieval and their incremental value relative to NLI still require a pre-registered tune-stage analysis.
- The alternative of excluding logprobs based on the DeepSeek pilot would discard locally usable measurements on the basis of a different endpoint. Including logprobs directly in the locked gate would assume predictive value that this diagnostic does not measure. The tune-stage comparison resolves that choice before formal testing.

## Decision: follow Protocol V2 as written for the remaining experiment

- Subsequent experimental work must follow Protocol V2 strictly. Use the PDF's stated sequence and requirements, with the previously fixed settings recorded in this log. Keep unresolved template fields explicit.
- Clarification to the preceding status discussion: V2 sections 7.3 and 10.1 step 3 specify a pilot-split signal check for NLI and bridge-entity coherence at similar re-retrieval rates against random selection or a single threshold, examining improved and degraded selections. V2 does not prescribe a specific combined score. The existing pilot entailment AUC is a separate descriptive diagnostic. The comparison method and re-retrieval rate in section 7.3 are still marked pending in V2, and the log does not establish them as pre-registered for the existing pilot. Any newly chosen settings must be dated accurately; they cannot be described as registered before the pilot results were seen.
- Step 6a PASS stays a non-degeneracy result. V2 leaves the uncertainty metric and its inclusion in the main experiment conditional. If confirmed and included, the uncertainty input must be shared by Fuzzy and the same-input crisp rule. The earlier discussion of evaluating particular logprob features on tune is a candidate plan, not a V2 requirement.
- Section 10.1 step 4 then tunes Fuzzy and the same-input crisp rule on dev against a common target re-retrieval rate and locks the parameters and prompt/query-rewrite versions. No new experiment, signal formula, threshold or comparator was adopted in this entry.

## Prepared: V2 §7.3 pilot signal check input audit

- Verified that the packaged pilot.json matches the original handoff byte for byte and contains 100 distinct bridge IDs. The real manual-review CSV covers 20 branch rows from 15 questions. The Step 2 CSVs are retrieval-only and the bundled Step 3 branch outputs are mock artifacts.
- The real Step 5 per_question.csv and branches.jsonl are listed in the run log under step5_pilot/ but are absent from the local project and handoff archive. The production writer confirms that per_question.csv supplies A/B answer scores, delta labels, retrieval/citation fields, and per-branch NLI scores. branches.jsonl preserves structured branch evidence for the bridge check. Request the two original exports.
- V2 §4.1 leaves the bridge-entity signal definition open, and §7.3 leaves the comparator and re-retrieval rate open. No recorded settings were found in the experiment log. Pilot results are already known, so this input audit does not retroactively pre-register new settings. The check is pending the original data and the recorded choices. No new inference or signal comparison was run.

## Prepared: received Step 5 pilot signal check exports

- Received per_question.csv and branches.jsonl in the local project root. Each has 100 distinct question IDs matching the original pilot split. Confirmed A/B score, class, citation and A-side NLI columns in the table, and structured A/B, first-round retrieval indices and NLI fields in the branch records.
- SHA-256: per_question.csv `ae8aaf299b0ac3bc40732153ba7858e56f3ef0676eb6deee6ab91c5381f4ae05`; branches.jsonl `1887083d6bfa7a4a2e476ce500b3cf122dd96dcf2e6eda1789cbd4c1064ada85`.
- This closes the export availability gap recorded above. The V2 bridge signal definition and comparison settings remain pending. Input checks used record identities and schema only; no new signal comparison was performed.

## Prepared: candidate settings for the V2 pilot signal check

- Proposed scope: an offline, supplemental §7.3 comparison on the existing 100-question pilot cache. The 16 improved, 82 tie, and 2 degraded totals are already known. Record any adopted settings before the new comparison, under their actual date. Preserve the original GO criteria and conclusion.
- Proposed signals: A-side entailment only for the NLI component. Defer model uncertainty in this pilot. Use a binary bridge proxy based on whether either first-round retrieved paragraph's body contains the other paragraph's full title as a contiguous normalized whole-word sequence. Search both directions. Use Unicode normalization, case folding and consistent word boundaries, retaining disambiguating title words and numerals. A match is evidence of a visible lexical link, not entity resolution or proof of support. Fewer than two distinct usable paragraphs makes this feature unavailable and falls back to NLI ranking. Use no gold evidence, gold answers, B-side values or labels in ranking.
- Proposed main comparison: lower A-side entailment alone versus a fixed equal-weight average of the NLI risk rank and the bridge-absence risk rank. Use tied midranks within each signal and a fixed seed/ID-based tie rule at the selection boundary. This is a pilot score, not the final fuzzy method. Also report the uniform random expectation at the same budget as a descriptive reference.
- Proposed common pilot budget: 20 of 100, a subjective choice informed by the known pilot aggregate. This leaves four extra selections relative to the 16-question hindsight Oracle trigger count. Random selection at this budget has expected improved/degraded counts of 3.2/0.4 from the known class totals. Report selected improved and degraded counts separately and do not infer safety gains from sparse degraded cases. The formal dev target, final fuzzy inputs and membership functions remain to be decided under V2.
- The 20-row manual NLI review stays qualitative. The protocol's unacceptable-error cutoff has no prior value recorded and is not assigned retroactively. No new data runs, feature scores, comparison outcomes or adopted settings in this entry.
- Input feasibility check only: 100/100 rows have a finite A-side entailment in [0, 1], and all 100 branch records resolve to two distinct first-round paragraph indices with nonempty titles and bodies. This check did not evaluate the title-matching rule.

## Prepared: comparative rationale for the proposed V2 pilot settings

Status: rationale for the [candidate settings](?plain=1#L362). These settings were not yet adopted. The purpose of the supplemental §7.3 comparison is to see whether bridge evidence improves selection beyond NLI at the same re-retrieval rate, using the same 100 cached A/B pairs.

### A-side entailment and model uncertainty

- A-side entailment is already available for all pilot questions and measures how strongly the first-round cited evidence supports the draft answer. The existing pilot AUC establishes a useful direction to examine, with lower entailment indicating higher priority for re-retrieval. That diagnostic covered improved vs tie, so the proposed budget-matched comparison would account for degraded questions as well.
- Neutral and contradiction could distinguish missing support from conflicting evidence. Adding them would require decisions on whether these cases should trigger re-retrieval at different rates and how their scores enter the rule. Using entailment in both comparison arms keeps the NLI score fixed, which makes the incremental effect of adding the bridge proxy easier to interpret.
- Defer model uncertainty for this pilot. DeepSeek logprobs at temperature 0 were degenerate in Steps 5 and 5b. Step 6a established non-degeneracy for Qwen, whose logprobs pertain to Qwen generations. Introducing that measurement would move the comparison to a different model and require a matching A/B cache. V2 leaves adoption of the uncertainty metric conditional.

### Bridge-entity proxy

- The full-title rule is motivated by the original HotpotQA construction. Candidate paragraph pairs were drawn from a Wikipedia hyperlink graph, and the destination article's entity can connect the two paragraphs. The proposed rule looks for a visible lexical connection in either direction between the two retrieved passages. It uses only first-round information. Gold answers, supporting facts, B-side outputs and F1 labels are reserved for scoring. [Yang et al., 2018, §2](https://aclanthology.org/D18-1259.pdf)
- Full-title whole-word matching makes a hit auditable by paragraph, title and text span. Its main cost is missed abbreviations, alternate spellings, aliases, pronouns and titles with disambiguators omitted in prose. Incidental mentions can also produce hits. The indicator measures a visible lexical link and serves as a proxy for coherence.
- Alias or partial-title matching could recover some missed links, with more ambiguity from shared surnames, place names and generic terms. It would require an alias source or fixed matching rules. An entity linker could resolve additional aliases and some ambiguities, with additional runtime, dependencies and model-specific errors. The full-title rule is preferred for the first check because it gives a reproducible error trail with the existing cached evidence. Its adequacy remains an empirical question.

### Comparator and ranking

- Use the NLI-only threshold as the primary comparator. It answers how many additional improved or degraded questions the bridge signal changes when the number selected and NLI input are held fixed. A comparison with random selection alone cannot attribute any advantage to the bridge signal because NLI could account for the entire difference. Retain the fixed-budget random expectation as a descriptive chance reference.
- The proposed equal-weight average of risk percentiles puts a continuous NLI score and a binary bridge indicator on a common ranking scale. Directly averaging the raw values would let their different distributions affect the strength of each signal. Optimizing weights on this already observed pilot would add tuning choices and favor the same sample used for the check. Equal weights give a reproducible pilot specification, with no evidence that they are optimal.
- Equal rank weights allow a substantial bridge effect. With both binary groups present and 100 questions, the groups' midranks differ by 50 positions. With percentiles defined as (rank − 1) / 99 and 50/50 averaging, the bridge indicator alone can shift the combined score by about 0.253. Giving NLI more weight would limit changes from the still-unvalidated proxy, with the tradeoff of a weaker probe of the bridge signal. The weighting remains a candidate specification. Dev is the stage for locking the formal fuzzy and same-input crisp gates.

### Common pilot budget

- At 10 selections, even a perfect ranking can recover at most 10 of the 16 improved questions. At 16 selections, recovering all improved questions requires every selection to be correct. A budget of 20 can cover all 16 and leaves four selections for ranking errors. It still limits re-retrieval to one fifth of the questions, making it a reasonable operating point for testing selectivity.
- Budgets of 25 or 30 would leave more room for misranked items and could be appropriate if reducing missed improved questions were the overriding priority. The current motivation is to test the signals under a relatively tight budget. There is no comparative result supporting 20 as preferable to 25 or 30. The budget is a subjective proposal informed by the known pilot class counts. Record any adoption before the supplemental comparison with the actual decision date. The V2 dev target rate is a separate choice.
- Report improved and degraded selections separately. A sample with only two degraded questions gives little information about avoiding harmful re-retrieval. The manual NLI audit is also qualitative because its 20 branch-level rows were selected for error inspection and cover 15 distinct questions. This supports keeping the protocol's previously unset unacceptable-error cutoff unfilled for the completed pilot.

No setting was adopted and no signal comparison was performed in this entry. The original pilot registration, observations and GO verdict are preserved.

## Decision: settings for the V2 §7.3 supplemental pilot comparison

- The candidate settings and comparative rationale above were adopted. Compare A-side entailment alone with the equal-weight average of the NLI and bridge-absence risk percentiles. Use the original 100 Step 5 pilot questions and the same A/B variants. Both strategies select exactly 20 questions. Report selected improved, tie and degraded counts, the difference in improved and degraded counts, and the theoretical expectation from choosing 20 questions uniformly without replacement. Both counts remain distinct outcomes. An equal degraded count is a tie on that outcome.
- Bridge implementation fixed before scoring. Use the two A-side BM25 paragraph indices and search both directions for a full normalized title in a sentence of the other paragraph's body. Normalize with Unicode NFKC and case-folding. Use continuous sequences of whole Unicode alphanumeric tokens, dropping punctuation as separators and keeping title words and numerals. Match within a sentence to avoid artificial phrases across boundaries. A hit has bridge-absence risk 0, and no hit has risk 1. Unusable or fewer than two distinct paragraphs produce missing bridge risk and use the NLI percentile in the combined ranking. No aliases, substring matches, or gold annotations enter the detector.
- Use negative A-side entailment to orient higher risk. Compute each signal's percentile as (midrank − 1) / (n − 1), averaging ranks on feature ties. Rank usable bridge values only. When at most one usable bridge score exists, use the NLI ranking for all questions because a bridge percentile cannot distinguish them. Average the two percentiles at 50/50 where both are available. Order boundary ties by ascending SHA-256 of UTF-8 text `42:<_id>`, with lexicographic ID fallback in case of a hash collision. Seed 42 matches the existing project convention and is fixed in advance of any new selection output.
- Validate the three input files agree by question ID and that the stored branch F1, A-side entailment, and delta class agree across exports. Rank first from A-side evidence and NLI only, then use the stored classes, checked with epsilon=0 from the paired cached F1 scores, to read out outcomes. Use no B-side or gold values to construct ranks.
- This is a supplemental offline comparison selected after the original pilot aggregate was seen. The 20% budget and 50/50 weight are subjective settings fixed before this comparison only. It does not reopen the original preregistered GO verdict, decide formal Fuzzy parameters, or choose the dev target rate. Model uncertainty stays deferred for this pilot; the NLI audit remains qualitative. No new scores or results were read before this entry.

## Prepared: V2 §7.3 offline comparator and synthetic tests

- Added analyze_pilot_signals_v2.py, test_pilot_signals_v2.py and the Chinese README_pilot_signals_v2.md. Reused compare_models.py for the epsilon-zero class rule and analyze_signals.py for loading the table and numeric scores. The script reads the three original exports, validates cross-file identities and values, ranks using A-side features, and writes audit files to a new output directory. It makes no API or NLI calls.
- New tests 8/8 passed using synthetic fixtures and the unchanged Step 3 mock response generator. Existing suites also passed: Step 5 23/23, analyze_signals 6/6, Step 5b 17/17, and Step 6a 16/16. The initial local test environment lacked rank_bm25, and the old HTTP mock health checks timed out under the proxy settings. Installed dependencies into a temporary Python path and ran the HTTP regressions with loopback excluded from proxying. No historical script or mock was edited. Mock data are synthetic.
- Settings match the preceding decision entry. Output paths: pilot_signals_v2/summary.json and pilot_signals_v2/per_question_selection.csv. About to execute on the original data for the first time.

## Executed: V2 §7.3 supplemental pilot signal comparison

- Ran locally on the original Step 5 pilot exports with the fixed 20-question budget, 50/50 risk-rank combination, and recorded title normalization and tie rule. The three input files agreed on all 100 bridge IDs. Their hashes are in summary.json. No new inference was requested.
- Pilot totals agreed with the original log: 16 improved, 82 tie, 2 degraded. The first-round bridge proxy returned 34 linked, 66 unlinked, and 0 unavailable. Each lexical match is traceable by source paragraph, target paragraph and sentence index in per_question_selection.csv.

| Strategy | Budget | Improved selected | Tie selected | Degraded selected |
|---|---:|---:|---:|---:|
| A-side NLI entailment alone | 20/100 | 6 | 14 | 0 |
| A-side NLI + bridge proxy, equal rank weights | 20/100 | 6 | 14 | 0 |
| Uniform random selection, theoretical expectation | 20/100 | 3.2 | 16.4 | 0.4 |

- The two selections shared 19 questions. The NLI-only selection's one replaced question was tie, and its replacement under the combined rule was tie. Combined minus NLI was zero on both the improved and degraded counts. Both observed improved counts exceeded the random expectation descriptively.
- Under this proxy, weighting, budget and pilot set, the combined rule showed no observed incremental gain over NLI on either outcome. There are only two degraded questions in the pilot, so the zero selected by both strategies provides limited information on harmful re-retrieval. This supplemental diagnostic does not establish equivalence, rule out other bridge measurements, reopen the original pilot GO, or decide formal dev inputs.
- Independently rebuilt title matches with token-window comparisons and rank percentiles by counting lower scores and ties. Confirmed both 20-question lists, their class counts, and both output files against the source hashes. The two artifacts are pilot_signals_v2/summary.json and pilot_signals_v2/per_question_selection.csv.

## Prepared: V2 §7.4 sample-size and compute planning

- For V2 §10.1 step 3 closeout, compare the current 1,000-question formal test split with a hypothetical 500-question evaluation drawn from the reserved test split. Use the original Step 5 pilot paired answer F1 differences and its observed improved proportion. Report the sample SD of B minus A and Oracle minus A, and illustrate the change in approximate mean-difference precision with half-width 1.96 × pilot SD / sqrt(n). These are descriptive planning quantities based on known pilot data. They do not estimate power for Fuzzy versus the same-input crisp rule or assume Qwen will replicate the DeepSeek pilot.
- Count answer requests required by V2 for each sample-size scenario: two cached branches per tune and test question and one separate Full-context call per test question. Use the arithmetic mean from the existing 30 successful local Step 6a A-side calls as a constant-latency reference. This reference assumes sequential requests and equal duration per call. B and Full-context have not been timed. Real-path latency runs, NLI, retries, transfer and setup are additional. No rates or available hours have been inferred.
- Keep the split manifest and formal method settings distinct. Use the logged official HotpotQA distractor validation source, bridge-only restriction, seed 42, and disjoint pilot, tune and test split. Read the saved pilot outputs and Step 6a cache only. Do not evaluate test questions or tune a gate in this closeout.

## Executed: V2 §10.1 step 3 closeout assessment

- V2 §7.3 readout is complete. Original Step 5 GO remains the pilot's preregistered outcome. The supplemental bridge comparison found zero changes in the selected improved and degraded counts at 20% with the full-title proxy and equal rank weights. The manual NLI review remains qualitative.
- Proposed formal sample under V2 §7.4: the existing 1,000-question reserved test.json. Source is Hugging Face hotpotqa/hotpot_qa, distractor config, public validation split (the official development data). Scope is bridge questions. The original seed-42 sequential split was pilot 100, tune 500, test 1,000, with 1,600 distinct IDs verified in Step 1. A recheck verified 100 pilot and 500 tune IDs, with no overlap, and the tune copy matched the archived copy byte for byte. The reserved test file was not available and its IDs and hash were not independently rechecked in this closeout. Test list path is recorded above.
- Descriptive sample-size evidence. In the 100 original pilot pairs, B minus A had mean 0.124 and sample SD 0.349926. Oracle minus A had mean 0.137333 and sample SD 0.328185. The 16% observed improved share would correspond to 80 or 160 improved cases at n=500 or n=1,000 if the rate transferred unchanged. Normal-reference half-widths for a mean pair difference with the same SD were respectively 0.03067 and 0.02169 for B minus A, and 0.02877 and 0.02034 for Oracle minus A. These are planning illustrations. No paired variance for Fuzzy minus the same-input crisp rule is available yet.
- Compute reference. The 30 real Step 6a local Qwen A calls took 229.5538 seconds in total, mean 7.651793 seconds per call on the Tesla T4 with the logged CPU offload configuration. A 500-question test requires 1,500 planned answer requests for A, B and Full-context. The current 1,000-question test requires 3,000. At the A-side mean for every request in a sequential scenario, test reference times are 3.188 or 6.376 hours. The fixed 500-question tune cache contributes 1,000 additional A/B requests or 2.125 reference hours. Combined tune and test scenarios are 5.314 and 8.502 hours respectively. The reference excludes NLI, separate real-path latency runs, retries, and setup. B and Full-context latency and available GPU time remain unverified.
- Recommendation subject to the compute budget. Prefer the existing 1,000-question split. It offers more expected improved cases and approximately 29% narrower reference intervals under the pilot-variance assumption, while 500 halves the planned test-generation calls. The 1,000-question recommendation does not establish formal power for the primary gate comparison. Available GPU time must be confirmed before locking the formal sample size.
- Proposed handoff to dev. Keep A-side entailment and the existing bridge proxy as candidates for the paired dev comparison. The pilot result describes one proxy, one weighting and one budget. Dev remains the place to confirm the shared input set, set the common target re-retrieval rate and lock the two gates and prompt/rewrite versions. Model uncertainty inclusion remains a separate V2 decision. No dev or test generation was run in this closeout.

## Decision: lock the 1,000-question formal test split under V2 §7.4

- GPU time has no fixed upper limit for this round. Adopt the existing 1,000-question reserved test split based on the preceding sample-size assessment. The larger split improves reference precision and provides more opportunities to observe improved questions. The 8.50-hour tune-plus-test figure remains a scenario based on A-side request timing. B-side and Full-context timing, NLI and real-path measurements will be recorded during execution.
- Fixed evaluation data: Hugging Face `hotpotqa/hotpot_qa`, `distractor` config, public `validation` split, bridge only. Use the original seed-42 sequential split: 100 pilot, 500 tune, 1,000 formal test. The authoritative formal manifest is `test.json`. Step 1 verified 1,600 unique IDs across all three files. The original test manifest remains the authoritative copy per the preceding assessment.
- This closes V2 §10.1 step 3. Step 4 is next: cache A/B outputs on the 500-question tune split and tune Fuzzy and the same-input crisp rule at a shared target re-retrieval rate before locking the gates and running the formal evaluation.

## Prepared: V2 step 4 paired tune generation

- Use all 500 seed-42 tune questions (SHA-256 478f6b2f4d7506a0b8d804de5aa077eacdd3ef20d90f127ac8d22999453ea53b). Endpoint health and Step 6a input checksums verified on the rented T4. Reuse the existing original Qwen2.5-7B-Instruct checkpoint, vLLM 0.8.5, unchanged Step 5 prompt and retrieval/query rewrite, k=2 and m=1, greedy temperature 0 and max output 128 tokens. Preflight both branches against the 4,096-token service cap. Generate one fresh A/B pair per ID under the same request path, using a tune-only cache for resumption.
- Stage A/B generation with the original run_pilot.py in answer-only mode and preserve raw answers, parsing, citations, latencies and token counts. The inherited pilot GO footer is bookkeeping only. Score the cached generations with the original three-way DeBERTa checkpoint and the established 512-token premise/hypothesis format. Reuse the fixed full-title bridge feature on first-round passages. Formal gate calibration is dev-only. Implementation and tie handling for both gates will be recorded before their dev outcomes are examined.

## Decision: V2 step 4 calibration specification

- Freeze the calibration protocol before review of dev outcomes. Use A-side DeBERTa entailment risk r=1−entailment and the previously fixed first-round full-title bridge indicator as the two inputs to both policies. The bridge stays in the shared comparison because its pilot result only describes one ranking at one budget. Defer the optional logprob input under V2 §4.1 so this comparison isolates the two fixed signal types. Retained answer-cache logprobs are independent diagnostic data. A missing bridge indicator removes its contribution and uses only the NLI rule.
- Fixed shared dev target is 20% or 100 of 500 questions. This carries over the operating point already used for the pilot comparison and gives a meaningful retrieval saving at an outcome-independent budget. It is a chosen dev design setting, not a fitted rate or a numerical promise on the held-out split. Fuzzy, crisp, and NLI-only all use this dev budget.
- Fuzzy uses zero-order Sugeno inference with two complementary piecewise-linear NLI memberships. For anchors lo and hi, high-risk membership h=clamp((r−lo)/(hi−lo),0,1) and low-risk membership 1−h. Bridge present/absent uses singleton memberships from the binary detector. The four shared rule consequents (NLI low/high) are (0,1−w) with bridge present and (w,1) with bridge absent. Product firing and normalized weighted mean give score (1−w)h+w times the bridge-absence indicator. With missing bridge use h. Same-input crisp uses those same inputs, anchors and rule consequents, with hard h=1[r≥(lo+hi)/2]. This holds the rule structure fixed while varying the NLI membership.
- Candidate grid uses linear empirical dev quantiles for lo at .10/.25/.40 and hi at .55/.70/.85, skips equal anchors, and uses w in .125/.25/.375. If all quantile anchors collapse, use (0,1) with the same weights. Tune each policy over the same grid for maximum total paired F1 gain at 100 selections, breaking candidate ties by fewer degraded selections, then more improved selections, then the first grid entry. Use mean F1 and realized retrieval rate plus EM and improved/tie/degraded for descriptive dev readout. These are fitted dev results.
- Rank both policies by score descending, then shared A-side entailment risk descending, then SHA-256 of UTF-8 `42:<_id>` ascending and ID ascending. The common secondary risk key avoids giving crisp an arbitrary selection based on input ordering within its discrete score bands. Lock each policy's dev boundary tuple and apply it per question on future evaluation, with no re-ranking to force 20% on the test split. The NLI-only comparator uses the same selection procedure with its risk as primary score. Preserve the checkpoint, prompt, BM25 and rewrite versions with the selected parameters.
- Answer jobs started on the verified tune hash and the prior vLLM service. All 1,000 prompt lengths via the pinned tokenizer fit the existing cap: A 196–793 tokens and B 235–1,494, before the 128-token completion allowance. One question has no unused paragraph to add and stays in the paired dataset under the existing retrieval behavior. Remote outputs are under `~/nlp/step4_dev`. No held-out test generation is part of this step.

## Running: V2 step 4 paired answers and calibration pipeline

- On the T4, tmux `nlp-v2-tune` started at [time omitted] with the existing answer-serving configuration. The verified upload of run_pilot.py had SHA-256 47b288beb379f48b3dbd36c8570a696f64c52c3348279692b9334025c1e1834f. Each request persists to `step4_dev/answers/answers_v2_dev.jsonl`. The first progress check confirmed 66 generated cache rows at [time omitted]; count is a progress indicator.
- DeBERTa snapshot pinned to b3546ea6b0346eb6f8d5d68b13c7dc6d0376b3d7. Downloaded over a separate connection because the remote Hugging Face connection timed out. Verified safetensors SHA-256 c03cd208bf920b4fbbb182a0535859a566e8acc3477d2b536bf87b769978524b against the publisher, and all seven downloaded files after transfer. The original NLI wrapper passed a synthetic three-label smoke on CPU from the downloaded snapshot. The real run uses CUDA batch 4 with the existing 512-token scorer.
- Added `calibrate_gates_v2.py`, `test_calibrate_gates_v2.py`, `run_step4_v2.sh`, and `README_step4_v2.md`. The three new synthetic calibration tests and eight existing bridge-signal tests passed. Shell syntax checks and remote script checksums passed. The fixed calibrator will write the policy, provenance hashes, dev summary, and per-question decisions.
- Worker `nlp-v2-finish` is queued on the experiment host. It validates both branches for each of the 500 IDs, retries failed or missing answers once with the original parameters, scores the cache, and calibrates and locks both policies. To free GPU memory for the NLI scorer it temporarily stops the original Qwen tmux service after both branches are complete and restores it on worker exit. All job paths and recovery instructions are in the step 4 README.

## Decision: validate batched tune generation on the same checkpoint

- Serial progress reached 101/1,000 recorded requests at [time omitted]. At the observed rate, about two hours remained. Adopt an eight-sequence service candidate to amortize CPU weight offload across requests. Keep the verified checkpoint, FP16 dtype, vLLM 0.8.5 V0/XFormers, memory offload, prompt, max context, decoding and tune data fixed. Keep the serial cache for recovery. In the batch trial generate all 1,000 branches in a fresh run and keep the caches separate, since scheduling may change numerical rounding. No dev scores were read to decide this change.
- Use eight round-robin ID shards with independent cache files and reassemble the 500 A/B pairs by the original input order. Select the run based on operational stability and throughput only. The final gate lock will include the hash of the run's serving script.

## Running: clean eight-sequence Qwen tune generation

- Preserved the 127 recorded serial answer rows under `step4_dev/serial` at [time omitted]. The eight-sequence CUDA service became healthy at [time omitted]. Its launch script `.serve-step4.sh` (SHA-256 fc82bca4e12c5e3f067ae50fd1b3433dc6ceb44067dd397e0ddd78f95113af7a) differs from the Step 6a script only in `--max-num-seqs 8`. Both tmux workers were restarted with the verified batch scripts. The first check saw 7 new branch rows. The serial rows are kept outside the active cache.
- A synthetic 500-ID shell test verified deterministic shard assignment and canonical A/B order, validated the merge, and verified error archival and recovery to all 1,000 branches on resumption. Shell syntax and gate calibration tests also passed. Per-shard caches support resuming the active job. The finishing worker uses the batch serve script in the lock provenance and for restoring Qwen after CUDA NLI.

## Executed: V2 step 4 dev calibration and gate lock complete

- Eight-sequence Qwen generation ran [time omitted] to [time omitted]. All 1,000 answer branches for 500 unique tune IDs were validated with zero failed or incomplete records. DeBERTa CUDA scoring covered all 1,000 branches, beginning at [time omitted]. The gate lock was written at [time omitted]. Qwen was restored with the eight-sequence launch script. Remote status and its health check both passed.
- Existing response and NLI handling was exercised. Parse fallbacks A/B were 1/0. NLI truncations A/B were 1/5 and the retrieved-premise fallback counts were 7/2. The title-based bridge signal was present on 175 of 500 questions. Explicitly retain the one pair lacking an extra paragraph as recorded in preflight.
- Same-input dev selections at the fixed 20% target: Fuzzy F1 0.536217749, EM 0.398, with 25 improved / 69 tie / 6 degraded. Crisp F1 0.535208225, EM 0.396, with 26 improved / 69 tie / 5 degraded. The two gates selected 85 common IDs and differed by +0.001009524 F1 on the fitted tune sample. NLI threshold F1 0.532084416. Never, Always and Oracle F1 respectively 0.500163781, 0.572603535, 0.607622511. These are dev calibration results.
- Locked the models, two shared inputs, 27-candidate search outcome, retrieval/prompt implementation hashes, and per-question boundary tuples in `step4_dev/gates/locked_gates.json`. Fuzzy anchors and bridge weight are {'lo': 0.0005892496127476443, 'hi': 0.381526725198905, 'bridge_weight': 0.375}. Crisp anchors and bridge weight are {'lo': 0.0005892496127476443, 'hi': 0.0075008252711235195, 'bridge_weight': 0.125}. Model uncertainty is deferred under the recorded step 4 design. The final test is reserved for V2 step 5.
- Archived the raw paired answers, scored branches, NLI scores, gate selections, summaries and serving script under local `step4_dev/`. Compared each file against the GPU's checksum manifest. Independently verified provenance hashes, all 500 paired IDs, all 1,000 NLI records, all three locked boundaries for every dev ID, selected label counts and F1/EM recomputation.

## Prepared: V2 §10.1 step 5 formal evaluation specification

- The existing 1,000-item test.json was used. Verified its SHA-256 is 6d9acf8c4b759406b206f82cd01da7c575046bc584259d9fe11b8cb564f95426, including after transfer. All 1,000 IDs are unique bridge items. The 100 pilot, 500 dev and 1,000 test IDs are pairwise disjoint. Test paragraph counts are 998 with ten, one with four, one with two. All test gold supporting-fact indices resolve to original sentences. Matched the dev gate lock SHA-256 ad4a0390042c40d934d445e9127b109e69031c112b1c1ecf08fed265a40a58ed and pinned serving script SHA-256 fc82bca4e12c5e3f067ae50fd1b3433dc6ceb44067dd397e0ddd78f95113af7a. The frozen tokenizer's pre-generation prompt ranges are 205–1,329 for A, 233–2,383 for B, and 288–3,414 for Full-context. Every question fits the 4,096-token limit with 128 tokens reserved for completion.
- Use one shared A/B answer pair per ID from the frozen Qwen checkpoint and vLLM configuration, with k=2, m=1, frozen prompt and rewrite, greedy temperature 0 and completion cap 128. Full-context uses the same answer model and prompt with all original candidate paragraphs in manifest order. Preserve the two-paragraph case, for which no new paragraph is available. Score A/B with the pinned DeBERTa CUDA scorer, batch 4 and maximum 512 tokens. Gate inputs and thresholds are the ones frozen in step 4, including the secondary tie rule. Report the 20% dev target for NLI-only, crisp and Fuzzy and their actual formal trigger rates. Never uses A, Always B, and Oracle chooses B only for strictly positive official answer F1 gain. Main quality metrics are official answer F1, EM and supporting-fact F1 from the HotpotQA scorer at commit fa3a36370899e1d85822de61e58c85ea19993154, script SHA-256 d35fc91a6db21d791dbdda11daf3856e9359f5701d54e3eefba20d88fecc02c0. Also report selected improved/tie/degraded, whole-sample changes versus A, and gate precision/recall/F1 with strictly positive B-minus-A F1 as the positive label. Gold labels are used only for evaluation and the hindsight Oracle.
- Sentence references follow the fixed Qwen post-processing approach. Give the selector the question, fixed generated answer and verbatim, individually numbered sentences from valid cited paragraphs, in citation order. Preserve the original zero-based sentence index and title in the official prediction format. Invalid IDs are dropped, duplicate IDs are deduplicated, malformed selector JSON contributes no references, and no valid paragraph citations gives an empty prediction without a selector call. Count and audit malformed/invalid outputs. For a selector input exceeding 3,968 tokens, halve its ordered candidate list recursively and take the union of returned valid IDs. This preserves candidates and the locked context limit. A selector call can add cost and can miss evidence omitted by the original paragraph citations. Changing the QA prompt to produce sentence IDs directly would invalidate the dev gate lock's matched answer setup. Expanding every cited paragraph to every sentence would predict many sentences the model never identified as support. Use the same selector for A, B and Full-context and include its time, calls and tokens on the live path. Pre-formal dev smoke uses a fixed SHA-256 ordering of 42:_id, the first 24 dev questions' cached A/B answers, plus freshly generated Full-context for the first eight. Pass requires completion, successful parsing and at least one nonempty sentence prediction. This is an operational check.
- Priority ablations use the same formal pairs and Fuzzy rule and boundary. For w/o NLI, replace the per-question NLI risk by the fixed midpoint of the locked low/high anchors, giving neutral high-risk membership 0.5 and a constant risk tie key. For w/o bridge, use the locked missing-bridge fallback and keep NLI risk. The midpoint and control are analyst-chosen before formal generation. A zero/one NLI membership would hard-code a low/high-risk premise. Recalibration would estimate a different policy at the target rate rather than isolate removal from the locked system. Report both realized rates and qualify quality differences in light of them.
- Measure Never, Always, NLI threshold, crisp, Fuzzy and Full-context on the same 32 test IDs, chosen by the same fixed hash order before outcomes. Fixed 32 is an engineering choice providing four nominal eight-request groups per method while limiting extra inference. Use eight dev warmups per method and a work-conserving pool of eight requests. Time from the start of retrieval or context preparation through final sentence selection. Count answer and selector LLM calls, NLI calls, LLM input/output tokens and consumed NLI input tokens separately. Report mean, P50, P90 and P95 latency, hardware and concurrency, and live sample trigger rates separately from 1,000-item replay rates. Gated paths generate A and score live NLI, then if triggered call the frozen retrieval function for B (which rebuilds the first-round ranking) and generate B, before doing one final evidence selection step. Always performs both retrieval rounds and generates B directly because fixed rewriting uses only the question and first retrieved document; Never generates A directly and Full-context uses the complete pool. NLI runs in CUDA when it passes a concurrent Qwen dev preflight. If co-resident CUDA fails, require a passed CPU NLI preflight before the formal job, report the CPU setting for live measurements, and retain CUDA batch 4 for offline quality. Oracle is an offline reference.
- For V2 §10.1 step 6 reporting, preserve the per-question paired scores. Pre-specify the §12 listed answer-F1 contrasts (Fuzzy minus crisp, NLI threshold and Never, Oracle minus Never, and Full-context minus Fuzzy) with 10,000 seed-42 question-level bootstrap replicates and individual 95% percentile intervals, continuing the pilot's interval convention. These are estimation intervals without a familywise significance claim. Step 6 analyses are deferred until completion of the main experiment.
- The seven new synthetic tests passed. The existing eleven bridge and calibration tests also passed. The mock case exercised the Step 3 response fixture via an opt-in in-process transport, with no change to the shared mock. Exact launch/recovery commands are in README_step5_v2.md and checksums in step5_v2/inputs.sha256. No held-out generation or formal scoring had run when writing this entry.

## Running: V2 step 5 remote dev smoke and formal worker

- SSH was restored via a foreground ControlMaster session. Uploaded only the new step 5 scripts, official scorer and input checksums. The GPU verified all seven manifest entries and all seven pinned NLI snapshot files. Existing Qwen vLLM passed the loopback health check.
- Started detached tmux `nlp-v2-test` at [time omitted]. The worker entered dev smoke at [time omitted]. It starts formal generation only after the dev sentence-selection and live-path checks pass. The two formal caches are separate; each completed answer is saved before evidence selection so a failed selector does not require regenerating its answer.

## Executed: dev-only validation passed and held-out generation started

- The fixed dev smoke completed all 56 branches (24 cached A/B pairs and 8 Full-context outputs). All 56 selector responses parsed, with zero invalid IDs and 53 nonempty sentence predictions. Maximum observed selector prompt length was 832. These counts are dev pipeline diagnostics.
- Co-resident CUDA NLI failed with out-of-memory while loading the model on the T4 with the existing Qwen vLLM service. The pre-registered CPU fallback passed all eight live dev paths (Qwen GPU, DeBERTa CPU, four CPU threads). Therefore real experiment latency uses CPU NLI and the official replay uses CUDA NLI. No change to serving or gate settings was made.
- GPU worker entered held-out generation at [time omitted]. At entry, zero of the 3,000 planned A/B/Full-context answer/evidence pairs were complete. No held-out scores were available at this checkpoint.

## Executed: legacy mock regression and first formal cache checkpoint

- At [time omitted] the remote worker had saved 48/3,000 answer/evidence pairs. Status checks used cache row counts only.
- The unchanged legacy Step 5 (23 tests), signal analysis (6), Step 5b (17) and Step 6a (16) suites all passed on the GPU host in a separate mock-only directory. The loopback runs hit local HTTP connection timeouts. The isolated rerun hid optional real torch/transformers imports for the legacy dependency-absence test and never called the live model. The formal worker and model environment were separate from those test processes.

## Running: first 250 formal answer/evidence pairs persisted

- At [time omitted] the watcher verified 250/3,000 held-out answer/evidence pairs. The post-smoke observed throughput was about 22 pairs per minute. Extrapolation implies about two additional hours for this generation stage, subject to prompt and output lengths.
- No official held-out scores, ablation outcomes or live latency results have been read. The worker continues detached in tmux.

## Running: formal generation checkpoint

- At [time omitted] the worker had persisted 505/3,000 answer/evidence pairs. The job remains in generation. No held-out metrics were read.

## Running: one third of the formal branch cache persisted

- The detached worker reached 1,003/3,000 complete answer/evidence records at [time omitted]. Observed generation throughput remains about 22 pairs per minute. Quality replay and timed paths are pending.

## Running: formal branch generation exceeded halfway

- Remote watcher reported 1,506/3,000 complete answer/evidence pairs at [time omitted]. The quality and cost stages had not yet run.

## Running: two thirds of the formal branch cache persisted

- Remote watcher reported 2,004/3,000 complete answer/evidence pairs at [time omitted]. At the observed rate, the remaining generation stage was approximately 45 minutes, followed by NLI and real-path measurement.

## Observed: SSH watcher disconnected during formal generation

- The watcher exited with SSH status 255. The foreground ControlMaster socket was absent and noninteractive authentication failed. The last verified server checkpoint remains 2,004/3,000 complete pairs at [time omitted].
- The formal tmux worker had been detached independently. The disconnect neither confirms failure nor completion of the GPU run. No change or restart was made. Requested reconnection so the final artifacts can be checked and recovered.

## Observed: formal result collection awaiting SSH reconnection

- Rechecked the workspace at [time omitted]. The requested SSH control socket was still absent and no formal outputs had been synchronized. The last verified server checkpoint remains 2,004/3,000 complete answer/evidence pairs at [time omitted].
- The server status, completed-cache counts, official scores and measured costs must be verified after reconnecting. The detached job should be checked before taking any restart action.

## Executed: verify completed V2 generation and repair the launch wrapper

- After SSH reconnection, verified that formal answer/evidence generation had finished at [time omitted], with 3,000 rows in each cache. The worker exited 1 while switching to CUDA NLI, because the exact session selector passed to tmux send-keys was not a pane target. Qwen was still healthy, and no formal NLI, quality scores or cost records existed.
- Captured immutable pre-recovery hashes: answers 33f987a088d01ecafb8c7abe730651ff268ef8af58d12b4a3fc2420112f1b8f4; evidence 17c098a3d60d2823febaf14224753882bf641425d02e630ac7ff12a230e8f733. Resume the original pipeline from these caches. No change to inference or scoring code.
- Resolved the service's single pane ID explicitly before sending the interrupt. The recovery wrapper passed shell syntax checking and has SHA-256 eabb6575f320dfb7710266d7b7d126b10a8eff81be98ec90739ac3eaae0ff814. Updated its input checksum only.

## Running: resume V2 step 5 from the complete generation cache

- The server verified all seven inputs and both original answer/evidence cache hashes. The recovered tmux task started at [time omitted]. Its generation entry point validated 3,000/3,000 completed pairs and finished without any new generation.
- CUDA NLI started at [time omitted]. The first check saw 64/2,000 NLI rows at [time omitted]. The remaining worker stages use the previously recorded configurations.

## Observed: fix conflicting model identities in NLI cache rows

- CUDA completed all 2,000 A/B scores, and Qwen restarted successfully. The replay exited 1 at [time omitted] before official scoring. The scorer result's model field had overwritten the answer-model cache key with the NLI snapshot path.
- Preserve the original NLI file and migrate identity metadata only. Validate all 1,000 IDs and exactly one A and B per ID, the locked NLI snapshot path and CUDA provenance, and the three probability labels. Keep the same question order, logits, probabilities and all other fields. Store the actual NLI model separately from the answer model used as the paired cache key. The new mock writer-to-reader regression and all 18 prior synthetic tests passed.

## Executed: validated cache metadata migration and resumed replay

- The migration validated all 2,000 unique (answer model, question ID, branch) pairs, confirmed HF/CUDA provenance and normalized three-label probabilities, and round-tripped each row to confirm equality to the original after reversing the identity-field change.
- Preserved original CUDA NLI rows as `nli_test_v2.original.jsonl`, SHA-256 272713082ccec54510aa821989a7dd4cbf195d24316d9903c64ea9a164f716cd. The corrected metadata cache SHA-256 is e1917e2a56d49418369029709caf72da86964c5739cfaf81faa205ab4f0d7262. Updated and verified the evaluator checksum. Resumed in the same detached session name at [time omitted] with Qwen already healthy.

## Executed: official quality replay complete, live cost measurement underway

- The corrected evaluator scored all 1,000 questions and emitted the nine official answer/supporting-fact prediction sets (six live strategies, the paired Oracle, two Fuzzy ablations).
- Downloaded the quality summary, per-question table and official predictions to a temporary directory and checked all eleven transfer hashes. Independently recomputed every prediction's F1, EM and Supp-F1 using the pinned official scorer. Verified all test IDs, the locked gate/ablation decisions and the Oracle positive-gain rule. Live metrics remained pending.

## Executed: V2 step 5 formal experiment completed and archived

- The remote worker exited 0 at [time omitted]. Verified the restored Qwen service, all result files against the server hashes, 3,000 answer/selector keys, 2,000 CUDA NLI keys, 1,000 distinct formal questions and nine complete official prediction sets. Recomputed official scores, frozen policy decisions, all latency percentiles and mean call/token counts locally. Confirmed all 2,000 original CUDA results are identical after undoing only the migrated identity fields, and that every supporting fact comes from an originally cited paragraph. No regeneration of the original outputs.
- Held-out quality across 1,000 questions. F1, EM and Supp-F1 below use the official script. The dev target for all three fitted gates is 20%. Oracle chooses strictly better cached B and is bounded to the paired A/B evidence budgets.

| Strategy | Answer F1 | EM | Supp-F1 | Re-retrieval | Selected improved / tie / degraded | Gate P / R / F1 |
|---|---:|---:|---:|---:|---:|---:|
| never | 0.50848218 | 0.401000 | 0.47511219 | 0.000% | 0 / 0 / 0 | — |
| always | 0.57657564 | 0.462000 | 0.52378889 | 100.000% | 123 / 827 / 50 | 0.123000 / 1.000000 / 0.219056 |
| nli_only | 0.53893035 | 0.427000 | 0.50146111 | 21.900% | 49 / 153 / 17 | 0.223744 / 0.398374 / 0.286550 |
| crisp | 0.54360782 | 0.430000 | 0.50215505 | 20.900% | 54 / 141 / 14 | 0.258373 / 0.439024 / 0.325301 |
| fuzzy | 0.54424354 | 0.432000 | 0.50242778 | 23.000% | 56 / 157 / 17 | 0.243478 / 0.455285 / 0.317280 |
| full | 0.64265380 | 0.502000 | 0.54903398 | 0.000% | 0 / 0 / 0 | — |
| oracle | 0.60606539 | 0.492000 | 0.51348362 | 12.300% | 123 / 0 / 0 | 1.000000 / 1.000000 / 1.000000 |
| fuzzy_without_nli | 0.56816135 | 0.452000 | 0.51939949 | 66.000% | 100 / 523 / 37 | 0.151515 / 0.813008 / 0.255428 |
| fuzzy_without_bridge | 0.53793035 | 0.426000 | 0.49979444 | 20.700% | 47 / 145 / 15 | 0.227053 / 0.382114 / 0.284848 |

- Live latency and token measurements below use 32 common held-out IDs per method (192 records), concurrency 8, 8 untimed dev warmups per method, Tesla T4 Qwen and CPU DeBERTa (four threads, serialized inference in the shared scorer). Calls and tokens include the evidence selector. Live trigger rates describe the 32-item run; the quality table uses the 1,000-item cached replay.

| Strategy | Mean s | P50 s | P90 s | P95 s | LLM calls | NLI calls | LLM input/answer+selector tokens | LLM output tokens | NLI tokens | Live rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| never | 19.2633 | 19.2056 | 23.7645 | 24.4067 | 2.00000 | 0.00000 | 697.75000 | 27.28125 | 0.00000 | 0.000% |
| always | 19.1285 | 18.7735 | 22.5594 | 23.5562 | 2.00000 | 0.00000 | 814.65625 | 26.37500 | 0.00000 | 100.000% |
| nli_only | 23.3239 | 22.4733 | 28.8741 | 31.1079 | 2.21875 | 1.00000 | 810.18750 | 30.84375 | 159.28125 | 21.875% |
| crisp | 22.8259 | 21.7110 | 28.6113 | 31.2132 | 2.18750 | 1.00000 | 800.93750 | 30.28125 | 159.28125 | 18.750% |
| fuzzy | 23.3623 | 22.4659 | 28.6471 | 31.2830 | 2.21875 | 1.00000 | 810.18750 | 30.84375 | 159.28125 | 21.875% |
| full | 24.9149 | 24.4573 | 29.6659 | 31.4079 | 2.00000 | 0.00000 | 1916.75000 | 27.78125 | 0.00000 | 0.000% |

- A/B/Full answer parse fallbacks were 0/0/0. Malformed selector calls were 11/10/8; invalid candidate IDs were 0/0/1; empty sentence predictions were 92/58/35. There were no selector split cases. A/B CUDA NLI truncations were 3/3 and premise fallback counts 15/8. One test question had no unused paragraph for B.
- Interpretation is descriptive at this stage. Fuzzy minus crisp answer F1 is +0.000636 with 23.0% versus 20.9% re-retrieval. Always improved 123 cases and degraded 50 versus Never. Full-context achieved higher F1 than any A/B policy or the paired A/B Oracle. The no-NLI ablation's 66.0% rate makes its quality comparison with 23.0% Fuzzy a comparison at different operating points.
- Archived outputs under local `step5_v2/`, including raw generation, selector, original and repaired NLI scores, nine official forecasts, per-question scores, live measurements, logs and checksum manifests. V2 step 6 paired bootstrap, error analysis and report assembly remain separate from this completed run.

## Prepared: V2 step 6 inference, tables and diagnostic sampling

- Use the five formal answer-F1 contrasts, sample unit, replicate count, seed and percentile interval already fixed in the [entry](?plain=1#L490). Reuse the pilot's paired bootstrap function, input in test.json order, with 10,000 resamples of 1,000 questions, seed 42, and linearly interpolated 2.5th and 97.5th percentiles. Report individual 95% intervals in percentage points. Use the original paired differences and keep all gated outcomes and evaluation metrics fixed. The intervals condition on the frozen policies and cached outputs, with no familywise significance claim or equivalence margin.
- For V2 §11.1–§11.5, fill a separate record linked to the template and log, including original pilot readouts and six real policies on three descriptive quality–cost axes (full replay re-retrieval rate, mean end-to-end latency, and mean total LLM tokens). Show the A/B Oracle reference and put paired contrast intervals in their own table. Keep live costs at the measured sample size and state the GPU/CPU configuration. Use original gate decision counts as well as strategy-wide answer changes using all 1,000 questions as the denominator.
- §12.2 diagnostics are exploratory, specified after formal aggregate results were available and before viewing these case narratives. Inspect five Fuzzy-missed improved questions and five Fuzzy-triggered degraded questions. For §3.3, inspect four Branch A cases per structural candidate stratum: valid paragraph citations with exactly one of two gold titles (missing hop), valid citations with no gold title (wrong citation), and exact-match answer with both gold titles cited (two-paragraph support). Title coverage only nominates examples. Read cited premises and both branch outputs where relevant to assess actual evidence. Rank within each stratum by ascending SHA-256 of UTF-8 `42:<_id>`, then ID. Allow overlap and record it. Use these small case-based audits to illustrate failure mechanisms, with no general prevalence claims or independent human-review claim. Also report whole-set gate misses, harmful triggers and gold-title coverage descriptively. Stratifying ensures rare failure modes are inspectable, while hash sampling avoids hand-picking examples within each stratum. Post-hoc case dimensions will not be used to revise thresholds or formal scores.

## Executed: V2 step 6 inference, case review, and paper sections complete

- Verified the step 5 archive again and ran the offline step 6 driver. On the 1,000 ordered paired questions with B=10,000 and seed 42, the five pre-specified answer-F1 estimates and individual 95% intervals (percentage points) were Fuzzy minus Crisp +0.064 [−0.365, +0.517], Fuzzy minus NLI-only +0.531 [+0.155, +0.994], Fuzzy minus Never +3.576 [+2.265, +4.914], A/B Oracle minus Never +9.758 [+8.059, +11.471], and Full-context minus Fuzzy +9.841 [+7.098, +12.614]. The interval for the same-input comparison spans zero, and the two policies used different held-out trigger rates despite a shared dev target. There is no equivalence or familywise claim in the report.
- Exploratory whole-set counts: Fuzzy missed 67 of the 123 improved cases. B added at least one gold title for 53 of the misses and 3 of the 17 harmful Fuzzy triggers. Both gold paragraphs were retrieved for 330 questions by A and 568 by B. The Fuzzy/Crisp trigger intersection was 193, with 37 Fuzzy-only and 16 Crisp-only triggers. Report full-population changes separately from the composition of the triggered subset.
- Retrieved all 22 hash-sampled case records, with no overlap across the five diagnostic strata. Eligible/sampled counts were 67/5 missed improvements, 17/5 triggered degradations, 727/4 missing-hop candidates, 123/4 wrong-citation candidates, and 95/4 joint-support candidates. Assistant case readings are recorded with full IDs and cached evidence, without independent human adjudication on these formal cases. They illustrate entity or role confusion, missing evidence links, sentence-selection omissions, and lexical answer F1 sensitivity. The separately recorded 20-row pilot audit was performed on the pilot audit sample.
- Wrote `step6_v2/Experiment_Report.md` with V2 §11.1–§11.5 and §12 readouts, `Error_Analysis.md` with all 22 review notes, `quality_cost.pdf` with six live strategies and the paired Oracle line, and English Methodology and Implementation and Experimental Results sections as LaTeX and a three-page IEEEtran 1.8b, 10 pt, two-column preview. The plot and estimates are reproducible from `analyze_step6_v2.py`. The Chinese README contains exact local commands.
- One optional draft of the analyzer attempted to reuse the pilot's CSV loader and hit its pilot-specific NLI column check. The final driver reads the formal schema, still using shared numeric conversion and the original paired bootstrap. Two targeted synthetic tests and eight existing tests passed. An independent vectorized bootstrap reproduced all five intervals to 1e-12. A fresh run reproduced the four generated artifacts byte-for-byte. Checked all three PDF pages visually, extraction of key values, figure placement, and local report links. No new model inference or threshold fitting was performed.

## Prepared independent review worksheet

- Prepared a blank reviewer workbook for the three representative V2 error-analysis cases `5aba89365542994dbf019932`, `5ab9547755429970cfb8ea6c`, and `5a7b4073554299042af8f733`. The evidence tab contains 43 source sentences from the retrieved A/B paragraphs. It marks retrieval rank, final sentence selection, and the dataset reference facts. The reviewer tab asks for answer correctness, evidence sufficiency, and passage-level reasoning.
- The workbook excludes the model scores and prior interpretations. Verified the exported question and answer text, source sentences, citation flags, reference facts, empty review cells, and dropdowns. Human review is pending. The workbook is in `outputs/nlp-v2-case-review/V2 代表案例人工复核表.xlsx`.

## Put evidence and review fields on one worksheet

- Revised the reviewer workbook at the same path to place each complete case and its response fields together on one worksheet. Verified all three question and answer blocks, 43 original sentence rows and their retrieval, citation and reference markers against the previous workbook. All 12 dropdown fields and three rationale fields are blank for independent review.

## Added criteria and worked example to reviewer worksheet

- Added instructions for semantic answer correctness, sufficiency of final citations, and locating original evidence. A labeled fictional example illustrates a correct answer with an incomplete cited chain. Verified all previous case content and blank fields in the revised workbook.

## Verified the V2 §10.2 reproducibility checklist

- Filled all seven fields of V2 §10.2 in `step6_v2/Reproducibility_Checklist.md`. Recorded split, hash-order and bootstrap seeds, single-generation caches, historical hardware and software, revision and checksum identities, cache invalidation, and the actual retry and recovery behavior. The formal generation request and serving command did not set an explicit decoding seed. The formal run lacks a corresponding archived Git commit and is identified by source and configuration checksums instead.
- Checked 23 entries in the local provenance manifest, 12 dev archive files and 27 formal archive files. The documented replay commands regenerated the three dev calibration artifacts, nine official test predictions, per-question results and quality summary, and four Step 6 analysis artifacts byte-for-byte. Independently re-aggregated means, timing percentiles, calls and tokens from all 192 saved live records. Verified NLI score equality across the 2,000 original and metadata-repaired records.
- This check used copies of the existing caches for computation. Fresh generation, fresh NLI inference and a new live timing pass were outside the performed validation.

## Executed: V2 §11 results register filled

- Filled V2 §11.1–§11.5 in `step6_v2/Experiment_Protocol_v2_Section11_Filled.docx`. Used the original template to retain its table structure and filed a separate results copy so the protocol source remains intact. Updated the copy's front scope statement and running labels to identify the filled section. All protocol content outside those labels and §11 was preserved.
- Used the 1,000-question formal archive for quality, retrieval rates, policy-wide changes and gate metrics. Used the common 32-question live subset per policy for token and latency, with the measurement configuration stated alongside the table. Oracle uses offline branch selection and has no live cost entry. In §11.4, used retriever coverage of both gold paragraphs as the recorded DeepSeek pilot readout, since the historical pilot file has no sentence-level Supp-F1 values.
- Embedded the archived three-panel quality–cost figure and included the five pre-registered paired F1 differences and individual 95% percentile intervals as Table 11-5, keeping the descriptive figure on its original scale. Verified Word table values against the formal quality and live summaries, the pilot records, the prior log and the archived paired results. Rendered the copy for visual checks of the result pages and confirmed the intended edit scope against the template. No model inference or new statistical analyses were run.

## Prepared: standalone V2 §11 results booklet

- Assemble the filled V2 §11.1–§11.5 into a standalone Chinese booklet for the project group. Preserve the formal and pilot denominators and pre-registered contrasts. Explain the existing results and show simple descriptive differences calculated from the archives, including selected versus whole-sample outcomes, separate cost measures and interpretation of the paired intervals. The additional explanation is prepared after the outcomes were observed. It introduces no new hypothesis test, metric definition, claim of equivalence, threshold or model run.

## Executed: standalone V2 §11 results booklet

- Wrote the eight-page editable Chinese booklet `step6_v2/NLP_V2_Section11_Results_Booklet.docx`. It explains every §11 result table, each of the three cost panels, and each of the five pre-registered paired F1 contrasts. Split the main table into quality/re-retrieval, real-path latency/tokens and call counts because those results use different samples and units. Included the documented live P50/P95, call statistics and NLI token counts from the existing archive.
- Verified corresponding cells against the filled §11 and source archives, checked the five paired estimates against the unrounded CSV and JSON, and checked gate denominators, pilot inputs and archive paths. Used the original archived quality–cost figure. Rendered and inspected all eight pages, including the complete figure, and checked the page guide. Interpretive differences and ratios are derived from the archived run. No new inference, threshold fitting, or statistical testing was performed.

## Received and checked returned V2 case review

- Received `副本V2 代表案例人工复核表.xlsx`. The returned copy includes all 12 decision fields and all three rationale fields. The reviewer-name field is blank. Compared with the blank worksheet. The three question/answer blocks, 43 evidence sentences, retrieval positions, citation flags and reference flags match after ignoring leading whitespace removed from 34 sentence cells.
- Returned answers for the three cases (A/B correct, then A/B evidence sufficient) were respectively no/yes and no/no for `5aba89365542994dbf019932`; yes/yes and no/no for `5ab9547755429970cfb8ea6c`; and yes/yes and no/no for `5a7b4073554299042af8f733`. The cited sentence locations in the rationales are consistent with the worksheet. The third case's official F1 stays 1 versus 2/3, while the returned review accepts both wordings semantically. These are three selected qualitative cases.

## Prepared: V2 experiment conclusions booklet

- Assemble a standalone booklet organized around the V2 research questions. Use archived formal comparisons, live cost measurements, the original pilot and supplemental checks, the returned qualitative review, and the §10.2 reproducibility record. Report only the previously defined formal contrasts, identify descriptive arithmetic, and qualify comparisons made at different realized rates. Use the same project conventions for F1, comparator ordering, and individual paired intervals. Include a concise English Conclusion for manuscript integration.

## Executed: V2 experiment conclusions booklet

- Delivered the six-page editable `step6_v2/NLP_V2_Experiment_Conclusions.docx`. It answers RQ1–RQ3, explains pilot and reproducibility scope, integrates the three returned qualitative reviews, and includes an English Conclusion for the manuscript. This is a synthesis of the archived results. No new statistical test, threshold fitting, model inference or human annotation was performed.
- Checked main and ablation scores, five pre-registered paired intervals, timing inputs and token totals, pilot outcomes, and the review labels against the archives. Verified that Fuzzy and Always have exactly the same mean total LLM token consumption in the 32-question timing sample (841.03125), with NLI use counted separately. Used matched-question numerical results only for the paired contrasts. Verified all six rendered pages and the page guide.

## Prepared: V2 experiment process handbook

- Map the original V2 sections 0–15 and their named subsections to dated decisions, execution notes, archives and readouts. Document the original Step numbering alongside V2 §10.1, use only recorded decision rationale, and mark retrospective explanation or missing confirmations as such. Include an onboarding path from data and model setup through dev calibration, formal replay, cost measurement, post-result analysis and paper handoff. Keep historical outputs and experiment settings intact.

## Executed: V2 experiment process handbook

- Delivered the 24-page editable `step6_v2/NLP_V2_Experiment_Process_Handbook.docx` in the order of the original V2 §0–§15, including its named subsections, C01–C19 and an offline replay appendix. It uses dated choices and available records to reconstruct preparation, alternatives, rationale, pipeline steps, outputs and bounded conclusions. Distinguishes original Step labels from V2 §10.1, the original pre-registered GO from supplemental pilot analysis, and formal paired reporting from exploratory case review.
- Verified the document section map, all formal quality and gate table values, five paired intervals, pilot counts and coverage, chart identity and clickable navigation. Rendered the full handbook and inspected its tables, code blocks, figure, navigation and page boundaries.
- Ran the appendix replay in a fresh temporary directory against archived inputs, with no remote inference. All 18 comparisons were byte-for-byte identical: three dev products, two official result tables, nine predictions, and four analysis artifacts. Rechecked the 23 local, 12 dev and 27 formal manifest entries. No threshold, model output, or scoring method was changed.

## Prepared: complete local V2 materials package

- Assemble one ZIP around the current workspace layout so relative replay paths and historical mock imports still resolve. Bundle the dated authoritative log, protocol, three splits, pilot and dev material, complete formal outputs, source and tests, review and manuscript assets, the three recent booklets, and prior snapshots for provenance. Use the existing share copy of the returned worksheet after verifying identical cell values, merges and validation rules; its editor identity metadata was removed earlier. Catalogue historical files only referenced in the log and keep raw secrets, unrelated workspace metadata and model environments outside the archive.

## Executed: complete local V2 materials package

- Prepared `NLP_Experiment_Materials_V2_Complete_2026-11-16.zip` with the current experiment artifacts, original protocol, dated log, three booklets, both qualitative review forms, paper files, scripts and tests, early materials and three earlier ZIP snapshots. Included README navigation, archival limits, data attribution, and an itemized SHA-256 manifest. The returned worksheet share copy keeps cell values, merges and validations and omits editor identity metadata.
- Verified the extracted layout and hashes for 162 manifested files, plus the manifest itself. Checked reference links, the 1,600 disjoint bridge IDs, the formal raw cache and timing counts, and the three existing manifests (23 local, 12 dev and 27 formal entries). All 21 current synthetic tests passed from the extracted package. The appendix replay reproduced 18 saved calibration, prediction, scoring and analysis artifacts byte for byte. No new model inference or timing was performed.
- Historical artifacts present only outside the local sources are enumerated in `ARCHIVE_SCOPE.md`. Package screening checked conventional credential patterns and nested archives. Synthetic test token strings were confirmed as fixtures.

## Prepared: V2 experiment parameter handbook

- Compile the experiment's scientific and operational settings in Markdown. Record the actual values, when each setting was fixed, its role and rationale, alternatives considered at the time, and retrospective design trade-offs where useful. Keep documented decisions, inherited implementation defaults, engineering settings and observed outputs distinct. Cross-check the final values against the lock file, versioned scripts, summaries and dated entries. No new analysis or threshold change is planned.

## Executed: V2 experiment parameter handbook

- Wrote `step6_v2/NLP_V2_Experiment_Parameters.md` with ten chapters and seventeen tables. Covers sample and retrieval choices, response and NLI settings, original pilot GO and later signal diagnostics, exact formal gate and ablation settings, sentence selection, live cost, bootstrap and case review, and reproducibility controls. Separates the recorded rationale and alternatives from explanations where an exact original rationale was not documented, including implementation defaults and design grid points.
- Validated all 66 internal/source links and Markdown table structure. Cross-checked the documented full-precision primary and secondary boundary values with the gate lock, the three sample splits, original pilot labels, Step 6a thresholds, realized formal rates and ablations, the latency subset, and bootstrap and case-sampling settings. No inference, threshold fitting or new statistical analysis was performed.

## V3 P0: offline audit
- A local `codex/v3-long-context` branch was created from the V2 archive commit `11e6af5f0af455919eec64032e27389aeba47e36`.
- 62 archive hashes were rechecked; the V2 3,000-question retrieval index and the QA prompt token counts match the archive. The formal scoring was replayed against the nine prediction files, the quality summaries and the per-question tables, and is byte-identical.
- Checked the 100 pilot, 500 tune and 1,000 formal questions: 1,600 mutually exclusive historical question ids in total. Outside the current history list there are 4,318 bridge IDs; the new final set is locked only after the team adds historical exposure information. Logged: one upstream supporting-sentence index out of range, and one question in the old Kaggle expanded pool with 6/26/56 paragraphs.
- The original Tencent Cloud instance console was pending reclamation, no local CUDA service was available, and the Kaggle session was not signed in. Only the offline length audit was completed at that point. Evidence: [P0 source map](v3/p0/source_map.md), [data audit](v3/p0/data_audit.md) and [offline lengths](v3/p0/length_audit.csv).

## V3 P1: data construction and length audit
- Used the fixed snapshot `14f0ace3c3fac7bd86149c616b5b05d8282e5c6a` of the public HotpotQA distractor train split. Paragraphs of 4,096 source questions were drawn by hash; after merging there were 38,229 donor paragraphs. 50 historical pilot questions that satisfy the base 10-paragraph and de-duplication constraints were selected, keeping the original paragraphs; each question was built at 10⊂30⊂60, with supplemental paragraphs picked half by BM25 and half at random.
- The first pass found 3 candidate paragraphs that reused a one-sentence ownership statement from the original evidence. Lexical de-duplication over all original sentences of the question was added, and the build was redone with the same corpus, ranking and seed. Across the 2,500 rebuilt injected paragraphs no verbatim copy of a normalised gold supporting sentence appeared. Also logged: 15 paragraphs carrying an answer phrase, 2 potential local hints, and 1 case where the original question's answer does not align with the question intent.
- The 150 online pools and all 123 gold supporting sentences passed the location check. 1,050 full prompts were recomputed with the fixed tokenizer, reserving 128 output tokens per call. Offline, the number of shared questions at 4096, 8192 and 16384 across the 10/30/60 paragraph tiers is 50/15/0, 50/50/9 and 50/50/50 respectively. Rebuilt artifacts are byte-identical.
- 400/100 conditional gating training/validation ids were frozen. The final set was not drawn. P1 produced data and length records only. See [P1 deliverables](v3/p1/README.md) and [shared scope](v3/p1/resource_estimate.md).

## V3 P0: GPU access and deployment
- An existing GPU was provided and SSH authentication was completed. The machine runs Ubuntu 22.04 and Python 3.10.12 with a single Tesla T4 of 15,360 MiB and driver 535.216.01. At access time GPU memory was 2 MiB, the host had about 29 GiB free RAM and 78 GiB free disk, and no existing Qwen/vLLM service was found. P0 runs in a separate remote directory on a loopback port.
- Parallel download of the four original safetensors shards of the fixed Qwen2.5-7B-Instruct revision `a09a35458c702b33eeacc393d103063234e8bc28` was started. Both tokenizer files matched the local P0 hashes.
- A 2 MiB range probe was run against the same vLLM wheel. The public PyPI endpoint received about 1.91 MiB in 16 seconds and then timed out; the Tencent Cloud mirror served the full 2 MiB. The roughly 235 MiB wheel prefix already received was kept, later packages were continued from the same-version mirror and rechecked against the official PyPI hashes. That comparison was a single range probe.
- The software environment was ready; 157 files were checked against the official PyPI SHA-256 list. vLLM 0.8.5, PyTorch 2.6.0+cu124, Transformers 4.51.3, fixed V0/XFormers; the FP16 CUDA attention smoke test passed.
- The second weight shard hit an HTTP/2 download interruption; the resumed shard passed verification. All four shards are ready and rechecked.

## V3 P0: capacity trial start
- The 4096 tier completed its first weight load. The vLLM log reports about 39.71 seconds to load weights and about 10.0152 GiB of model loading, after which service capacity initialisation began.
- Fixed V0, XFormers, FP16, 4 GiB CPU offload, `max-num-seqs=8`, eager. For 4096, 8192 and 16384 the test is one full-length synthetic request plus the longest real QA prompt of the matching 10, 30, 60 paragraph tier, followed by 8 of that tier's longest real prompts submitted simultaneously. Pass/fail is recorded from booked tokens, peak GPU memory and scheduler samples. This entry records the start of the run; per-tier results follow.

## V3 P0: 4096 tier passes
- The service reported a 4096 limit. The longest real prompt in the 10-paragraph tier was 2,488 input tokens, returning 21 output tokens in 10.886 seconds for a single request. The full-length synthetic request used 3,968 + 128 tokens and took 56.543 seconds.
- All eight real requests returned, with input tokens matching P1. Batch wall time was 20.772 seconds; sampling saw 8 requests running at once with a sampled peak of 14,807 MiB. The scheduler queued during first-segment prefill and then reached 8 concurrent requests.
- After all requests finished, the executor terminated its own vLLM. The engine exit log records `MQLLMEngine terminated` and NCCL cleanup warnings; the service then shut down and GPU memory returned to 2 MiB. The 8192 tier started next.

## V3 P0: 8192 tier passes, long prompts queue
- The service reported a 8192 limit. The longest real prompt in the 30-paragraph tier was 5,420 input tokens, returning 21 output tokens in 13.149 seconds. The full-length synthetic request was 8,064 + 128 tokens and took 60.000 seconds.
- All eight real requests returned; batch wall time was 46.054 seconds. Sampling saw at most 5 requests running at once and at most 6 waiting, and the two peaks need not coincide. GPU KV cache sampled peak was 91.59% and peak GPU memory 14,825 MiB. After the service shut down, GPU memory returned to 2 MiB.
- The P1 10 and 30 paragraph tiers, 50 questions each, can form a shared tier at this limit and enter the run per the P1 length report. This capacity trial validated the longest representative input of two tiers; the formal whole-path latency and quality are still measured by P1.5. The 16384 tier started next.

## V3 P0: 16384 tier first start fails
- Under the same 4 GiB CPU offload configuration, vLLM reported only **8,016 tokens** when initialising the KV cache, less than the configured 16,384; the service exited 1 without issuing a generation request. The startup sampled peak was 14,205 MiB, and GPU memory returned to 2 MiB after exit.
- The first-start result was kept, and the next attempt changes only the CPU offload from **4 GiB to 6 GiB** to free memory. Original weights, CUDA path, client concurrency and samples stay the same. If 6 GiB passes it is recorded as a separate long-context service configuration.

## V3 P0: 16384 tier retest started
- The 6 GiB CPU offload retest was launched into a separate output directory, keeping the first-start failure. vLLM finished cache initialisation; the log reports a theoretical KV concurrency of 2.62 when every sequence fills 16,384 tokens. That value is a cache-capacity estimate; the real concurrent count is sampled from the requests that follow.
- A long-context single request was already observed generating. Still to collect: the real prompt, the full-length synthetic request, the complete eight-request batch responses and peaks.

## V3 P0: 16384 retest passes, P0 GPU acceptance done
- With the 6 GiB offload, vLLM reserved 2,684 GPU KV blocks, the service reported 16384 and startup took 51.075 seconds. The longest real prompt in the 60-paragraph tier measured 10,828 input and 18 output tokens in 19.477 seconds. The full-length synthetic request was 16,256 + 128 tokens and took 89.262 seconds, with a sampled peak of 14,919 MiB.
- All eight real requests submitted together returned; batch wall time was 86.187 seconds. Sampling saw at most 4 requests running at once, batch peak 14,395 MiB and GPU KV cache peak 93.59%. The 6 GiB configuration is used only for the long-context retest; the results of the 4 GiB environment are kept separately.
- After every test service of this round ended, GPU memory returned to 2 MiB. The 37 raw files of the first start and the retest have identical transfer SHA-256 values; each stage's telemetry peaks were recomputed and the question ids, prompt hashes and API counts of the real inputs were checked item by item against the P1 records. See [P0 GPU acceptance](v3/p0/gpu_runtime.md), [first-start evidence](v3/p0/live-2026-11-16/primary-evidence.sha256) and [retest evidence](v3/p0/live-2026-11-16/offload6-evidence.sha256).
- P1.5 can run the 50-question comparison for the 10 and 30 paragraph tiers in the uniform 8192/4 GiB environment. The full 60-paragraph comparison uses the accepted 16384/6 GiB configuration, whose policy cost must be measured separately. The P0 capacity trial read no gold and computed no answer quality.

## V3 P1.5: execution registration
- The authorised T4 was reused; GPU memory was 2 MiB before start, and the fixed P0 weights and dependencies were still available. First the full 50 questions were run at 8192/4 GiB for the 10 and 30 paragraph tiers, and the 60-paragraph tier was run separately at 16384/6 GiB on the same question batch. The latter deployment differs, so costs are compared within a tier.
- **The retrieval-evidence audit was completed before the policy was locked.** On the 10/30/60 paragraph pools, V2 `2+1` hits both gold evidence paragraphs on 31/21/22 questions. One supplemental retrieval plus two paragraphs gives 37/25/29, and plus four paragraphs gives 43/34/32, so `2+2` and `2+4` were registered as extension branches. These are offline retrieval recalls against the paired gold.
- Locked: fixed BM25 top-2/4/6, Full, the V2 original rule reading the three merged paragraphs directly, and `2+1/2/4` which executes a first answer and then re-retrieves once. Same Qwen, prompts, temperature 0, 128 output tokens. Each chained supplemental-retrieval path counts as two answer requests; scheduling rotates path order across same-question blocks, at most 8 per batch. Warm-up is registered separately.
- Quality uses the fixed official answer EM/F1, while retrieval and citation gold-title recall are registered separately. Scheduling, cache and request files contain no gold. The known answer anomaly of the original development question `5ae610e55542995703ce8ae1` serves as the pre-registered sensitivity analysis; the main results still use all 50 questions. Failures, retries, cumulative actual tokens, wall time and the A/B post-hoc selection upper bound are recorded; no gating or sentence-level verification is implemented at this stage. See the [run protocol](v3/p1_5/protocol.json).

## V3 P1.5: main trial start and first batch checks
- The remote host confirmed 6 SHA-256 values covering the online inputs, the P1 length audit, the run protocol and the reused V2 code. The service reports the same Qwen and 8192 tokens. The top-2 and Full warm-ups ran separately on two questions each for the 10 and 30 paragraph tiers. The complete target for the 8192 main trial is **800 paths**, including the first-round and last-round calls that each supplemental-retrieval path executes separately.
- The first batch produced **56/800** successful paths. It covers the completed batches of fixed retrieval, Full, the single V2 answer and two-stage supplemental retrieval. Prompt tokens returned by the service match the P1 locked audit. Same-question comparison results continue to accumulate.
- **P1.5 8192 checkpoint.** The remote host had confirmed 208/800 successful paths. The latest batch was 30 paragraphs, `top6`: 8 submitted, 0 failed, batch wall time 13.67 seconds. Live logs are saved by block; quality is scored offline after collection is complete.

## V3 P1.5: service switch command review
- A temporary tmux session reproduced that an exact session name cannot be a `send-keys` pane target. The actual 8192 answering run kept running. A handoff script with checkable preconditions was added: only once 800 entries are complete and this switch error is detected does it stop 8192 by the actual pane ID and start the planned 16384/6 GiB. The initial driver and state are kept; no prompt, path or timing of already-completed results is changed.
- **P1.5 8192 checkpoint.** 408/800 successful paths confirmed. The latest batch was 10 paragraphs, `2plus1`: 8 submitted, 0 failed, batch wall time 26.78 seconds.
- **P1.5 8192 checkpoint.** 600/800 successful paths confirmed. The latest batch was 30 paragraphs, `2plus2`: 8 submitted, 0 failed, batch wall time 28.71 seconds.
- **P1.5 8192 checkpoint.** 800/800 successful paths confirmed. The latest batch was 10 paragraphs, `2plus1`: 2 submitted, 0 failed, batch wall time 19.41 seconds.
- **8192 to 16384 service handoff.** The 800 paths of the 8192 run were confirmed fully written to disk. The original driver hit the already-reproduced tmux pane-targeting error when stopping the service; the separate handoff script kept the error state, stopped the service by pane ID and continued the 60-paragraph run.
- **P1.5 16384 checkpoint.** 104/400 successful paths confirmed. The latest batch was 60 paragraphs, `2plus1`: 8 submitted, 0 failed, batch wall time 29.89 seconds.

## V3 P1.5: recovery connection lost
- At recheck the server's SSH port 22 was still reachable; the previously authenticated ControlMaster channel had dropped and a newly opened channel reported broken pipe. A single read-only reconnect with the existing local public key failed authentication.
- The 10/30 paragraph tiers already have 800 remote completion records. The 60-paragraph tier was last confirmed at 104/400; the run is managed by a separate tmux process and its final state after the disconnect is still to be collected. The recovery archive is still zero bytes locally; no actual answer quality or complete cost results exist yet.
- Rebuilding the authentication channel was requested. After recovery the first step is to check the existing remote completion markers and success records, fill in only the remaining paths, and keep the original batch timing and handoff evidence.

## V3 P1.5: remote runs confirmed finished after reconnect
- The 8192 run had finished 800 entries and the 16384 run 400 entries, both with final process status 0. The non-zero state before the handoff, the actual pane-ID recovery log and the raw batches of every tier are all kept. The original runs were complete and no rerun was needed.
- Both experimental services had ended; Tesla T4 memory returned to 2 MiB and utilisation was 0%. Collection of the SHA-256-tagged results, evidence and scripts began, and offline scoring is still pending.

## V3 P1.5: quality and cost acceptance complete
- 25 recovered files passed SHA-256. Question ids, sizes, pool and prompt hashes, context order, token usage and the pre-registered method coverage all re-verify consistently. The formal pre-check covers 1,200 paths and 1,650 Qwen calls, plus 12 warm-up calls. Cumulative usage is 1,590,626 input/29,102 output tokens (warm-ups listed separately). The 168 measured batches total 62 minutes 11 seconds of wall time. No HTTP, prompt-validation or answer-parsing failure occurred.
- **30-paragraph main results.** Full F1 56.73%, 4,341 input tokens, 32.47 seconds. Two-stage 2+4 F1 59.92%, 1,316 input tokens, 23.59 seconds. Paired F1 difference +3.19 percentage points, exploratory 95% interval [−11.27, +17.77]. 2+4 improves 13 questions, ties 35 and degrades 2. Its Oracle is 62.13%; the original 2+1 Oracle is 49.59%.
- **The other two tiers.** At 10 paragraphs, 2+4 gives the tier's highest F1 70.68%; V2 direct reading of 2+1 gives 63.18% and 10.49 seconds. In the separate 60-paragraph diagnostic, 2+2 gives F1 58.65%, about 1,034 input tokens and 28.55 seconds, with Oracle 62.86%.
- Verdict: conditional admission to P2 for verification diagnostics. At 30 paragraphs, first check whether the expanded supplemental-retrieval branches match the observable evidence gap, and add direct answering, small budgets and simple self-check to the later controls. No gating training results or sealed-set conclusion exist yet. Full quality, cumulative tokens, latency and paired intervals are in the [P1.5 report](v3/p1_5/REPORT.md).
- Offline scoring was repeated on the same recovered raw files; the 5 scoring artifacts are byte-identical. The [SHA-256 list](v3/p1_5/analysis/outputs.sha256) of the scoring artifacts and the quality–cost figure has been verified.

## V3 P2: relation and evidence verification
- The 8192/4 GiB Qwen service started in a separate directory on the same T4. The DeBERTa original weights specified by the plan completed SHA-256 verification. Local NLI runs on 4 CPU threads, at most 4 times per question, with each premise+hypothesis at most 512 tokens in total.
- Locked: the 50 P1.5 development questions at 30 paragraphs and the original first answer A. The main diagnostic target is the same-question F1 gain of the original two-stage 2+4; 2+2 is a sensitivity. 30 questions were drawn by fixed hash for manual spot-checking, and three items were registered: the same-budget 10/50 feature comparison, the diagnostic threshold E≥0.5, and the fallback to V2 whole-question NLI plus bridge signal. No sealed question was read and no threshold tuning was performed. See the [P2 protocol](v3/p2/protocol.json).
- Online inputs keep only the first-round question stem, source text, draft and citations; the separate direct-reading control reads the same P1 candidate pools. 15 uploaded files passed hash verification. 50 runs each of relation extraction, Qwen self-check, and original-rule direct reading of 2+2 and 2+4 started. Each relation output budget is 512 tokens. Same-name and coreference markers, source-ID whitelists, and explicit missing/fallback flags when evidence is incomplete are all saved.

## V3 P2: structural interface deviation and fix
- All of the first 32 returned records failed strict validation: 18 have wrong root fields and 14 are invalid JSON. The original examples show a missing bridge-entity field, explanatory text after the JSON, and an illegal citation-value form. All first-round records and costs are kept.
- Before any P2 gain diagnostic was read, an XGrammar-constrained JSON retest was registered. It constrains the bridge field, 1–4 relations, the candidate/unresolved fields and the allowed source ids per question. Relation ids are generated from list order, and duplicate ids can be de-duplicated mechanically; the claim, entity and evidence content is determined by the original response and the raw output is kept. Both schemas compile successfully with the fixed XGrammar on the remote host. The same 50 questions are retested for relations and self-check; the direct-generation controls reuse the first-round same-hash records.
- A separate in-flight queue was submitted and waits for the first-round inference and the CPU NLI to finish before using the same T4, keeping logs and outputs separately. The first-round Qwen finished; all four task types returned 50 successful calls each, with HTTP success and structural pass rate accounted separately.
- Offline, the locked V2 single-NLI threshold and its actual trigger count were recomputed. Same-budget comparisons still select 10 questions by a score cut-off, with ties decided by the pre-fixed question-id hash.

## V3 P2: first-round recovery and baseline controls
- The original CPU verification finished: the three NLI smoke cases were labelled E, C and N in order. All 22 files recovered from the first round passed SHA-256. Relation strict validation passed 1/50; 27 questions have root-structure errors, 22 invalid JSON, and 49 take the fallback of original whole-question NLI plus bridge proxy. Whole-question NLI was truncated 0/50. Free-generation self-check passed 50/50, but its risk score has only one value.
- The XGrammar retest took over right after: same 50 questions, same first answer, same inference settings, rerunning only relations and self-check.
- The two direct-reading controls use the same final prompts, input tokens and evidence order as their paired P1.5 B runs. Direct reading 2+2 gives F1 55.52%, 661.26 input tokens and 10.99 seconds; direct reading 2+4 gives F1 59.92%, 948.92 input tokens and 13.04 seconds. The 50 answer texts of 2+4 are exactly identical to the two-stage version. Each direct-reading F1 equals its cached two-stage counterpart.
- The local summary script carried an old variable left over when the shared scoring function was extracted, so the first offline summary raised `NameError`. Replaying with the fixed A sample count as the denominator for all F1 succeeded; no extra inference was needed and the remote results and the branches used are unchanged.

## V3 P2: self-check prompt fix and constrained backend check
- All 50 free-generation self-checks returned the prompt's `risk=2` and the same reason sentence verbatim. Their AUROC is 0.5, and questions were selected by the tie rule. The original control is kept. A second independent prompt was registered that drops this example and requires the reason to point at the current question, with scoring definition, inputs, budget and model fixed, marked as a development-period interface fix.
- The 50 example-free self-checks entered a separate queue and wait for the relation experiment to stop the service. They are archived separately; the self-check inside the existing relation retest keeps executing as registered.
- The vLLM service log shows that although the API requests XGrammar, the compatibility check switched to Outlines because of the schema length and list bounds. An offline CPU compile passing does not determine the API's actual backend. The real service log is kept; request configuration and runtime backend are recorded separately from now on, together with the actual time needed to build each question's constraint.
- The first constrained batch passed structural validation 8/8. A quick semantic check found at least one question that writes all 4 `claim` entries as the string `true`. Another question outputs the author and the work's date but misses the nickname identity relation in the question stem. Both problems stay in the original records and diagnostics; structural success and semantic quality checks are recorded separately.
- Frozen inputs were rebuilt from the original recovered files and all three hashes matched. The three first-round offline summary artifacts and the spot-check material were generated twice and are byte-identical. Synthetic boundary checks cover illegal sentence ids, unparseable coreference, complete joint evidence, over-long splits and self-check score types.
- The constrained relation retest had returned 40/50, with 39 passing strict validation. 1 was rejected because a candidate field is an unknown placeholder. Client request time includes vLLM's per-question constraint generation and queueing; a batch currently runs at most 8 concurrent requests.
- All 50 constrained relation records returned; 48 pass strict validation, a structural pass rate of 96%. The other two keep their failure reasons and enter the old-signal fallback. CPU verification continues after the constrained self-check with the same prompt ends.

## V3 P2: relation retest results and manual package
- The constrained retest ended with status 0, and all 14 archive files passed SHA-256. T4 sampling showed 2 MiB and 0% utilisation; the example-free self-check then started its own service.
- The 48 valid records contain 144 relations and 121 locatable citations. 2 questions were structurally rejected and 3 have no complete verifiable relation, so 5 questions fall back. Local CPU NLI ran 116 times, at most 4 per question, longest actual input 217 tokens, no truncation. The 50 V2 E/N/C groups agree value by value across the two batches.
- On the main control (supplemental 2+4, same budget 10/50): whole-question risk AUROC 0.823, whole-question plus bridge 0.780, local risk 0.655, gap 0.739, equal-weight composite 0.717. Whole-question plus bridge selects 7 improved questions with group F1 52.48%; local risk selects 5 improved questions with group F1 51.81%, no degraded question. The constrained self-check that keeps the example also copies the example verbatim; the failure evidence is kept.
- 30 fixed blind-review questions and 151 blank review rows are available. Recomputing the blank sheet confirms 0 manual questions completed; status is pending acceptance.
- The example-free self-check recovery connection exited with 255 and the local control socket disappeared. Retested against the fixed server fingerprint, the host is reachable but the local public key failed authentication. Restoring the shared SSH channel was requested; queue start and final state await confirmation from the remote records, and no GPU job needs to be re-issued.
- The 36 recovered artifacts from the first round and the relation retest passed SHA-256 again. The constrained-version offline results and blind-review material were regenerated and are byte-identical. The manual sheet is confirmed unfilled; per the plan the fallback of original whole-question NLI plus bridge stays, and P3 and training are not started. Current evidence: [P2 report](v3/p2/REPORT.md).

## V3 P2: example-free self-check recovery and compute wrap-up
- After the shared SSH connection was restored, the self-check was confirmed to have started, returned its 50th entry and ended with status 0. After shutdown the T4 was at 2 MiB with 0% utilisation, unchanged on recheck. This round did recovery and recomputation only, with no extra inference. The 3 remote run source files matched their original SHA-256, and the 8 recovered files passed local recheck.
- All 50 example-free self-checks pass format and frozen-input verification, over 50 HTTP calls. Scores 0/1/2/3 cover **13/8/29/0** questions. Cumulative 24,521 input and 1,303 output tokens; mean request 19.92 seconds, P95 30.25 seconds. The AUROC of the main 2+4 branch is **0.625**; selecting 10 questions gives 4 improved and 6 ties, group F1 **48.35%**. 2+2 has AUROC 0.591 and group F1 45.15%.
- With this control added there are 14 same-budget evaluations, and two local recomputations are byte-identical. All P2 machine runs are wrapped up; the remaining phase acceptance item is the manual relation faithfulness and consistency check. Details: [updated report](v3/p2/REPORT.md) and [machine summary](v3/p2/analysis-guided/summary.json).

## V3 P2: annotation sheet recompute and P2 acceptance
- `human_ratings_AI_assisted.tsv` was received and read from a workspace copy, SHA-256 `94b405d5105c9d1690fcd8381d13124cdf4ef3fd7a2a1a44f2343e1aa83c6f6a`. Its 151 row identifiers match the fixed 30-question template; 20 questions have 99 rows fully annotated. The reviewer field is `AI-assisted (Codex)`; team members were confirmed to have rechecked each question and the submitted label is final.
- The established script recomputed the sheet twice with identical output. Of 59 relations, 26 are faithful, 30 unfaithful and 3 unknown, a deterministic faithfulness rate of **46.43% (26/56)**, below the plan's **90%**. Of the 20 reviewed questions, 3 have complete relation coverage and 17 incomplete.
- V2 whole-question NLI agrees with the manual support label 1/20; local NLI agrees 39/42. Counted by the question-level statements and relation-level evidence bundles that each can score, the detailed E/N/C comparison is saved with the [recompute results](v3/p2/review-guided/assessment.json).
- P2 manual acceptance is complete; the current relation-extraction module does not clear the faithfulness threshold. The fallback of V2 whole-question NLI plus bridge proxy stays, and P3 and gating training are not started. [P2 report](v3/p2/REPORT.md)

## V3 P3: original-query fallback route
- P3 was started on request. Fixed 30-paragraph pools; A is BM25 top-2, and B re-answers after taking 4 more paragraphs with the V2 original query. The old whole-question NLI risk and the title-bridge proxy keep the P2 definitions. Local relations, gap queries, P4 training and the final set are not part of this round.
- 15 of the 100/50 pre-selected questions triggered P1's original-paragraph near-duplicate rule. Selection moved down the fixed hash order of each original split, filtering only by question type and paragraph count. Training gained 12 and validation 3, with 1 further near-duplicate skipped during replacement. The final 100/50 questions have an empty qid intersection with the 50 development questions. The identical P1 donor index is reused, with 10 original, 10 BM25 and 10 random paragraphs per pool. The pre-fixed 300 prompts contain 197,460 input tokens; the longest A/B prompts including the output reserve are 921/1,681 tokens. Question ids and source-file hashes: [P3 data manifest](v3/p3/input/manifest.json) and [cohort list](v3/p3/input/cohorts.json).
- All 50 development-question A/B results recompute identically with the official HotpotQA scorer. A/B F1 is 42.81%/59.92%; after supplemental retrieval 13 questions improve, 35 tie and 2 degrade. Every A projection matches the P2 first-round information and original signals exactly. The cache-reusing development recompute adds no new inference timing. [Development recompute](v3/p3/development/summary.json)
- The fixed 8192/4 GiB service started on the same T4. All 18 online files passed SHA-256; the transferred content is only whitelisted candidate pools, question ids, lengths and code configuration, while official scoring material stays local. The outer submission command's port pre-check had a quoting error; the actual remote driver independently ran the correct port check and started the service. The 150-pair A/B online run started, followed by a CPU process that receives only A projections and computes the old NLI features.
- Rebuilt candidate pools, cohorts, prompt lengths and offline gold are byte-identical. The A-only input test rejects B answers, gold, labels, supporting sentences and third-paragraph source text. The offline audit of supplemental paragraphs records 11 questions and 21 literal answer hit paragraphs, with no copied normalised gold supporting sentence. 40 pairs were done across 5 batches with no failure.
- 96/150 pairs were done with no failure. The 12 measured batches hold 8 questions each; batch wall time is about 24–30 seconds, with warm-ups stored separately.
- The 150th answer pair and all 150 first-round NLI features finished with status 0. After the GPU service stopped, memory was 2 MiB and utilisation 0%. All 300 measured requests returned HTTP 200, plus 2 warm-up calls. Measurement used 197,460 input and 5,269 output tokens; the 19 batches total 519.18 seconds of wall time. Per-question A+B mean is 23.94 seconds, P95 28.44 seconds. CPU NLI mean is 0.51 seconds, longest input 474 tokens, 0 truncations, and 7 questions fall back to building the premise from the first-round retrieved paragraphs.
- 15 files were collected and all passed SHA-256. The 150 first-round projections match the prompts and source-text hashes of the upstream A exactly, and the offline labels can be recomputed per question from the raw A/B outputs and the local gold. Both offline summary directories reproduce byte-identically.
- The 100 training questions have A/B F1 **40.56%/50.38%**, with 22/72/6 improved/tie/degraded. The 50 validation questions have A/B F1 **44.07%/60.47%**, with 13/34/3 improved/tie/degraded. All 150 positive, zero and negative labels are saved. The small-scale P3 original-query fallback acceptance passes; it was not expanded to 400/100 and P4 was not started. [P3 report](v3/p3/REPORT.md) · [offline labels](v3/p3/analysis/offline_labels.jsonl) · [machine summary](v3/p3/analysis/summary.json)

## V3 P4: original-query fallback small-scale training trial
- P3's per-question results were recomputed, verifying the first-round prompts and pool hashes of the 100/50 questions, A/B ΔF1, costs and the fixed split. P4 uses only the whole-question NLI risk and the bridge-missing flag, with features, scoring targets and costs stored separately. 120 questions have a missing bridge and 30 a visible bridge; first-round signals are complete. The rebuilt frozen package is byte-identical. [Protocol](v3/p4/protocol.json) · [input manifest](v3/p4/input/manifest.json)
- On the existing server, 18 configurations plus an independent rerun were completed on CPU with a single thread, float32 and PyTorch 2.6.0+cu124. CUDA was disabled; the T4 stayed at 2 MiB and 0% before and after, and no new QA or NLI inference ran. The 18 fits total about 5.44 seconds. 67 recovered files passed SHA-256; the two rounds are byte-identical apart from timing, the predictions after loading the 18 weight sets agree value by value, gradients are finite and the rule-weight sums check out. [Raw archive](v3/p4/remote-evidence/evidence.sha256)
- The full form and the four-consequent-only form both select α=0. The full model with the pre-set primary seed 42 is best at round 20 and early-stops at round 50, with all 8 parameters updated. That model has validation MSE 0.15454, linear regression 0.15887 and constant 0.18104. The 46 validation-budget replays and 8 paired-interval recomputations agree. At the 10%/20%/30%/50% validation budget tiers, the three full-model seeds and linear regression select identical questions tier by tier, with F1 48.33%/54.33%/54.00%/60.27%.
- P4 trial-training engineering acceptance is complete. At the 20% budget, the fixed Fuzzy recalibrated on the training set gives 51.00% F1; the full Sugeno is 3.33 percentage points higher, exploratory paired 95% interval [−1.33, +10.00]. The main model and linear regression show no actual selection or cost difference on this validation set. The research scope ends at this small-scale trial; 400/100 and P5 are not started. [Validation report](v3/p4/validation_report.md) · [quality–cost replay](v3/p4/analysis/validation_cost_curve.csv)

## V3 P5: formal sealing and runs
- Strict V3.1 execution was requested, and the team confirmed there are no additional HotpotQA questions from unarchived experiments or manual diagnostics. The protocol now records the P4 fallback route, the 100/50 question checkpoint, the 30-paragraph main tier, the 20% main action boundary and the two primary comparisons. Bridge candidates outside the audited history were sampled by fixed hash, pre-setting 300 main samples, 60 same-question cross-tier samples, 60 blind-review samples (20 double-scored) and 50 main-tier end-to-end timing samples. The 300-question size references the development paired variance and the existing T4 path cost. No non-inferiority tolerance bound was pre-set.
- The sealed files were written; 23 original-paragraph near-duplicates and 1 paragraph-count anomaly were excluded before sampling and replaced by moving down the order. The longest complete-answer prompts including the output reserve are 2,985/6,042/10,960 tokens for the 10/30/60 tiers. 420 qid/tier combinations are fixed, and the 2,940 base answer requests pre-audit 3,332,722 input tokens, with citations, self-check and actual-path timing counted separately. The original 50 P3 validation questions were reused for the Qwen self-check, and 48 action boundaries and the V2 original threshold were frozen by the pre-set hash decisions. The portable formula aligns with the archived P4 scores and validation selections. [Data manifest](v3/p5/input/manifest.json) · [weights and thresholds](v3/p5/policy_lock.json)
- The final online package was uploaded and passed SHA-256 item by item. The first start missed `calibrate_gates_v2.py` while importing the V2 sentence-level selector, exited with status 1 and produced no final prediction. The original V2 module was restored and the import verified; the separate remote queue resumed with the same locked inputs and run script, and the first exit status is kept.
- A recheck found the shared SSH channel disconnected, so no new remote state was visible. Restoring the previously authorised connection was requested. The next step is to check the separate queue and saved records first, keeping the existing predictions. No formal scoring yet. [P5 report and progress](v3/p5/REPORT.md)
- SSH access was restored. The separate remote queue had kept running since it started, and the 30-paragraph main tier had **1,256/2,100** answer-and-citation paths on disk while the GPU was still busy. Read-only monitoring and automatic collection after completion were restarted, with no inference re-submitted. The scorer and blind-review generator were validated against synthetic fixtures that contain no final questions.
- The sealed directory was rebuilt from the fixed data and the development-calibration self-check; question ids, source text, prompt hashes, local gold package and thresholds are all byte-identical. End-to-end measured quality scores the raw answers and citations from the same run, while main-tier quality analysis still uses the locked decisions of the shared branches.
- The last visible record was **1,515/2,100**. The shared SSH connection dropped again and the monitoring and collection clients exited with 255. The job is still managed by the separate remote queue; restoring monitoring over a background SSH control connection was requested. No formal scoring yet.
- After reconnection the remote raw timings were rechecked. The 30-paragraph main tier and its self-check finished; the 10-paragraph diagnostic and its self-check finished; and the five end-to-end paths on the 50 questions finished. When switching to the 60-paragraph service, the port and GPU had already been released but the old service tmux session was still exiting, so creating a session with the same name failed with status 1.
- The reconnected check verified 2,520 answer-and-citation paths, 360 Qwen self-checks, 250 end-to-end records and the main-tier completion marker; the T4 was at 2 MiB and 0%. The old driver and manifest, the original state and the SHA-256 values of the first three raw files were saved separately. The launcher gained a condition that waits for the old tmux session to exit. SHA-256 comparison confirms the only change in the online manifest is the launcher; samples, thresholds, inference and scoring configuration all follow the sealed version. The 60-paragraph run then resumed, with automatic collection once it completes.
- The 60-paragraph service completed 4 warm-up paths and formal output kept growing. Checking the first 2,520 shared paths, 360 self-checks and 250 end-to-end timings against the digest left before the resume, the file prefixes are byte-identical. HTTP calls in the completed part had no failures; 7 shared paths returned no usable answer and 2 could not obtain a self-check score. Their original records and pre-set fallbacks stay, and these questions are not removed.
- The last visible state of the 60-paragraph job was **80/420** answer-and-citation paths, running. The shared SSH control socket disappeared again and both local clients exited with 255. Restoring the connection was requested. Remote inference continues in the separate tmux queue and no rerun was started. Formal aggregation awaits collection of the raw records.
- The shared connection was restored. The remote job had kept running through the disconnect, and 60-paragraph answer-and-citation paths reached **176/420**, with T4 utilisation sampled at **100%**. Read-only monitoring resumed with the same collection procedure that waits for the final exit state.
- The 60-paragraph answer-and-citation paths finished, and the self-check finished after them. After the Qwen service stopped, the T4 was at 2 MiB and 0%. The full-tier CPU features and policy decisions were written to disk, and the remote exited normally with status 0. The **26 files** in the collection manifest passed SHA-256, and the final online manifest is byte-identical to the local version.
- Verified: 2,940 answer-and-citation paths, 420 self-checks, 420 CPU feature rows, 250 real online timings and 20,580 locked policy decisions. The prefixes of the three raw files from before the resume passed verification again. Billing records total 6,440 Qwen HTTP requests, 4,511,421 input and 91,426 output tokens, plus 14 warm-up calls. Kept: 10 paths with no usable answer, 3 records with no first answer that could not be self-checked, and 62 sentence-level selector format parse failures; HTTP requests had no failure or retry.
- **Formal machine test.** On the 300-question 30-paragraph main evaluation set at the validation-target 20% budget: Sugeno F1 **44.64%**, fixed Fuzzy **43.64%**, linear regression **44.64%**. Sugeno's difference from fixed Fuzzy is **+1.00** percentage point, paired 95% interval **[−1.33, +3.33]**, corrected 97.5% interval **[−1.65, +3.61]**. Sugeno and linear regression end with exactly the same per-question actions. The main tier's actual supplemental-retrieval rates are 16.33%, 15.67% and 16.33%. On the 50 same questions, Sugeno averages 20.60 seconds online, P95 28.44 seconds. [Full P5 report](v3/p5/REPORT.md) · [paired intervals](v3/p5/analysis/paired_intervals.csv)
- **Manual acceptance pending collection.** Official scores, paired intervals and blind-review artifacts were generated again and all checked byte-identical. The first reviewer's material holds 60 questions and 300 responses; the second holds 20 of those questions and 100 responses. Recomputing the blank sheets gives **0/60 completed and 0/20 double-scored**. [Artifact list](v3/p5/analysis/outputs.sha256)

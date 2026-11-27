"use strict";

const get = id => document.getElementById(id);
const state = { catalog: null, input: "sample", running: false };

function element(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "请求未能完成。");
  return data;
}

function updateInput() {
  const useSamples = state.input === "sample";
  get("sample").hidden = !useSamples;
  get("custom").hidden = useSamples;
  get("qid").required = useSamples;
  get("question").required = !useSamples;
  get("passages").required = !useSamples;
  get("sample-tab").setAttribute("aria-pressed", useSamples);
  get("custom-tab").setAttribute("aria-pressed", !useSamples);
}

function showSelectedQuestion() {
  const question = state.catalog.questions.find(item => item.qid === get("qid").value);
  get("example-question").textContent = question?.question || "";
}

async function initialize() {
  try {
    state.catalog = await fetchJson("/api/questions");
    const live = state.catalog.mode === "live";
    get("mode").textContent = live ? "实时模型" : "P5 归档回放";
    get("mode").classList.add(live ? "live" : "replay");
    get("mode-note").textContent = live
      ? "实时调用 Qwen 和 DeBERTa。每次在该题的候选资料内检索。"
      : "使用 P5 归档中的模型输出。每道实验题有 30 段候选资料。";
    get("custom-tab").hidden = !live;

    const demos = element("optgroup");
    demos.label = "答辩示例";
    const others = element("optgroup");
    others.label = "其他 P5 实验题";
    state.catalog.questions.forEach(({ qid, question }, index) => {
      const featureIndex = state.catalog.featured.indexOf(qid);
      const prefix = featureIndex >= 0 ? ["归档触发补查 · ", "归档直接结束 · "][featureIndex] : `${index + 1}. `;
      const option = element("option", prefix + question);
      option.value = qid;
      (featureIndex >= 0 ? demos : others).append(option);
    });
    get("qid").append(demos, others);
    showSelectedQuestion();
    get("submit").disabled = false;
  } catch (error) {
    setStatus("未能读取题目，请刷新重试。", true);
  }
}

function setStatus(message, error = false) {
  const status = get("status");
  status.textContent = message;
  status.classList.toggle("error", error);
}

function details(title, ...content) {
  const box = element("details");
  box.append(element("summary", title), ...content);
  return box;
}

function passages(items) {
  const container = element("div", undefined, "passages");
  if (!items.length) container.append(element("p", "本轮没有新增候选段落。", "hint"));
  for (const item of items) {
    const block = element("div", undefined, "passage");
    block.append(element("b", item.title), element("p", item.text));
    container.append(block);
  }
  return container;
}

function verification(trace) {
  const info = element("div", undefined, "verification");
  const metrics = element("dl", undefined, "metrics");
  for (const [label, key] of [["支持", "entailment"], ["信息不足", "neutral"], ["矛盾", "contradiction"]]) {
    const value = trace.probabilities?.[key];
    const group = element("div");
    group.append(element("dt", label), element("dd", value == null ? "—" : `${(value * 100).toFixed(1)}%`));
    metrics.append(group);
  }
  info.append(metrics, element("p", trace.nli_fallback
    ? "首答未给出可用段落引用，NLI 使用首轮检索段落核验。"
    : trace.draft_cited.length ? "核验基于首答引用的段落。" : "无可用的首答核验记录。", "hint"));
  if (trace.nli_truncated) info.append(element("p", "NLI 输入超过长度限制，已截断。", "hint"));
  return info;
}

function renderTrace(trace) {
  const block = element("div", undefined, "trace");
  block.append(details("首轮 BM25 检索与作答",
    element("p", trace.draft || "未得到首答", "draft"),
    passages(trace.initial)
  ), details("DeBERTa NLI 核验", verification(trace)));
  const decision = element("div", undefined, "verification");
  const topology = trace.bridge === 1 ? "未检测到衔接" : trace.bridge === 0 ? "检测到衔接" : "无法判断";
  decision.append(
    element("p", `缺证风险 ${trace.risk?.toFixed(3) ?? "—"} · ${topology}`),
    element("p", `门控得分 ${trace.score?.toFixed(3) ?? "—"} · 校准阈值 ${trace.boundary.toFixed(3)}`),
    element("p", trace.triggered
      ? (trace.route === "top2" ? "已补查一次，保留首答。" : "已补查一次，并根据扩展后的材料重新作答。")
      : "本题结束，保留首答。", "hint")
  );
  block.append(details("Sugeno 模糊门控", decision));
  if (trace.triggered) block.append(details(`新增检索段落 · ${trace.additional.length}`, passages(trace.additional)));
  return block;
}

function renderAnswer(title, result, fuzzy = false) {
  const card = element("article", undefined, fuzzy ? "card fuzzy" : "card");
  const top = element("div", undefined, "card-top");
  top.append(element("h3", title));
  if (fuzzy) {
    const text = !result.trace.draft ? "首答失败" : result.trace.triggered ? "补查一次" : "保留首答";
    top.append(element("span", text, "route-tag"));
  }
  card.append(top, element("p", result.ok ? result.answer : "模型未返回有效答案", "answer"));
  const { attempts, calls, input_tokens, output_tokens } = result.stats;
  card.append(element("p", `Qwen ${calls} 次 · 输入 ${input_tokens} tokens · 输出 ${output_tokens} tokens`, "stats"));
  if (attempts !== calls) card.append(element("p", `共 ${attempts} 次尝试，token 数按成功调用统计。`, "hint"));

  const references = element("div", undefined, "references");
  if (result.evidence.length) {
    for (const item of result.evidence) {
      const quote = element("blockquote");
      quote.append(element("cite", `${item.title} · 原文第 ${item.index + 1} 句`), element("p", item.text));
      references.append(quote);
    }
  } else {
    references.append(element("p", "系统未选出可展示的句级引用。", "hint"));
  }
  const citations = details(`最终引用 · ${result.evidence.length} 句`, references);
  citations.open = true;
  card.append(citations);
  if (fuzzy) card.append(renderTrace(result.trace));
  else card.append(details(`送入模型的检索段落 · ${result.context.length}`, passages(result.context)));
  return card;
}

function showResult(data) {
  const turn = element("article", undefined, "turn");
  const question = element("div", undefined, "turn-question");
  question.append(element("span", `提问 · ${data.pool_size} 段候选资料`), element("h2", data.question));
  const cards = element("div", undefined, "cards");
  if (data.baseline) cards.append(renderAnswer("2+1 直接作答", data.baseline));
  if (data.fuzzy) cards.append(renderAnswer("NLI + Sugeno", data.fuzzy, true));
  turn.append(question, cards);
  get("conversation").prepend(turn);
}

get("sample-tab").addEventListener("click", () => { state.input = "sample"; updateInput(); });
get("custom-tab").addEventListener("click", () => { state.input = "custom"; updateInput(); });
get("qid").addEventListener("change", showSelectedQuestion);

get("ask-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (state.running) return;
  const body = { strategy: get("strategy").value };
  if (state.input === "sample") body.qid = get("qid").value;
  else {
    body.question = get("question").value.trim();
    body.passages = get("passages").value.trim().split(/\r?\n[\t \r]*\r?\n/).map(p => p.trim()).filter(Boolean);
  }
  state.running = true;
  get("submit").disabled = true;
  setStatus(state.catalog.mode === "live" ? "正在检索并调用模型，预计需要几十秒。" : "正在读取 P5 记录。");
  try {
    const data = await fetchJson("/api/ask", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
    });
    showResult(data);
    setStatus("问答完成。");
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    state.running = false;
    get("submit").disabled = false;
  }
});

initialize();

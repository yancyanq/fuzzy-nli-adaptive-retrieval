"""Group 13's P5 chatbot. Start with python3 demo/app.py."""

from argparse import ArgumentParser
import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import sys
from threading import Lock
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen


HERE = Path(__file__).resolve().parent
EXP = HERE.parent / "exp"
P5 = EXP / "v3" / "p5"
INPUT = P5 / "input"
ARCHIVE = P5 / "remote-evidence" / "live"
BASE = "v2_direct_2plus1"
FIRST = "top2"
EXPANDED = "direct_2plus4"
POLICY = "full_sugeno_seed42"
STRATEGIES = ("compare", "baseline", "fuzzy")
ROUTES = (BASE, FIRST, EXPANDED)


def load_p15():
    spec = importlib.util.spec_from_file_location("p15_runner", EXP / "v3" / "p1_5" / "run.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


P15 = load_p15()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_archive(filename, key, keep):
    return {key(row): row for row in P15.read_jsonl(ARCHIVE / filename) if keep(row)}


def evidence_for(pool, run):
    output = []
    contexts = pool["input"]["contexts"]
    for title, index in run["sp"]:
        matches = [
            chunk["sentences"][index]
            for i in run["paragraph_indices"]
            for chunk in [contexts[i]]
            if chunk["title"] == title and 0 <= index < len(chunk["sentences"])
        ]
        if matches and len({item["text"] for item in matches}) == 1:
            output.append({"title": title, "sentence_id": matches[0]["sentence_id"],
                           "index": index, "text": matches[0]["text"].strip()})
    return output


def paragraph_views(pool, indices):
    views = []
    for i in indices:
        chunk = pool["input"]["contexts"][i]
        views.append({"id": i, "title": chunk["title"],
                      "text": " ".join(s["text"].strip() for s in chunk["sentences"])})
    return views


def result_card(pool, run, calls):
    good = [call for call in calls if call["ok"]]
    return {
        "answer": run["answer"] if run["ok"] else "",
        "ok": run["ok"],
        "evidence": evidence_for(pool, run),
        "evidence_status": run.get("evidence_reason"),
        "stats": {"calls": len(good), "attempts": sum(len(call["attempts"]) for call in calls),
                  "input_tokens": sum(call["input_tokens"] for call in good),
                  "output_tokens": sum(call["output_tokens"] for call in good)},
    }


def fuzzy_trace(pool, first, expanded, feature, decision, boundary):
    return {
        "draft": first["answer"] if first["ok"] else "",
        "draft_cited": [pool["input"]["contexts"][first["paragraph_indices"][i - 1]]["title"]
                         for i in first["citations"]],
        "initial": paragraph_views(pool, first["paragraph_indices"]),
        "additional": paragraph_views(
            pool, [i for i in (expanded or {}).get("paragraph_indices", []) if i not in first["paragraph_indices"]]
        ),
        "triggered": decision["triggered"], "route": decision["final_route"],
        "reason": decision["reason"], "score": decision["decision_score"], "boundary": boundary,
        "bridge": feature.get("bridge"), "risk": feature.get("risk"),
        "probabilities": feature.get("nli_probabilities"), "nli_fallback": feature.get("nli_premise_fallback"),
        "nli_truncated": feature.get("nli_truncated", False),
    }


class Replay:
    mode = "replay"

    def __init__(self):
        self.cfg = read_json(P5 / "protocol.json")
        self.lock = read_json(P5 / "policy_lock.json")
        if (P15.file_hash(P5 / "protocol.json") != self.lock["protocol_sha256"]
                or P15.file_hash(P5 / "policy.py") != self.lock["model_logic_sha256"]):
            raise ValueError("P5 protocol and policy must match the frozen lock")
        self.size = self.cfg["primary_size"]
        self.budget = self.cfg["primary_budget_percent"]
        self.boundary = -self.lock["boundaries"][POLICY][str(self.budget)][0]
        self.pools = {qid: pool for (_, qid), pool in P15.load_pools(INPUT / "pools.jsonl", [self.size]).items()}

        def primary(row):
            return row["pool_size"] == self.size and row["qid"] in self.pools

        self.quality = read_archive("quality.jsonl", lambda r: (r["qid"], r["route"]),
                                    lambda r: primary(r) and r["route"] in ROUTES)
        self.feature = read_archive("features.jsonl", lambda r: r["qid"], primary)
        self.decision = read_archive("decisions.jsonl", lambda r: r["qid"],
                                     lambda r: primary(r) and r["policy"] == POLICY
                                     and r["budget_percent"] == self.budget)
        for qid, pool in self.pools.items():
            rows = [self.feature[qid], self.decision[qid], *(self.quality[qid, route] for route in ROUTES)]
            if any(row["pool_sha256"] != pool["pool_sha256"] for row in rows):
                raise ValueError(f"P5 records do not match the question pool {qid}")
        timing = read_json(INPUT / "split.json")["timing_qids"]
        self.featured = [
            next(qid for qid in timing if self.decision[qid]["triggered"] == triggered
                 and all(self.quality[qid, route]["ok"] for route in ROUTES))
            for triggered in (True, False)
        ]

    def catalog(self):
        return {"mode": self.mode, "pool_size": self.size, "budget": self.budget, "featured": self.featured,
                "questions": [{"qid": qid, "question": self.pools[qid]["input"]["question"]}
                              for qid in (*self.featured, *sorted(self.pools.keys() - set(self.featured)))]}

    def run(self, strategy, qid=None, question=None, passages=None):
        if qid not in self.pools or question is not None or passages is not None:
            raise ValueError("归档回放请选择一条 P5 实验题。")
        pool = self.pools[qid]
        output = {"mode": self.mode, "qid": qid, "question": pool["input"]["question"], "pool_size": self.size}
        if strategy in ("compare", "baseline"):
            direct = self.quality[qid, BASE]
            output["baseline"] = result_card(pool, direct, direct["calls"]) | {
                "context": paragraph_views(pool, direct["paragraph_indices"])}
        if strategy in ("compare", "fuzzy"):
            first = self.quality[qid, FIRST]
            decision = self.decision[qid]
            expanded = self.quality[qid, EXPANDED] if decision["triggered"] else None
            final = self.quality[qid, decision["final_route"]]
            calls = first["calls"][:1] + (expanded["calls"][:1] if expanded else []) + final["calls"][1:]
            output["fuzzy"] = result_card(pool, final, calls) | {
                "trace": fuzzy_trace(pool, first, expanded, self.feature[qid], decision, self.boundary)}
        return output


def custom_pool(question, passages):
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 300:
        raise ValueError("请输入 1–300 字符的问题。")
    if not isinstance(passages, list) or not 2 <= len(passages) <= 30:
        raise ValueError("请输入 2–30 段候选资料，用空行分隔。")
    contexts = []
    for index, passage in enumerate(passages, 1):
        if not isinstance(passage, str) or not 1 <= len(passage.strip()) <= 1000:
            raise ValueError("每段资料须为 1–1,000 字符。")
        chunk_id = P15.digest([index, passage])
        sentences = re.split(r"(?<=[.!?。！？])\s+", passage.strip())
        contexts.append({"chunk_id": chunk_id, "title": f"用户资料 {index}", "sentences": [
            {"sentence_id": f"{chunk_id}:{n}", "text": sentence} for n, sentence in enumerate(sentences)
        ]})
    payload = {"question": question.strip(), "contexts": contexts}
    digest = P15.digest(payload)
    return {"qid": digest[:24], "pool_size": len(contexts), "pool_sha256": digest, "input": payload}


class TracedRuntime:
    """Record the precise intermediate responses from the unmodified P5 runner."""

    def __init__(self, runtime):
        self.runtime = runtime
        self.answers = {}

    def __getattr__(self, name):
        return getattr(self.runtime, name)

    def answer(self, pool, ex, route, audit, ledger):
        response = self.runtime.answer(pool, ex, route, audit, ledger)
        self.answers[route] = response
        return response


class TracedNli:
    def __init__(self, nli):
        self.nli = nli
        self.feature = {}

    def get(self, input_row):
        self.feature = self.nli.get(input_row)
        return self.feature


class Live(Replay):
    mode = "live"

    def __init__(self, args):
        super().__init__()
        for directory in ("v3/p5", "v3/p2", "v3/p3", "v2"):
            sys.path.insert(0, str(EXP / directory))
        from transformers import AutoTokenizer
        import runtime

        cap = self.cfg["services"][str(self.size)]["context"]
        endpoint = args.model_url.rstrip("/")
        with urlopen(endpoint + "/models", timeout=10) as response:
            models = json.load(response)["data"]
        if not any(model["id"] == self.cfg["model"] and model.get("max_model_len") == cap for model in models):
            raise ValueError(f"需要 {self.cfg['model']} 和 {cap} token 的 P5 vLLM 服务")
        runtime.URL = endpoint
        self.runtime = runtime
        self.rt = runtime.Runtime(self.cfg, AutoTokenizer.from_pretrained(str(args.tokenizer), local_files_only=True), cap)
        self.nli = runtime.NLI(self.cfg, args.snapshot)
        self.model_lock = Lock()
        self.audit = {
            (r["pool_size"], r["qid"], r["route"]): r for r in P15.read_jsonl(INPUT / "lengths.jsonl")
            if r["pool_size"] == self.size and r["route"] in ROUTES
        }

    def run(self, strategy, qid=None, question=None, passages=None):
        if qid is not None:
            if qid not in self.pools or question is not None or passages is not None:
                raise ValueError("请选择一条实验题，或输入问题和候选资料。")
            pool = self.pools[qid]
            audit = self.audit
        else:
            pool = custom_pool(question, passages)
            audit = self.custom_audit(pool)
        output = {"mode": self.mode, "qid": pool["qid"], "question": pool["input"]["question"],
                  "pool_size": pool["pool_size"]}
        if not self.model_lock.acquire(blocking=False):
            raise RuntimeError("正在处理另一条请求，请稍后再试。")
        try:
            if strategy in ("compare", "baseline"):
                run = self.rt.direct(pool, BASE, audit)
                output["baseline"] = result_card(pool, run, run["calls"]) | {
                    "context": paragraph_views(pool, run["paragraph_indices"])}
            if strategy in ("compare", "fuzzy"):
                rt, nli = TracedRuntime(self.rt), TracedNli(self.nli)
                decision = self.runtime.timed(rt, nli, pool, audit, self.lock, POLICY, self.budget)
                final = rt.answers[decision["final_route"]] | {
                    "sp": decision["sp"], "evidence_reason": decision["citation_reason"]}
                output["fuzzy"] = result_card(pool, final, decision["calls"]) | {
                    "trace": fuzzy_trace(pool, rt.answers[FIRST], rt.answers.get(EXPANDED),
                                         nli.feature, decision, self.boundary)}
        finally:
            self.model_lock.release()
        return output

    def custom_audit(self, pool):
        audit = {}
        runtime = self.runtime
        ex = runtime.example_from_pool(pool)
        for route in ROUTES:
            indices = runtime.route_indices(runtime.v2, ex, route)
            messages = runtime.answer_messages(runtime.v2, ex, indices, route)
            tokens = self.rt.count(messages)
            if tokens + self.cfg["max_output_tokens"] > self.rt.cap:
                raise ValueError("检索后的资料超出模型上下文，请缩短候选内容。")
            audit[pool["pool_size"], pool["qid"], route] = {
                "pool_sha256": pool["pool_sha256"], "input_tokens": tokens,
                "prompt_sha256": P15.digest(messages),
                "chunk_ids": [pool["input"]["contexts"][i]["chunk_id"] for i in indices],
            }
        return audit


ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}


class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, body, content_type, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(body)

    def json_response(self, data, status=200):
        self.send_bytes(P15.encoded(data), "application/json; charset=utf-8", status)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/questions":
            self.json_response(self.server.app.catalog())
        elif path in ASSETS:
            name, mime = ASSETS[path]
            self.send_bytes((HERE / "static" / name).read_bytes(), mime)
        else:
            self.json_response({"error": "页面不存在。"}, 404)

    def do_POST(self):
        if self.path != "/api/ask":
            self.json_response({"error": "接口不存在。"}, 404)
            return
        if self.headers.get_content_type() != "application/json":
            self.json_response({"error": "请求须使用 JSON。"}, 415)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 150_000:
                raise ValueError("请求为空或过长。")
            body = json.loads(self.rfile.read(size).decode("utf-8"))
            if not isinstance(body, dict) or set(body) - {"strategy", "qid", "question", "passages"}:
                raise ValueError("请求字段无效。")
            strategy = body.pop("strategy", "compare")
            if strategy not in STRATEGIES:
                raise ValueError("请选择有效的问答策略。")
            qid = body.get("qid")
            if qid is not None and not isinstance(qid, str):
                raise ValueError("题目编号无效。")
        except (ValueError, TypeError, UnicodeError):
            self.json_response({"error": "请求格式无效或内容过长。"}, 400)
            return
        try:
            result = self.server.app.run(strategy, **body)
        except ValueError as exc:
            self.log_error("%s", exc)
            message = str(exc)
            if message and ord(message[0]) > 127:
                self.json_response({"error": message}, 400)
            else:
                self.json_response({"error": "问答未能完成，请检查模型服务和 P5 输入。"}, 502)
        except (RuntimeError, URLError) as exc:
            self.log_error("%s", exc)
            self.json_response({"error": "模型正在处理另一条请求，或暂时无法响应。"}, 503)
        else:
            self.json_response(result)


def main():
    cli = ArgumentParser(description=__doc__)
    cli.add_argument("--port", type=int, default=7860)
    cli.add_argument("--live", action="store_true")
    cli.add_argument("--tokenizer", type=Path)
    cli.add_argument("--snapshot", type=Path)
    cli.add_argument("--model-url", default="http://127.0.0.1:18082/v1")
    args = cli.parse_args()
    if args.live and not (args.tokenizer and args.snapshot):
        cli.error("--live requires --tokenizer and --snapshot")
    app = Live(args) if args.live else Replay()
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        server.app = app
        print(f"FNLI QA ({app.mode}): http://127.0.0.1:{server.server_port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()

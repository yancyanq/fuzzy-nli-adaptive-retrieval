"""P5 measured online paths. This module has no access to gold or scores."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import json
import math
from pathlib import Path
from threading import Lock
from time import perf_counter, sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import p15_runner
from routes import answer_messages, example_from_pool, route_indices
from policy import decide
from first_round import validate_a
import compare_models as v2
import generate_test_v2 as selector
import guided

URL = "http://127.0.0.1:18082/v1"


@dataclass
class Ledger:
    remaining_input: int


class Runtime:
    def __init__(self, cfg, tokenizer, cap):
        self.cfg = cfg
        self.tokenizer = tokenizer
        self.cap = cap

    def count(self, messages):
        return len(self.tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True))

    def request(self, ledger, kind, messages, reserve, guided_json=None):
        tally = self.count(messages)
        started = perf_counter()
        call = {"kind": kind, "prompt_sha256": p15_runner.digest(messages), "expected_input_tokens": tally,
                "input_tokens": 0, "output_tokens": 0, "attempts": [], "ok": False}
        if tally+reserve > self.cap:
            return call | {"reason": "context_limit", "seconds": 0.}
        body = {"model": self.cfg["model"], "messages": messages, "max_tokens": reserve, "temperature": self.cfg["temperature"]}
        if guided_json:
            body.update(guided_json=guided_json, guided_decoding_backend="xgrammar")
        req = Request(URL + "/chat/completions", data=p15_runner.encoded(body), headers={"Content-Type": "application/json"})
        reason = "request_failed"
        for retry in range(1,4):
            if ledger.remaining_input < tally:
                reason = "budget_exhausted"
                break
            ledger.remaining_input -= tally
            sent = perf_counter()
            error = None
            try:
                with urlopen(req, timeout=420) as stream:
                    reply = json.load(stream)
                usage, choice = reply["usage"], reply["choices"][0]
                if (usage["prompt_tokens"] != tally or not 0 <= usage["completion_tokens"] <= reserve
                        or not isinstance(choice["message"]["content"], str)):
                    raise ValueError("Service usage or response violated the frozen prompt audit")
                call["attempts"].append({"index": retry, "http_status": 200, "seconds": perf_counter()-sent})
                return call | {"ok": True, "reason": None, "seconds": perf_counter()-started, "response_id": reply["id"],
                               "input_tokens": tally, "output_tokens": usage["completion_tokens"],
                               "finish_reason": choice["finish_reason"], "raw": choice["message"]["content"]}
            except HTTPError as err:
                error = {"http_status": err.code, "error": err.read(1024).decode(errors="replace")}
                if err.code not in {408,429,500,502,503,504}:
                    call["attempts"].append(error | {"index": retry, "seconds": perf_counter()-sent})
                    break
            except (URLError, TimeoutError, OSError) as err:
                error = {"error": str(err)}
            call["attempts"].append(error | {"index": retry, "seconds": perf_counter()-sent})
            if retry < 3:
                sleep(2**(retry-1))
        return call | {"reason": reason, "seconds": perf_counter()-started}

    def answer(self, pool, ex, route, audit, ledger):
        indices = route_indices(v2, ex, route)
        messages = answer_messages(v2, ex, indices, route)
        ids = [pool["input"]["contexts"][i]["chunk_id"] for i in indices]
        promised = audit[pool["pool_size"],pool["qid"],route]
        if (promised["pool_sha256"] != pool["pool_sha256"] or promised["chunk_ids"] != ids
                or promised["prompt_sha256"] != p15_runner.digest(messages)
                or promised["input_tokens"] != self.count(messages)):
            raise ValueError("Live answer input differs from the signed audit")
        call = self.request(ledger, "answer", messages, self.cfg["max_output_tokens"])
        parsed = v2.parse_response(call.get("raw",""))
        citations = [i for i in parsed["citations"] if type(i) is int and 1 <= i <= len(indices)]
        return {"answer": parsed["answer"], "citations": citations, "paragraph_indices": indices,
                "chunk_ids": ids, "calls": [call], "ok": call["ok"] and bool(parsed["answer"]),
                "parse_ok": parsed["parse_ok"], "invalid_citation_count": len(parsed["citations"])-len(citations),
                "reason": call["reason"] if not call["ok"] else None if parsed["answer"] else "empty_answer"}

    def evidence(self, ex, answer, ledger):
        candidates = list(enumerate(selector.sentence_candidates(ex, answer), start=1))
        pending = [candidates] if candidates and answer["ok"] else []
        calls, evidence = [], []
        reason = None if pending else "no_cited_sentences"
        reserve = self.cfg["selector_max_output_tokens"]
        while pending and len(calls) < self.cfg["selector_max_calls_per_answer"]:
            group = pending.pop()
            messages = selector.selector_messages(ex, answer, group)
            if self.count(messages)+reserve > self.cfg["selector_total_tokens_max"]:
                middle = len(group)//2
                if not middle:
                    reason = "overlong_single_sentence"
                    continue
                pending.extend((group[middle:], group[:middle]))
                continue
            call = self.request(ledger, "selector", messages, reserve)
            calls.append(call)
            if not call["ok"]:
                reason = call["reason"]
                if reason == "budget_exhausted":
                    break
                continue
            selected, ok, invalid = selector.parse_selector(call["raw"], dict(group))
            call.update(parse_ok=ok, invalid_ids=invalid, selected=selected)
            if not ok:
                reason = "selector_parse_failure"
            allowed = dict(group)
            evidence.extend((allowed[i][0], allowed[i][1]) for i in selected)
        if pending and reason is None:
            reason = "selector_call_limit"
        return [list(x) for x in dict.fromkeys(evidence)], calls, reason

    def project_a(self, pool, a):
        contexts = [pool["input"]["contexts"][i] for i in a["paragraph_indices"]]
        row = {"qid": pool["qid"], "pool_sha256": pool["pool_sha256"], "a_prompt_sha256": a["calls"][0]["prompt_sha256"],
               "question": pool["input"]["question"], "draft_answer": a["answer"], "draft_citations": a["citations"],
               "contexts": contexts}
        validate_a(row)
        return row

    def selfcheck(self, pool, a, ledger):
        if not a["ok"]:
            return {"risk": None, "reason": "a_unavailable", "calls": []}
        row = self.project_a(pool,a)
        prompt = guided.wire_messages(row,"selfcheck",example_free=True)
        call = self.request(ledger,"selfcheck",prompt,self.cfg["selfcheck_max_output_tokens"],guided.schema(row,"selfcheck"))
        result = guided.validate_wire(call["raw"],row,"selfcheck") if call["ok"] else {}
        return {"risk": result.get("risk"), "reason": result.get("reason",call["reason"]), "calls": [call]}

    def direct(self, pool, route, audit):
        started = perf_counter()
        ledger = Ledger(self.cfg["cumulative_qwen_input_limit"])
        ex = example_from_pool(pool)
        ans = self.answer(pool, ex, route, audit, ledger)
        evidence, calls, reason = self.evidence(ex, ans, ledger)
        result = {k: pool[k] for k in ("qid","pool_size","pool_sha256")}
        return result | ans | {"route": route, "sp": evidence, "calls": ans["calls"]+calls, "evidence_reason": reason,
                               "seconds": perf_counter()-started, "budget_remaining": ledger.remaining_input}


class NLI:
    def __init__(self, cfg, snapshot):
        import torch
        from run_pilot import HFNliScorer
        from pathlib import Path
        spec = cfg["nli"]
        if p15_runner.file_hash(Path(snapshot) / "model.safetensors") != spec["model_sha256"]:
            raise ValueError("DeBERTa weights failed identity check")
        torch.set_num_threads(spec["threads"])
        self.limit = spec["input_tokens_max"]
        self.scorer = HFNliScorer(str(snapshot), "cpu", max_length=self.limit, batch_size=1)
        self.lock = Lock()

    def get(self, a):
        from run_pilot import build_hypothesis, build_premise
        from analyze_pilot_signals_v2 import bridge_matches
        if not a["draft_answer"]:
            return {"risk": None,"bridge": None,"nli_seconds": 0.,"nli_input_tokens": 0,"nli_truncated": False}
        validate_a(a)
        before = perf_counter()
        context = [[c["title"], [s["text"] for s in c["sentences"]]] for c in a["contexts"]]
        premise = build_premise({"context": context},a["draft_citations"],[0,1])
        hyp = build_hypothesis(a["question"],a["draft_answer"])
        queued = perf_counter()
        with self.lock:
            scoring = perf_counter()
            (prediction,) = self.scorer.score_many([{"premise": premise["premise"], "hypothesis": hyp}])
        probs = prediction["probs"]
        if (set(probs) != {"entailment","neutral","contradiction"} or not math.isclose(sum(probs.values()),1.,abs_tol=1e-6)
                or any(not 0 <= value <= 1 for value in probs.values())):
            raise ValueError("Invalid NLI probabilities")
        bridge = bridge_matches(context,[0,1])
        return {"risk": 1-probs["entailment"], "bridge": None if bridge is None else int(not bridge),
                "nli_seconds": perf_counter()-before, "nli_queue_seconds": scoring-queued, "nli_truncated": prediction["truncated"],
                "nli_input_tokens": min(self.limit,prediction["n_tokens"]), "nli_probabilities": probs,
                "nli_premise_fallback": premise["used_fallback"]}


def timed(rt, nli, pool, audit, lock, method, budget):
    started = perf_counter()
    ledger = Ledger(rt.cfg["cumulative_qwen_input_limit"])
    ex = example_from_pool(pool)
    first = rt.answer(pool,ex,"top2",audit,ledger)
    feature = {"risk": None, "bridge": None, "nli_seconds": 0., "nli_input_tokens": 0}
    qwen = {"calls": [], "risk": None}
    if first["ok"] and method == "qwen_selfcheck":
        qwen = rt.selfcheck(pool,first,ledger)
    elif first["ok"]:
        feature = nli.get(rt.project_a(pool,first))
    yes, score, reason = decide(lock,method,budget,pool["qid"],feature["risk"],feature["bridge"],qwen["risk"])
    route = "v2_direct_2plus1" if method == "v2_native" else "direct_2plus4"
    expanded = rt.answer(pool,ex,route,audit,ledger) if yes and first["ok"] else None
    final = expanded if expanded and expanded["ok"] else first
    sp, cites, citation_reason = rt.evidence(ex,final,ledger)
    return {k:pool[k] for k in ("qid","pool_size","pool_sha256")} | {
        "policy":method,"budget_percent":budget,"triggered":bool(expanded),"final_route":route if final is expanded else "top2",
        "decision_score":score, "reason":expanded["reason"] if expanded and not expanded["ok"] else reason,
        "answer":final["answer"],"sp":sp,"calls":first["calls"]+qwen["calls"]+(expanded["calls"] if expanded else [])+cites,
        "citation_reason":citation_reason,"seconds":perf_counter()-started, "budget_remaining":ledger.remaining_input,
        "nli_seconds":feature["nli_seconds"],"nli_input_tokens":feature["nli_input_tokens"],"ok":final["ok"]}


def read_index(path, fields):
    rows = p15_runner.read_jsonl(path) if path.exists() else []
    result = {tuple(row[k] for k in fields): row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"Duplicate durable journal record in {path.name}")
    return result


def run_jobs(path, fields, jobs, worker, workers, label):
    previous = read_index(path, fields)
    if len({job for job in jobs}) != len(jobs):
        raise ValueError("Ambiguous run identity")
    todo = [job for job in jobs if job not in previous]
    with ThreadPoolExecutor(max_workers=workers) as executor, path.open("a",encoding="utf-8") as stream:
        for start in range(0,len(todo),workers):
            started = perf_counter()
            jobs_now = todo[start:start+workers]
            tasks = [executor.submit(worker, *job) for job in jobs_now]
            for result in as_completed(tasks):
                row = result.result()
                p15_runner.append(stream,row)
            completed = len(jobs)-len(todo)+start+len(tasks)
            if completed % 40 == 0 or completed == len(jobs):
                print(json.dumps({"part":label,"n":completed,"target":len(jobs),"last_batch_seconds":perf_counter()-started,
                                  "utc":p15_runner.utc_now()}),flush=True)

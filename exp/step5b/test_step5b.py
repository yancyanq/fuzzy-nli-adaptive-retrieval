#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit + mock end-to-end tests for Step 5b (rerun_toplogprobs.py).

All numbers produced against the mock server are FAKE (deterministic hashes),
and the per_question.csv used here is SYNTHETIC. They are NOT results.
Run: python3 test_step5b.py
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEP3 = HERE.parent / "step3"
STEP5 = HERE.parent / "step5"
sys.path.insert(0, str(HERE))
import rerun_toplogprobs as rt  # noqa: E402

cm = rt.cm
SECRET = "sk-testSECRET0123456789"


class TestMath(unittest.TestCase):
    def test_margin_known(self):
        alts = [["b", -1.5], ["a", -0.2], ["c", -3.0]]  # unsorted on purpose
        self.assertAlmostEqual(rt.token_margin(alts), 1.3)

    def test_margin_with_zero_top1(self):
        self.assertAlmostEqual(rt.token_margin([["x", 0.0], ["y", -2.0]]), 2.0)

    def test_margin_missing(self):
        self.assertIsNone(rt.token_margin([["x", -0.1]]))
        self.assertIsNone(rt.token_margin([]))
        self.assertIsNone(rt.token_entropy([["x", -0.1]]))

    def test_entropy_uniform(self):
        alts = [[str(i), math.log(0.1)] for i in range(4)]  # renormalised -> uniform 1/4
        self.assertAlmostEqual(rt.token_entropy(alts), math.log(4))

    def test_entropy_known_two(self):
        # probs 0.6 / 0.2 -> renormalised 0.75 / 0.25
        h = -(0.75 * math.log(0.75) + 0.25 * math.log(0.25))
        self.assertAlmostEqual(rt.token_entropy([["a", math.log(0.6)], ["b", math.log(0.2)]]), h)

    def test_span_matches_compare_models_rule(self):
        toks = ['{"', "answer", '":', ' "', "New", " York", '",', ' "', "citations", '":', " [", "1", "]}"]
        lps = [-0.01 * (i + 1) for i in range(len(toks))]
        idx, fb = rt.answer_span_indices(toks, "New York")
        self.assertFalse(fb)
        self.assertEqual(idx, [4, 5])
        items = [{"token": t, "logprob": lp} for t, lp in zip(toks, lps)]
        mean_lp, min_lp, _ = cm.summarize_logprobs(items, "New York")
        self.assertAlmostEqual(mean_lp, sum(lps[i] for i in idx) / len(idx))
        self.assertAlmostEqual(min_lp, min(lps[i] for i in idx))

    def test_span_fallback(self):
        idx, fb = rt.answer_span_indices(["a", "b"], "zzz")
        self.assertTrue(fb)
        self.assertEqual(idx, [0, 1])
        idx, fb = rt.answer_span_indices(["a", "b"], "")
        self.assertTrue(fb)

    def test_branch_metrics_known(self):
        recs = [
            {"t": '{"answer": "', "lp": 0.0, "top": [['{"answer": "', 0.0], ["x", -5.0]]},
            {"t": "Paris", "lp": 0.0, "top": [["Paris", 0.0], ["Lyon", -2.0], ["Nice", -4.0]]},
            {"t": " Texas", "lp": 0.0, "top": [["Austin", -0.1], [" Texas", -0.5]]},  # chosen != top1
            {"t": '"}', "lp": 0.0, "top": [['"}', 0.0]]},  # one alternative -> missing
        ]
        met = rt.branch_metrics(recs, "Paris Texas")
        self.assertFalse(met["span_fallback"])
        self.assertEqual(met["n_span_tokens"], 2)
        self.assertAlmostEqual(met["mean_margin"], (2.0 + 0.4) / 2)
        self.assertAlmostEqual(met["min_margin"], 0.4)
        self.assertAlmostEqual(met["first_margin"], 2.0)
        self.assertEqual(met["n_chosen_ne_top1"], 1)
        self.assertEqual(met["n_top1_alt_zero"], 3)
        self.assertEqual(met["n_chosen_lp_zero"], 4)
        self.assertEqual(met["n_margin_missing"], 0)
        met2 = rt.branch_metrics(recs, "")  # fallback: all tokens, last one missing
        self.assertTrue(met2["span_fallback"])
        self.assertEqual(met2["n_margin_missing"], 1)
        self.assertAlmostEqual(met2["mean_margin"], (5.0 + 2.0 + 0.4) / 3)


class TestAUCOrientation(unittest.TestCase):
    def _rows(self):
        rows = []
        for m in (0.1, 0.2, 0.3):
            rows.append({"label": "improved", "unchanged_both": True, "mean_margin_A": m, "min_margin_A": m,
                         "first_margin_A": m, "mean_entropy_A": 2 - m, "nli_entailment_A": 0.5})
        for m in (1.0, 2.0, 3.0):
            rows.append({"label": "tie", "unchanged_both": True, "mean_margin_A": m, "min_margin_A": m,
                         "first_margin_A": m, "mean_entropy_A": 2 - m, "nli_entailment_A": 0.5})
        rows.append({"label": "tie", "unchanged_both": False, "mean_margin_A": 0.05, "min_margin_A": 0.05,
                     "first_margin_A": 0.05, "mean_entropy_A": 1.95, "nli_entailment_A": 0.9})
        rows.append({"label": "degraded", "unchanged_both": True, "mean_margin_A": 0.0, "min_margin_A": 0.0,
                     "first_margin_A": 0.0, "mean_entropy_A": 2.0, "nli_entailment_A": 0.9})
        return rows

    def test_low_margin_high_entropy_gives_auc_1(self):
        a, _ = rt.analyze(self._rows(), n_boot=200, seed=42)
        p = a["primary_unchanged_AB"]
        self.assertEqual(p["n_by_class"], {"improved": 3, "tie": 3, "degraded": 1})
        self.assertAlmostEqual(p["signals"]["mean_margin_A"]["auc_improved_vs_tie"], 1.0)
        self.assertAlmostEqual(p["signals"]["mean_entropy_A"]["auc_improved_vs_tie"], 1.0)
        self.assertAlmostEqual(p["signals"]["nli_entailment_A"]["auc_improved_vs_tie"], 0.5)

    def test_sensitivity_includes_changed(self):
        a, _ = rt.analyze(self._rows(), n_boot=200, seed=42)
        s = a["sensitivity_all"]
        self.assertEqual(s["n_by_class"]["tie"], 4)
        # changed tie row has the lowest margin -> beats all 3 improved: AUC = 9/12
        self.assertAlmostEqual(s["signals"]["mean_margin_A"]["auc_improved_vs_tie"], 9 / 12)

    def test_same_subset_for_nli(self):
        rows = self._rows() + [{"label": "improved", "unchanged_both": True, "mean_margin_A": None,
                                "nli_entailment_A": 0.0}]
        a, ex = rt.analyze(rows, n_boot=100, seed=42)
        self.assertEqual(ex["no_margin_A"], 1)
        self.assertEqual(a["primary_unchanged_AB"]["signals"]["nli_entailment_A"]["n_improved"], 3)


class TestConsistencyAndCache(unittest.TestCase):
    def test_normalised_equality(self):
        self.assertTrue(rt.answers_equal("The United States.", "united states"))
        self.assertFalse(rt.answers_equal("USA", "United States"))

    def test_cache_isolation_guard(self):
        with tempfile.TemporaryDirectory() as d:
            for bad in (os.path.join(d, "cache.jsonl"), os.path.join(d, "other", "cache.jsonl")):
                with self.assertRaises(SystemExit):
                    with redirect_stderr(io.StringIO()):
                        rt.assert_cache_isolated(bad, d)
            rt.assert_cache_isolated(os.path.join(d, "out", rt.CACHE_NAME), d)  # ok

    def test_cache_key_and_resume_skips_errors(self):
        class A:  # minimal args
            k, m, temperature, max_tokens = 2, 1, 0.0, 128
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, rt.CACHE_NAME)
            base = {"model": "M", "_id": "q1", "branch": "A", "k": 2, "m": 1, "temperature": 0.0,
                    "max_tokens": 128, "content": "{}", "tokens": []}
            rt.append_toplp_cache(p, {**base, "top_logprobs": 5, "error": "Timeout"})
            rt.append_toplp_cache(p, {**base, "top_logprobs": 3, "error": None})
            rt.append_toplp_cache(p, {**base, "branch": "B", "top_logprobs": 5, "error": None, "k": 3})
            with open(p, "a") as f:
                f.write('{"half-written')
            with redirect_stderr(io.StringIO()):
                t = rt.load_toplp_cache(p, "M", A)
            self.assertEqual(list(t), [("M", "q1", "A", 3)])


# ---------------------------------------------------------------------------
# End-to-end against the mock server (FAKE numbers)
# ---------------------------------------------------------------------------
def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_mock(data_path, counter_path, port):
    cmd = [sys.executable, str(STEP3 / "test_mock_server.py"), "--host", "127.0.0.1", "--port", str(port),
           "--answers-from", str(data_path), "--counter", str(counter_path),
           "--top-logprobs-mode", "deepseek_t0"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.time() + 8
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(proc.communicate())
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.4) as r:
                if r.status == 200:
                    return proc, f"http://127.0.0.1:{port}/v1"
        except Exception:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("mock server did not start")


def _counter(path):
    if not os.path.isfile(path):
        return 0, []
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    return int(d.get("n_requests") or 0), d.get("requests") or []


def _mock_answers(data):
    """What the mock returns per branch (imported from the mock itself)."""
    sys.path.insert(0, str(STEP3))
    import test_mock_server as tms
    tms.GOLD = {ex["question"].strip(): ex.get("answer") or "" for ex in data}
    out = {}
    for ex in data:
        r1, r2 = cm.retrieve_indices(ex, 2, 1)
        for b, idx in (("A", list(r1)), ("B", list(r1) + list(r2))):
            user = cm.build_messages(ex, idx)[1]["content"]
            out[(ex["_id"], b)] = tms.make_answer(user)["answer"]
    return out


class TestEndToEndMock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="step5b_mock_")
        cls.root = Path(cls.tmp.name)
        cls.data_path = STEP5 / "testdata" / "mini_pilot.json"
        cls.data = json.loads(cls.data_path.read_text(encoding="utf-8"))
        assert len(cls.data) == 4
        ans = _mock_answers(cls.data)
        # SYNTHETIC Step 5 folder: labels and NLI values are invented for the test.
        cls.step5 = cls.root / "step5_pilot"
        cls.step5.mkdir()
        labels = ["improved", "improved", "tie", "tie"]
        nli = [0.30, 0.60, 0.90, 0.20]
        rows = []
        for i, ex in enumerate(cls.data):
            a, b = ans[(ex["_id"], "A")], ans[(ex["_id"], "B")]
            if i == 3:
                a = "SYNTHETIC-DIFFERENT-ANSWER"  # forces one CHANGED answer
            rows.append({"_id": ex["_id"], "delta_class": labels[i], "answer_A": a, "answer_B": b,
                         "F1_A": 0.0, "F1_B": 1.0, "nli_entailment_A": nli[i], "nli_entailment_B": 0.9})
        with open(cls.step5 / "per_question.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        cls.step5_cache = cls.step5 / "cache.jsonl"
        cls.step5_cache.write_text('{"sentinel": "step5 cache must stay untouched"}\n', encoding="utf-8")
        cls.step5_hash = hashlib.sha256(cls.step5_cache.read_bytes()).hexdigest()
        cls.counter = cls.root / "counter.json"
        cls.proc, cls.url = _start_mock(cls.data_path, cls.counter, _free_port())
        os.environ["LOCAL_API_KEY"] = SECRET

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
        cls.tmp.cleanup()

    def _run(self, out, extra=()):
        argv = ["--data", str(self.data_path), "--preset", "custom", "--base-url", self.url,
                "--model", "mock-qa", "--key-env", "LOCAL_API_KEY", "--n", "4",
                "--step5-dir", str(self.step5), "--out", str(out), "--bootstrap-samples", "300", *extra]
        buf, err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf), redirect_stderr(err):
            rc = rt.main(argv)
        self.assertEqual(rc, 0, msg=err.getvalue())
        return buf.getvalue(), err.getvalue()

    def test_full_flow(self):
        out = self.root / "step5b_toplp"
        n0, _ = _counter(self.counter)
        stdout, stderr = self._run(out)
        n1, reqs = _counter(self.counter)
        self.assertEqual(n1 - n0, 8)  # 4 questions x 2 branches
        for r in reqs[n0:]:
            self.assertTrue(r["logprobs"])
            self.assertEqual(r["top_logprobs"], 5)
            self.assertEqual(r["temperature"], 0.0)
        self.assertNotIn(SECRET, stdout + stderr)
        self.assertIn("LOCAL_API_KEY=set", stdout)
        # Step 5 cache untouched; own cache written
        self.assertEqual(hashlib.sha256(self.step5_cache.read_bytes()).hexdigest(), self.step5_hash)
        cache_lines = (out / rt.CACHE_NAME).read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(cache_lines), 8)
        rec = json.loads(cache_lines[0])
        self.assertEqual(rec["top_logprobs"], 5)
        self.assertTrue(rec["tokens"] and len(rec["tokens"][0]["top"]) == 5)
        self.assertNotIn(SECRET, (out / rt.CACHE_NAME).read_text(encoding="utf-8"))

        s = json.loads((out / "toplp_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(s["calls"]["new_api_calls_this_run"], 8)
        self.assertEqual(s["consistency_vs_step5"]["changed_answers_A"], 1)
        self.assertEqual(s["consistency_vs_step5"]["changed_answers_B"], 0)
        self.assertEqual(s["consistency_vs_step5"]["changed_ids_A"], [self.data[3]["_id"]])
        self.assertEqual(s["consistency_vs_step5"]["questions_both_unchanged"], 3)
        # deepseek_t0 mock: chosen logprob 0.0 everywhere, chosen == top1
        self.assertEqual(s["chosen_ne_top1_tokens"], {"A": 0, "B": 0})
        self.assertGreater(s["chosen_logprob_exactly_zero_tokens"]["A"], 0)
        self.assertEqual(s["chosen_logprob_exactly_zero_tokens"]["A"],
                         s["tokens_in_analysed_records"]["output_tokens_with_logprobs_A"])
        p = s["analysis"]["primary_unchanged_AB"]
        self.assertEqual(p["n_by_class"], {"improved": 2, "tie": 1, "degraded": 0})
        self.assertEqual(s["analysis"]["sensitivity_all"]["n_by_class"]["tie"], 2)
        for sub in ("primary_unchanged_AB", "sensitivity_all"):
            for col in ("mean_margin_A", "nli_entailment_A", "mean_entropy_A"):
                auc = s["analysis"][sub]["signals"][col]["auc_improved_vs_tie"]
                self.assertTrue(0.0 <= auc <= 1.0)
        # NLI AUC on synthetic values: primary improved {0.30,0.60} vs tie {0.90} -> 1.0
        self.assertAlmostEqual(p["signals"]["nli_entailment_A"]["auc_improved_vs_tie"], 1.0)
        self.assertIn("workaround", s["note"])
        self.assertIn("No gate threshold", s["note"])
        with open(out / "consistency.csv", encoding="utf-8-sig") as f:
            cons = list(csv.DictReader(f))
        self.assertEqual(len(cons), 8)
        self.assertEqual(cons[0]["status"], "CHANGED")  # changed rows listed first
        self.assertIn("PRIMARY", stdout)

        # resume: second run makes no new calls, same primary AUC
        n2, _ = _counter(self.counter)
        self._run(out)
        self.assertEqual(_counter(self.counter)[0], n2)
        s2 = json.loads((out / "toplp_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(s2["calls"]["cache_hits"], 8)
        self.assertEqual(s2["primary_result"], s["primary_result"])

        # analyze-only: no calls, identical analysis
        self._run(out, ["--analyze-only"])
        self.assertEqual(_counter(self.counter)[0], n2)
        s3 = json.loads((out / "toplp_summary.json").read_text(encoding="utf-8"))
        self.assertTrue(s3["analyze_only"])
        self.assertEqual(s3["analysis"], s["analysis"])
        self.assertEqual(hashlib.sha256(self.step5_cache.read_bytes()).hexdigest(), self.step5_hash)

    def test_analyze_only_empty_cache_and_skip_api_alias(self):
        out = self.root / "empty_out"
        n0, _ = _counter(self.counter)
        stdout, _ = self._run(out, ["--skip-api"])
        self.assertEqual(_counter(self.counter)[0], n0)
        s = json.loads((out / "toplp_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(s["calls"]["missing_not_called"], 8)
        self.assertEqual(s["analysis"]["primary_unchanged_AB"]["n_questions"], 0)
        self.assertIsNone(s["primary_result"]["auc_improved_vs_tie"])

    def test_refuses_step5_cache_path(self):
        with self.assertRaises(SystemExit):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                rt.main(["--data", str(self.data_path), "--preset", "custom", "--base-url", self.url,
                         "--model", "mock-qa", "--key-env", "LOCAL_API_KEY", "--n", "4",
                         "--step5-dir", str(self.step5), "--out", str(self.root / "x"),
                         "--cache", str(self.step5_cache)])
        self.assertEqual(hashlib.sha256(self.step5_cache.read_bytes()).hexdigest(), self.step5_hash)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit + mock end-to-end tests for Step 6a (check_logprobs.py).

All numbers produced against the mock server are FAKE (deterministic hashes).
They are NOT experimental results.
Run: python3 test_step6a.py
"""
from __future__ import annotations

import hashlib
import io
import json
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
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
STEP3 = HERE.parent / "step3"
sys.path.insert(0, str(HERE))
import check_logprobs as cl  # noqa: E402

SECRET = "sk-testSECRET0123456789step6a"


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_mock(data_path, counter_path, port, mode):
    cmd = [
        sys.executable, str(STEP3 / "test_mock_server.py"),
        "--host", "127.0.0.1", "--port", str(port),
        "--answers-from", str(data_path),
        "--counter", str(counter_path),
        "--top-logprobs-mode", mode,
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.time() + 8
    while time.time() < deadline:
        if proc.poll() is not None:
            out, err = proc.communicate()
            raise RuntimeError((out, err))
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.4) as r:
                if r.status == 200:
                    body = json.loads(r.read().decode("utf-8"))
                    if body.get("top_logprobs_mode") != mode:
                        proc.kill()
                        raise RuntimeError(f"mock mode mismatch: {body}")
                    return proc, f"http://127.0.0.1:{port}/v1"
        except RuntimeError:
            raise
        except Exception:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("mock server did not start")


def _stop(proc):
    if proc is None:
        return
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    for stream in (proc.stdout, proc.stderr):
        if stream is not None:
            stream.close()


def _counter(path):
    if not os.path.isfile(path):
        return 0, []
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    return int(d.get("n_requests") or 0), d.get("requests") or []


def make_synth_data(n=30):
    """Official-format HotpotQA-like items with unique questions and answers.

    Unique answers make the mock completions differ so a healthy logprob
    mode can produce spread in per-question means. Not a real dataset.
    """
    data = []
    for i in range(n):
        title_a = f"Author{i:03d}"
        title_b = f"Publisher{i:03d}"
        title_c = f"City{i:03d}"
        ans = f"Author{i:03d} Smith"
        q = f"Who wrote book number {i} in the synthetic series?"
        data.append({
            "_id": f"synth-{i:03d}",
            "question": q,
            "answer": ans,
            "type": "bridge",
            "level": "easy",
            "supporting_facts": [[title_a, 0], [title_b, 0]],
            "context": [
                [title_a, [f"{ans} wrote book number {i} in the synthetic series."]],
                [title_b, [f"Book number {i} was issued by {title_b}."]],
                [title_c, [f"The author once lived in {title_c}."]],
                [f"Distractor{i:03d}X", [f"Unrelated fact X for item {i}."]],
                [f"Distractor{i:03d}Y", [f"Unrelated fact Y for item {i}."]],
            ],
        })
    return data


def _default_args(**kwargs):
    d = dict(
        max_zero_chosen_frac=cl.DEFAULT_MAX_ZERO_CHOSEN_FRAC,
        max_placeholder_alt_frac=cl.DEFAULT_MAX_PLACEHOLDER_ALT_FRAC,
        placeholder_threshold=cl.DEFAULT_PLACEHOLDER_THRESHOLD,
        min_distinct_values=cl.DEFAULT_MIN_DISTINCT,
    )
    d.update(kwargs)
    return SimpleNamespace(**d)


class TestCriteriaUnit(unittest.TestCase):
    def test_defaults_are_the_pre_registered_values(self):
        self.assertEqual(cl.DEFAULT_MAX_ZERO_CHOSEN_FRAC, 0.50)
        self.assertEqual(cl.DEFAULT_MAX_PLACEHOLDER_ALT_FRAC, 0.05)
        self.assertEqual(cl.DEFAULT_PLACEHOLDER_THRESHOLD, -9000.0)
        self.assertEqual(cl.DEFAULT_MIN_DISTINCT, 10)
        self.assertEqual(cl.CACHE_NAME, "cache_logprob_check.jsonl")
        self.assertNotEqual(cl.CACHE_NAME, "cache.jsonl")

    def test_pass_on_healthy_synthetic_stats(self):
        means = [-0.10 * (i + 1) for i in range(30)]
        margins = [0.20 + 0.01 * i for i in range(30)]
        stats = {
            "frac_zero_span": 0.02,
            "frac_placeholder_alts": 0.0,
            "mean_lp_dist": cl.describe_distribution(means),
            "mean_margin_dist": cl.describe_distribution(margins),
        }
        verdict, failed, res = cl.evaluate_criteria(stats, _default_args(), 30, 30)
        self.assertEqual(verdict, "PASS")
        self.assertEqual(failed, [])
        self.assertTrue(res["1_zero_chosen_frac"]["passed"])
        self.assertTrue(res["2_placeholder_alt_frac"]["passed"])
        self.assertTrue(res["3_mean_chosen_logprob_spread"]["passed"])
        self.assertTrue(res["4_mean_margin_spread"]["passed"])
        self.assertGreaterEqual(res["3_mean_chosen_logprob_spread"]["n_distinct"], 10)
        self.assertGreater(res["3_mean_chosen_logprob_spread"]["variance"], 0)

    def test_fail_all_zero_chosen_and_collapsed_means(self):
        # DeepSeek-t0 style: every chosen logprob 0, means identical
        stats = {
            "frac_zero_span": 1.0,
            "frac_placeholder_alts": 0.0,
            "mean_lp_dist": cl.describe_distribution([0.0] * 30),
            "mean_margin_dist": cl.describe_distribution([2.0 + 0.01 * i for i in range(30)]),
        }
        verdict, failed, res = cl.evaluate_criteria(stats, _default_args(), 30, 30)
        self.assertEqual(verdict, "FAIL")
        self.assertIn("zero_chosen_frac", failed)
        self.assertIn("mean_chosen_logprob_spread", failed)
        self.assertNotIn("placeholder_alt_frac", failed)
        self.assertNotIn("mean_margin_spread", failed)
        self.assertFalse(res["1_zero_chosen_frac"]["passed"])
        self.assertFalse(res["3_mean_chosen_logprob_spread"]["passed"])
        self.assertEqual(res["3_mean_chosen_logprob_spread"]["n_distinct"], 1)
        self.assertEqual(res["3_mean_chosen_logprob_spread"]["variance"], 0.0)

    def test_fail_placeholder_and_collapsed_margin(self):
        # Step 5b style: alternatives are -9999, margin collapses to 9999
        means = [-0.10 * (i + 1) for i in range(30)]
        stats = {
            "frac_zero_span": 0.0,
            "frac_placeholder_alts": 0.9,
            "mean_lp_dist": cl.describe_distribution(means),
            "mean_margin_dist": cl.describe_distribution([9999.0] * 30),
        }
        verdict, failed, _ = cl.evaluate_criteria(stats, _default_args(), 30, 30)
        self.assertEqual(verdict, "FAIL")
        self.assertEqual(failed, ["placeholder_alt_frac", "mean_margin_spread"])

    def test_placeholder_under_is_strict(self):
        means = [-0.10 * (i + 1) for i in range(30)]
        margins = [0.20 + 0.01 * i for i in range(30)]
        stats = {
            "frac_zero_span": 0.0,
            "frac_placeholder_alts": 0.05,  # equal to the cap is not "under"
            "mean_lp_dist": cl.describe_distribution(means),
            "mean_margin_dist": cl.describe_distribution(margins),
        }
        verdict, failed, _ = cl.evaluate_criteria(stats, _default_args(), 30, 30)
        self.assertEqual(verdict, "FAIL")
        self.assertEqual(failed, ["placeholder_alt_frac"])

    def test_zero_frac_at_most_is_inclusive(self):
        means = [-0.10 * (i + 1) for i in range(30)]
        margins = [0.20 + 0.01 * i for i in range(30)]
        stats = {
            "frac_zero_span": 0.50,
            "frac_placeholder_alts": 0.0,
            "mean_lp_dist": cl.describe_distribution(means),
            "mean_margin_dist": cl.describe_distribution(margins),
        }
        verdict, failed, _ = cl.evaluate_criteria(stats, _default_args(), 30, 30)
        self.assertEqual(verdict, "PASS")
        self.assertEqual(failed, [])

    def test_incomplete_is_fail_even_if_other_numbers_look_fine(self):
        means = [-0.10 * (i + 1) for i in range(20)]
        margins = [0.20 + 0.01 * i for i in range(20)]
        stats = {
            "frac_zero_span": 0.0,
            "frac_placeholder_alts": 0.0,
            "mean_lp_dist": cl.describe_distribution(means),
            "mean_margin_dist": cl.describe_distribution(margins),
        }
        verdict, failed, res = cl.evaluate_criteria(stats, _default_args(), 30, 20)
        self.assertEqual(verdict, "FAIL")
        self.assertIn("incomplete", failed)
        # Other criteria are also marked failed because the run is incomplete.
        self.assertFalse(res["0_complete"]["passed"])
        self.assertFalse(res["1_zero_chosen_frac"]["passed"])

    def test_cli_override_changes_verdict(self):
        means = [-0.1, -0.2, -0.3]  # only 3 distinct
        margins = [1.0, 2.0, 3.0]
        stats = {
            "frac_zero_span": 0.0,
            "frac_placeholder_alts": 0.0,
            "mean_lp_dist": cl.describe_distribution(means),
            "mean_margin_dist": cl.describe_distribution(margins),
        }
        v1, f1, _ = cl.evaluate_criteria(stats, _default_args(), 3, 3)
        self.assertEqual(v1, "FAIL")
        self.assertIn("mean_chosen_logprob_spread", f1)
        v2, f2, _ = cl.evaluate_criteria(
            stats, _default_args(min_distinct_values=3), 3, 3,
        )
        self.assertEqual(v2, "PASS")
        self.assertEqual(f2, [])

    def test_describe_distribution_empty(self):
        d = cl.describe_distribution([])
        self.assertEqual(d["n"], 0)
        self.assertEqual(d["n_distinct"], 0)
        self.assertIsNone(d["variance"])

    def test_is_placeholder(self):
        self.assertTrue(cl.is_placeholder(-9999.0, -9000.0))
        self.assertTrue(cl.is_placeholder(-9000.0, -9000.0))
        self.assertFalse(cl.is_placeholder(-8999.0, -9000.0))
        self.assertFalse(cl.is_placeholder(None, -9000.0))

    def test_cache_isolation_guard(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):
                with redirect_stderr(io.StringIO()):
                    cl.assert_cache_isolated(os.path.join(d, "cache.jsonl"))
            cl.assert_cache_isolated(os.path.join(d, cl.CACHE_NAME))


class TestEndToEndMock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="step6a_mock_")
        cls.root = Path(cls.tmp.name)
        cls.data = make_synth_data(30)
        cls.data_path = cls.root / "tune_synth.json"
        cls.data_path.write_text(json.dumps(cls.data, ensure_ascii=False), encoding="utf-8")
        # extra questions so --offset can be tested
        extra = make_synth_data(5)
        for i, ex in enumerate(extra):
            ex["_id"] = f"extra-{i:03d}"
            ex["question"] = f"Offset-only question {i}?"
            ex["answer"] = f"OffsetAnswer{i:03d}"
            ex["context"][0][0] = f"OffsetAuthor{i:03d}"
            ex["context"][0][1] = [f"OffsetAnswer{i:03d} wrote the offset book {i}."]
        cls.data_off = cls.data + extra
        cls.data_off_path = cls.root / "tune_synth_off.json"
        cls.data_off_path.write_text(json.dumps(cls.data_off, ensure_ascii=False), encoding="utf-8")
        os.environ["VLLM_API_KEY"] = SECRET

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _run(self, out, url, data_path=None, extra=()):
        argv = [
            "--data", str(data_path or self.data_path),
            "--base-url", url,
            "--model", "mock-qa",
            "--key-env", "VLLM_API_KEY",
            "--n", "30",
            "--out", str(out),
            *extra,
        ]
        buf, err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf), redirect_stderr(err):
            rc = cl.main(argv)
        self.assertEqual(rc, 0, msg=err.getvalue() + "\n" + buf.getvalue())
        return buf.getvalue(), err.getvalue()

    def test_vllm_healthy_is_pass(self):
        counter = self.root / "counter_healthy.json"
        proc, url = _start_mock(self.data_path, counter, _free_port(), "vllm_healthy")
        try:
            out = self.root / "out_healthy"
            n0, _ = _counter(counter)
            stdout, stderr = self._run(out, url)
            n1, reqs = _counter(counter)
            self.assertEqual(n1 - n0, 30)
            for r in reqs[n0:]:
                self.assertTrue(r["logprobs"])
                self.assertEqual(r["top_logprobs"], 5)
                self.assertEqual(r["temperature"], 0.0)
            combined = stdout + stderr
            self.assertNotIn(SECRET, combined)
            self.assertIn("VLLM_API_KEY=set", stdout)
            self.assertIn("VERDICT: PASS", stdout)
            self.assertIn("degeneracy only", stdout)
            self.assertNotIn("AUC", stdout.replace("No AUC is computed.", "").replace("No AUC is computed.", ""))

            s = json.loads((out / "logprob_check.json").read_text(encoding="utf-8"))
            self.assertEqual(s["verdict"], "PASS")
            self.assertEqual(s["failed_criteria"], [])
            self.assertEqual(s["n_scheduled"], 30)
            self.assertEqual(s["n_usable_questions"], 30)
            self.assertEqual(s["calls"]["new_api_calls_this_run"], 30)
            self.assertEqual(s["branch"], "A")
            self.assertEqual(s["k"], 2)
            tok = s["tokens"]
            self.assertGreater(tok["n_output_tokens"], 0)
            self.assertLessEqual(tok["frac_chosen_lp_exactly_zero_span"] or 0.0, 0.50)
            self.assertEqual(tok["n_placeholder_alternatives"], 0)
            self.assertGreaterEqual(s["per_question_distributions"]["mean_chosen_logprob_span"]["n_distinct"], 10)
            self.assertGreater(s["per_question_distributions"]["mean_chosen_logprob_span"]["variance"], 0)
            self.assertGreaterEqual(s["per_question_distributions"]["mean_margin_span"]["n_distinct"], 10)
            self.assertGreater(s["per_question_distributions"]["mean_margin_span"]["variance"], 0)
            # Healthy fixture: chosen logprob equals the top-1 alternative
            self.assertEqual(tok["frac_chosen_lp_equals_top1_alt_lp"], 1.0)
            self.assertIn("not used in the PASS/FAIL verdict", s["answer_quality_info_only"]["note"])
            self.assertIsNotNone(s["answer_quality_info_only"]["mean_F1"])
            self.assertEqual(
                s["criteria_defaults_pre_registered"]["max_zero_chosen_frac"], 0.50,
            )

            cache_path = out / cl.CACHE_NAME
            self.assertTrue(cache_path.is_file())
            self.assertNotEqual(cache_path.name, "cache.jsonl")
            self.assertFalse((out / "cache.jsonl").exists())
            lines = cache_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 30)
            rec = json.loads(lines[0])
            self.assertEqual(rec["branch"], "A")
            self.assertEqual(rec["top_logprobs"], 5)
            self.assertTrue(rec["tokens"] and len(rec["tokens"][0]["top"]) == 5)
            self.assertNotIn(SECRET, cache_path.read_text(encoding="utf-8"))

            csv_path = out / "logprob_check_tokens.csv"
            self.assertTrue(csv_path.is_file())
            csv_text = csv_path.read_text(encoding="utf-8-sig")
            self.assertIn("chosen_logprob", csv_text)
            self.assertGreaterEqual(csv_text.count("\n"), 30)

            # resume: second run makes no new calls, same verdict
            n2, _ = _counter(counter)
            self._run(out, url)
            self.assertEqual(_counter(counter)[0], n2)
            s2 = json.loads((out / "logprob_check.json").read_text(encoding="utf-8"))
            self.assertEqual(s2["verdict"], "PASS")
            self.assertEqual(s2["calls"]["cache_hits"], 30)
            self.assertEqual(s2["calls"]["new_api_calls_this_run"], 0)
            self.assertEqual(
                s2["per_question_distributions"], s["per_question_distributions"],
            )

            # analyze-only
            self._run(out, url, extra=("--analyze-only",))
            self.assertEqual(_counter(counter)[0], n2)
            s3 = json.loads((out / "logprob_check.json").read_text(encoding="utf-8"))
            self.assertTrue(s3["analyze_only"])
            self.assertEqual(s3["verdict"], "PASS")
        finally:
            _stop(proc)

    def test_deepseek_t0_is_fail(self):
        counter = self.root / "counter_ds.json"
        proc, url = _start_mock(self.data_path, counter, _free_port(), "deepseek_t0")
        try:
            out = self.root / "out_ds"
            stdout, stderr = self._run(out, url)
            self.assertNotIn(SECRET, stdout + stderr)
            self.assertIn("VERDICT: FAIL", stdout)
            s = json.loads((out / "logprob_check.json").read_text(encoding="utf-8"))
            self.assertEqual(s["verdict"], "FAIL")
            self.assertIn("zero_chosen_frac", s["failed_criteria"])
            self.assertIn("mean_chosen_logprob_spread", s["failed_criteria"])
            self.assertEqual(s["n_usable_questions"], 30)
            self.assertEqual(s["tokens"]["frac_chosen_lp_exactly_zero_span"], 1.0)
            self.assertEqual(
                s["per_question_distributions"]["mean_chosen_logprob_span"]["n_distinct"], 1,
            )
            self.assertEqual(
                s["per_question_distributions"]["mean_chosen_logprob_span"]["variance"], 0.0,
            )
            # The current deepseek_t0 fixture does not use -9999 placeholders
            self.assertEqual(s["tokens"]["n_placeholder_alternatives"], 0)
            self.assertNotIn("placeholder_alt_frac", s["failed_criteria"])
        finally:
            _stop(proc)

    def test_refuses_cache_jsonl_name(self):
        counter = self.root / "counter_refuse.json"
        proc, url = _start_mock(self.data_path, counter, _free_port(), "vllm_healthy")
        try:
            with self.assertRaises(SystemExit):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    cl.main([
                        "--data", str(self.data_path), "--base-url", url,
                        "--model", "mock-qa", "--key-env", "VLLM_API_KEY",
                        "--n", "30", "--out", str(self.root / "out_bad"),
                        "--cache", str(self.root / "cache.jsonl"),
                    ])
        finally:
            _stop(proc)

    def test_offset_selects_later_questions(self):
        counter = self.root / "counter_off.json"
        proc, url = _start_mock(self.data_off_path, counter, _free_port(), "vllm_healthy")
        try:
            out = self.root / "out_off"
            # 5 extra questions only — use lowered distinct-values to test offset, not criteria
            stdout, _ = self._run(
                out, url, data_path=self.data_off_path,
                extra=("--offset", "30", "--n", "5", "--min-distinct-values", "2"),
            )
            s = json.loads((out / "logprob_check.json").read_text(encoding="utf-8"))
            self.assertEqual(s["n_offset"], 30)
            self.assertEqual(s["n_scheduled"], 5)
            self.assertEqual(s["n_usable_questions"], 5)
            ids = [q["_id"] for q in s["questions"]]
            self.assertEqual(ids, [f"extra-{i:03d}" for i in range(5)])
            self.assertNotIn("synth-000", ids)
        finally:
            _stop(proc)

    def test_analyze_only_empty_cache_is_incomplete_fail(self):
        out = self.root / "out_empty"
        buf, err = io.StringIO(), io.StringIO()
        # no server needed
        with redirect_stdout(buf), redirect_stderr(err):
            rc = cl.main([
                "--data", str(self.data_path),
                "--base-url", "http://127.0.0.1:9",
                "--model", "mock-qa",
                "--n", "30",
                "--out", str(out),
                "--analyze-only",
            ])
        self.assertEqual(rc, 0, msg=err.getvalue())
        s = json.loads((out / "logprob_check.json").read_text(encoding="utf-8"))
        self.assertEqual(s["verdict"], "FAIL")
        self.assertIn("incomplete", s["failed_criteria"])
        self.assertEqual(s["calls"]["missing_not_called"], 30)
        self.assertEqual(s["n_usable_questions"], 0)
        self.assertNotIn(SECRET, buf.getvalue() + err.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit and mock end-to-end tests for Step 5.

All numbers produced with --nli-backend mock or the local mock chat server
are FAKE and must not be treated as experimental results.
"""
from __future__ import annotations

import csv
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HERE = Path(__file__).resolve().parent
STEP3 = HERE.parent / "step3"
sys.path.insert(0, str(HERE))

import run_pilot as rp  # noqa: E402


# ---------------------------------------------------------------------------
# Known 10-question fixture (unit tests only; not experiment results)
# ---------------------------------------------------------------------------
# F1_A: 0.0, 0.5, 1.0, 0.8, 0.4, 0.6, 0.0, 1.0, 0.2, 0.5
# F1_B: 0.5, 0.5, 1.0, 0.9, 0.3, 0.6, 0.0, 0.8, 0.8, 0.5
# improved (B>A): indices 0, 3, 8          -> 3
# tie            : indices 1, 2, 5, 6, 9   -> 5
# degraded (B<A) : indices 4, 7            -> 2
# Oracle chooses A on tie and on degraded, so
# Oracle-A = [0.5, 0, 0, 0.1, 0, 0, 0, 0, 0.6, 0]
# mean = 1.2 / 10 = 0.12
F1_A_10 = [0.0, 0.5, 1.0, 0.8, 0.4, 0.6, 0.0, 1.0, 0.2, 0.5]
F1_B_10 = [0.5, 0.5, 1.0, 0.9, 0.3, 0.6, 0.0, 0.8, 0.8, 0.5]
ORACLE_MINUS_A_10 = [0.5, 0.0, 0.0, 0.1, 0.0, 0.0, 0.0, 0.0, 0.6, 0.0]


def classify_lists(f1_a, f1_b, eps=0.0):
    n_imp = n_tie = n_deg = 0
    deltas = []
    for a, b in zip(f1_a, f1_b):
        klass = rp.classify_delta(b - a, eps)
        branch, of1 = rp.oracle_choice(a, b, eps)
        if klass == "improved":
            n_imp += 1
        elif klass == "tie":
            n_tie += 1
        else:
            n_deg += 1
        deltas.append(of1 - a)
        if klass == "tie":
            assert branch == "A"
        if klass == "degraded":
            assert branch == "A"
        if klass == "improved":
            assert branch == "B"
    return n_imp, n_tie, n_deg, deltas


class TestClassificationAndOracle(unittest.TestCase):
    def test_eps0_known_counts(self):
        n_imp, n_tie, n_deg, deltas = classify_lists(F1_A_10, F1_B_10, 0.0)
        self.assertEqual((n_imp, n_tie, n_deg), (3, 5, 2))
        self.assertEqual(len(deltas), len(ORACLE_MINUS_A_10))
        for got, exp in zip(deltas, ORACLE_MINUS_A_10):
            self.assertAlmostEqual(got, exp)
        self.assertAlmostEqual(sum(deltas) / 10, 0.12)

    def test_oracle_chooses_a_on_tie(self):
        branch, of1 = rp.oracle_choice(0.5, 0.5, 0.0)
        self.assertEqual(branch, "A")
        self.assertEqual(of1, 0.5)
        self.assertEqual(rp.classify_delta(0.0, 0.0), "tie")

    def test_eps0_any_positive_delta_is_improved(self):
        self.assertEqual(rp.classify_delta(1e-12, 0.0), "improved")
        self.assertEqual(rp.classify_delta(-1e-12, 0.0), "degraded")
        self.assertEqual(rp.classify_delta(0.0, 0.0), "tie")


class TestBootstrap(unittest.TestCase):
    def test_point_equals_mean_and_ci_contains_point(self):
        point, lo, hi = rp.paired_bootstrap_mean_ci(ORACLE_MINUS_A_10, n_boot=10000, seed=42)
        self.assertAlmostEqual(point, 0.12)
        self.assertLessEqual(lo, point)
        self.assertGreaterEqual(hi, point)
        # Reproducible with the same seed
        point2, lo2, hi2 = rp.paired_bootstrap_mean_ci(ORACLE_MINUS_A_10, n_boot=10000, seed=42)
        self.assertEqual((point, lo, hi), (point2, lo2, hi2))

    def test_empty(self):
        point, lo, hi = rp.paired_bootstrap_mean_ci([], n_boot=100, seed=42)
        self.assertTrue(all(x != x for x in (point, lo, hi)))  # all NaN


class TestGoNoGo(unittest.TestCase):
    def test_go_fixture(self):
        # n=100, improved=15, degraded=5, point=0.08, ci_lo=0.02
        g = rp.go_nogo(100, 15, 5, 0.08, 0.02)
        self.assertTrue(g["overall_pass"])
        self.assertEqual(g["overall"], "GO")
        self.assertTrue(all(c["pass"] for c in g["criteria"]))

    def test_nogo_headroom_point(self):
        g = rp.go_nogo(100, 15, 5, 0.04, 0.01)
        self.assertFalse(g["overall_pass"])
        self.assertEqual(g["overall"], "NO-GO")
        by = {c["id"]: c for c in g["criteria"]}
        self.assertFalse(by["headroom_point"]["pass"])
        self.assertTrue(by["headroom_ci_lo"]["pass"])
        self.assertTrue(by["improved_share"]["pass"])
        self.assertTrue(by["degraded_ratio"]["pass"])

    def test_nogo_ci_lo(self):
        g = rp.go_nogo(100, 15, 5, 0.06, -0.01)
        self.assertFalse(g["overall_pass"])
        by = {c["id"]: c for c in g["criteria"]}
        self.assertTrue(by["headroom_point"]["pass"])
        self.assertFalse(by["headroom_ci_lo"]["pass"])

    def test_nogo_improved_share(self):
        g = rp.go_nogo(100, 9, 2, 0.08, 0.02)
        self.assertFalse(g["overall_pass"])
        by = {c["id"]: c for c in g["criteria"]}
        self.assertFalse(by["improved_share"]["pass"])

    def test_nogo_degraded_ratio(self):
        g = rp.go_nogo(100, 10, 6, 0.08, 0.02)
        self.assertFalse(g["overall_pass"])
        by = {c["id"]: c for c in g["criteria"]}
        self.assertFalse(by["degraded_ratio"]["pass"])

    def test_zero_improved_with_degraded(self):
        g = rp.go_nogo(100, 0, 3, 0.0, -0.01)
        self.assertFalse(g["overall_pass"])
        by = {c["id"]: c for c in g["criteria"]}
        self.assertFalse(by["degraded_ratio"]["pass"])
        self.assertFalse(by["improved_share"]["pass"])


class TestLabelMapping(unittest.TestCase):
    def test_does_not_assume_index_order(self):
        # Index 2 is entailment, not index 0.
        logits = [0.1, 0.2, 5.0]
        id2label = {0: "contradiction", 1: "NEUTRAL", 2: "Entailment"}
        probs, argmax, unknown = rp.probs_from_logits(logits, id2label)
        self.assertEqual(argmax, "entailment")
        self.assertEqual(unknown, [])
        self.assertGreater(probs["entailment"], probs["neutral"])
        self.assertGreater(probs["entailment"], probs["contradiction"])
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=6)

    def test_string_keys(self):
        probs, argmax, _ = rp.probs_from_logits(
            [9.0, 0.0, 0.0],
            {"0": "entailment", "1": "neutral", "2": "contradiction"},
        )
        self.assertEqual(argmax, "entailment")
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=6)


class TestHypothesisAndPremise(unittest.TestCase):
    def test_hypothesis_template(self):
        h = rp.build_hypothesis("Who wrote X?", "Ada Lovelace")
        self.assertEqual(h, 'The answer to the question "Who wrote X?" is: Ada Lovelace.')
        self.assertEqual(rp.HYPOTHESIS_TEMPLATE, 'The answer to the question "{question}" is: {answer}.')

    def test_fallback_when_no_usable_citations(self):
        ex = {
            "context": [
                ["TitleA", ["sent a"]],
                ["TitleB", ["sent b"]],
                ["TitleC", ["sent c"]],
            ]
        }
        info = rp.build_premise(ex, [], [1, 0])
        self.assertTrue(info["used_fallback"])
        self.assertEqual(info["titles"], ["TitleB", "TitleA"])
        self.assertEqual(info["source_indices"], [1, 0])
        self.assertIn("TitleB", info["premise"])

    def test_citation_order_and_dedup(self):
        ex = {
            "context": [
                ["TitleA", ["sent a"]],
                ["TitleB", ["sent b"]],
                ["TitleC", ["sent c"]],
            ]
        }
        info = rp.build_premise(ex, [2, 1, 2, 9], [0, 2])
        # citation 2 -> index 2 (TitleC), citation 1 -> index 0 (TitleA); 9 dropped
        self.assertFalse(info["used_fallback"])
        self.assertEqual(info["titles"], ["TitleC", "TitleA"])


class TestTruncationMock(unittest.TestCase):
    def test_mock_truncation_counter(self):
        short = rp.mock_nli_score("short premise", "short hyp", max_length=512)
        self.assertFalse(short["truncated"])
        long_prem = " ".join(["word"] * 600)
        long = rp.mock_nli_score(long_prem, "hyp tokens here", max_length=512)
        self.assertTrue(long["truncated"])
        self.assertGreater(long["n_tokens"], 512)
        # Fake scores, but still a valid probability simplex
        self.assertAlmostEqual(sum(long["probs"].values()), 1.0, places=6)

    def test_official_sp_f1_null_without_sentence_indices(self):
        ex = {"supporting_facts": [["T", 0]], "context": [["T", ["s"]]]}
        self.assertIsNone(rp.branch_official_sp_f1(ex, [1, 2]))
        val = rp.branch_official_sp_f1(ex, [("T", 0)])
        self.assertEqual(val, 1.0)


class TestAuditSample(unittest.TestCase):
    def _row(self, qid, **kwargs):
        base = {
            "_id": qid,
            "question": f"Q {qid}",
            "gold_answer": "gold",
            "gold_titles": ["G1", "G2"],
            "answer_A": "a",
            "answer_B": "b",
            "F1_A": 1.0,
            "F1_B": 1.0,
            "EM_A": 1.0,
            "EM_B": 1.0,
            "cite_gold_hits_A": 1,
            "cite_gold_hits_B": 1,
            "citation_titles_A": ["G1"],
            "citation_titles_B": ["G1"],
            "retrieved_titles_A": ["G1", "X"],
            "retrieved_titles_B": ["G1", "G2"],
            "nli_premise_titles_A": ["G1"],
            "nli_premise_titles_B": ["G1", "G2"],
            "nli_argmax_A": "entailment",
            "nli_argmax_B": "entailment",
            "nli_truncated_A": False,
            "nli_truncated_B": False,
            "nli_entailment_A": 0.8,
            "nli_entailment_B": 0.8,
        }
        base.update(kwargs)
        return base

    def test_types_and_shortfall(self):
        rows = []
        # 3 false entailment on A (wrong answer, NLI says entailment)
        for i in range(3):
            rows.append(self._row(
                f"fe{i}",
                F1_A=0.0, EM_A=0.0, cite_gold_hits_A=0,
                citation_titles_A=["X"], nli_argmax_A="entailment",
                # B is a clean entailment with a good answer — not an error type
                F1_B=1.0, EM_B=1.0, cite_gold_hits_B=2,
                citation_titles_B=["G1", "G2"], nli_argmax_B="entailment",
                nli_premise_titles_B=["G1", "G2"],
            ))
        # 8 false non-entailment on B
        for i in range(8):
            rows.append(self._row(
                f"fn{i}",
                nli_argmax_B="contradiction",
                F1_B=1.0, EM_B=1.0, cite_gold_hits_B=1,
            ))
        # 2 truncated on A, not already (a) or (b): good answer, gold in premise, but truncated
        # and NLI says entailment (agrees with coverage) so only (c) via truncation
        for i in range(2):
            rows.append(self._row(
                f"tr{i}",
                nli_truncated_A=True,
                nli_argmax_A="entailment",
                F1_A=1.0, EM_A=1.0, cite_gold_hits_A=1,
                nli_premise_titles_A=["G1"],
            ))

        selected, meta = rp.sample_audit(rows, n_target=20, seed=42)
        self.assertIn("false_entailment", meta["shortfalls"])
        self.assertEqual(meta["shortfalls"]["false_entailment"]["available"], 3)
        self.assertEqual(meta["shortfalls"]["false_entailment"]["taken"], 3)
        self.assertEqual(meta["pool_sizes"]["false_non_entailment"], 8)
        # quota for false_non_entailment is 7
        taken_fn = [s for s in selected if s["error_type"] == "false_non_entailment"]
        self.assertEqual(len(taken_fn), 7)
        taken_tr = [s for s in selected if s["error_type"] == "truncated_or_disagreement"]
        self.assertEqual(len(taken_tr), 2)
        self.assertEqual(meta["n_selected"], 3 + 7 + 2)
        # human_label is not set here; CSV writer leaves it empty
        self.assertTrue(any(s["branch"] == "B" for s in selected))
        self.assertTrue(any(s["branch"] == "A" for s in selected))

    def test_empty_does_not_crash(self):
        selected, meta = rp.sample_audit([], n_target=20, seed=42)
        self.assertEqual(selected, [])
        self.assertEqual(meta["n_selected"], 0)
        self.assertEqual(len(meta["shortfalls"]), 3)


# ---------------------------------------------------------------------------
# End-to-end mock (NOT experimental results)
# ---------------------------------------------------------------------------
def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_mock_server(data_path, counter_path, port):
    cmd = [
        sys.executable,
        str(STEP3 / "test_mock_server.py"),
        "--host", "127.0.0.1",
        "--port", str(port),
        "--answers-from", str(data_path),
        "--counter", str(counter_path),
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    url = f"http://127.0.0.1:{port}/v1"
    deadline = time.time() + 8
    import urllib.request
    last_err = None
    while time.time() < deadline:
        if proc.poll() is not None:
            out, err = proc.communicate()
            raise RuntimeError(f"mock server exited: {err or out}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.4) as r:
                if r.status == 200:
                    return proc, url
        except Exception as exc:
            last_err = exc
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError(f"mock server did not start: {last_err}")


def _read_counter(path):
    if not os.path.isfile(path):
        return 0
    with open(path, "r", encoding="utf-8") as f:
        return int(json.load(f).get("n_requests") or 0)


def _make_long_example():
    long_sents = [" ".join(["lorem"] * 80) for _ in range(8)]
    return {
        "_id": "synthetic-truncation-001",
        "question": "What is the synthetic placeholder answer used for truncation tests?",
        "answer": "PlaceholderAnswer",
        "type": "bridge",
        "level": "hard",
        "supporting_facts": [["SynthGold", 0], ["SynthOther", 0]],
        "context": [
            ["SynthGold", long_sents],
            ["SynthOther", long_sents],
            ["SynthDistract1", long_sents],
            ["SynthDistract2", long_sents],
            ["SynthDistract3", ["short"]],
        ],
        "_comment": "SYNTHETIC example for mock truncation tests only; not a HotpotQA item.",
    }


class TestEndToEndMock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="step5_mock_")
        cls.root = Path(cls.tmp.name)
        mini = json.loads((HERE / "testdata" / "mini_pilot.json").read_text(encoding="utf-8"))
        # 4 real pilot questions + 1 clearly marked synthetic item (truncation path)
        cls.data = mini + [_make_long_example()]
        cls.data_path = cls.root / "mini_plus_synth.json"
        cls.data_path.write_text(json.dumps(cls.data, ensure_ascii=False), encoding="utf-8")
        cls.counter = cls.root / "counter.json"
        cls.port = _free_port()
        cls.proc, cls.url = _start_mock_server(cls.data_path, cls.counter, cls.port)
        os.environ["LOCAL_API_KEY"] = "EMPTY"

    @classmethod
    def tearDownClass(cls):
        if cls.proc and cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
        cls.tmp.cleanup()

    def _common(self, out, extra):
        argv = [
            "--data", str(self.data_path),
            "--preset", "custom",
            "--base-url", self.url,
            "--model", "mock-qa",
            "--key-env", "LOCAL_API_KEY",
            "--k", "2",
            "--m", "1",
            "--out", str(out),
            "--nli-backend", "mock",
        ] + extra
        buf = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(err):
            rc = rp.main(argv)
        self.assertEqual(rc, 0, msg=err.getvalue() + buf.getvalue())
        return buf.getvalue(), err.getvalue()

    def test_cache_reuse_skip_nli_then_nli_only_and_truncation(self):
        out1 = self.root / "run_n2"
        out2 = self.root / "run_n5"
        before = _read_counter(self.counter)
        # First two questions, answers only
        out, err = self._common(out1, ["--n", "2", "--skip-nli"])
        after_first = _read_counter(self.counter)
        self.assertEqual(after_first - before, 4, msg="expected 2 questions x 2 branches")
        self.assertTrue((out1 / "cache.jsonl").is_file())
        summ1 = json.loads((out1 / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summ1["api_calls"], 4)
        self.assertEqual(summ1["cache_hits"], 0)
        self.assertFalse(summ1["nli_ran"])
        self.assertIn("NLI was not run", out)

        # Five questions, reuse the first four branch answers via --answer-cache
        out, err = self._common(
            out2,
            [
                "--n", "5",
                "--skip-nli",
                "--answer-cache", str(out1 / "cache.jsonl"),
            ],
        )
        after_second = _read_counter(self.counter)
        self.assertEqual(after_second - after_first, 6, msg="only 3 new questions x 2 should be called")
        summ2 = json.loads((out2 / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summ2["api_calls"], 6)
        self.assertEqual(summ2["cache_hits"], 4)
        self.assertEqual(summ2["n"], 5)
        # Classification with eps=0 is recorded
        with open(out2 / "per_question.csv", encoding="utf-8-sig") as _f:
            pq = list(csv.DictReader(_f))
        self.assertEqual(len(pq), 5)
        self.assertTrue(all(r["delta_class"] in {"improved", "tie", "degraded"} for r in pq))
        # Oracle column present; ties should choose A
        for r in pq:
            if r["delta_class"] == "tie":
                self.assertEqual(r["oracle_branch"], "A")
            if r["delta_class"] == "improved":
                self.assertEqual(r["oracle_branch"], "B")
            if r["delta_class"] == "degraded":
                self.assertEqual(r["oracle_branch"], "A")

        # nli-only should make zero new API calls and write NLI + audit
        out, err = self._common(
            out2,
            ["--n", "5", "--nli-only", "--nli-max-length", "512"],
        )
        after_nli = _read_counter(self.counter)
        self.assertEqual(after_nli, after_second)
        self.assertIn("FAKE", err)
        self.assertIn("must not be reported as experimental results", err)
        summ3 = json.loads((out2 / "summary.json").read_text(encoding="utf-8"))
        self.assertTrue(summ3["nli_ran"])
        self.assertTrue(summ3["nli"]["scores_are_fake"])
        self.assertEqual(summ3["api_calls"], 0)
        self.assertGreaterEqual(summ3["nli"]["n_truncated"], 1)
        # synthetic item should be truncated on at least one branch
        nli_rows = [
            json.loads(line)
            for line in (out2 / "nli_scores.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        synth = [r for r in nli_rows if r["_id"] == "synthetic-truncation-001"]
        self.assertEqual(len(synth), 2)
        self.assertTrue(any(r["truncated"] for r in synth))
        # audit file exists and has human_label header; may be short
        with open(out2 / "audit_sample.csv", encoding="utf-8-sig") as f:
            audit = list(csv.DictReader(f))
        with open(out2 / "audit_sample.csv", encoding="utf-8-sig") as _f:
            self.assertIn("human_label", csv.DictReader(_f).fieldnames)
        for a in audit:
            self.assertEqual(a["human_label"], "")
        self.assertIn("go_nogo", summ3)
        self.assertIn(summ3["go_nogo"]["overall"], {"GO", "NO-GO"})
        self.assertIn("official supporting-fact F1 is sentence-level", summ3["official_sp_f1_note"])
        # Cache was copied into out2
        self.assertTrue((out2 / "cache.jsonl").is_file())
        with open(out2 / "cache.jsonl", encoding="utf-8") as _f:
            n_cache = sum(1 for line in _f if line.strip())
        self.assertEqual(n_cache, 10)  # 5 q x 2

    def test_hf_backend_fails_cleanly_without_transformers(self):
        out = self.root / "run_hf_fail"
        # Reuse answers already written if present; otherwise skip-nli first is heavy.
        # Use nli-only on the previous out if it exists, else a tiny skip+nli attempt.
        src = self.root / "run_n5"
        if not (src / "branches.jsonl").is_file():
            self.skipTest("previous e2e output not present")
        argv = [
            "--data", str(self.data_path),
            "--preset", "custom",
            "--base-url", self.url,
            "--model", "mock-qa",
            "--key-env", "LOCAL_API_KEY",
            "--n", "5",
            "--out", str(src),
            "--nli-only",
            "--nli-backend", "hf",
        ]
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            with self.assertRaises(SystemExit) as cm:
                rp.main(argv)
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("pip install transformers torch", err.getvalue())


class TestCliDefaults(unittest.TestCase):
    def test_locked_defaults(self):
        # argparse requires --data; parse with a dummy path (not opened here)
        args = rp.parse_args(["--data", "pilot.json"])
        self.assertEqual(args.n, 100)
        self.assertEqual(args.k, 2)
        self.assertEqual(args.m, 1)
        self.assertEqual(args.temperature, 0.0)
        self.assertEqual(args.max_tokens, 128)
        self.assertEqual(args.tie_eps, 0.0)
        self.assertEqual(args.out, "step5_pilot")
        self.assertEqual(args.preset, "deepseek")
        self.assertEqual(args.nli_model, rp.DEFAULT_NLI_MODEL)
        self.assertEqual(args.nli_max_length, 512)
        self.assertEqual(args.nli_backend, "hf")
        self.assertEqual(args.min_headroom, 0.05)
        self.assertEqual(args.min_improved_share, 0.10)
        self.assertEqual(args.max_degraded_ratio, 0.5)
        self.assertEqual(args.bootstrap_samples, 10000)
        self.assertEqual(args.bootstrap_seed, 42)


if __name__ == "__main__":
    print(
        "NOTE: any scores from --nli-backend mock or the local mock chat server "
        "are FAKE and are not experimental results.",
        file=sys.stderr,
    )
    unittest.main(verbosity=2)

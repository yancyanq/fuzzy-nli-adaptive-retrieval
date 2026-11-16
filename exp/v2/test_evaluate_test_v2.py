"""Synthetic conformance checks for cache replay and ablations."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import evaluate_test_v2 as ev
import generate_test_v2 as gen
from test_generate_test_v2 import EXAMPLE, ROOT


class EvaluationTest(unittest.TestCase):
    def setUp(self):
        self.lock = gen.load_lock(ROOT / "step4_dev/gates/locked_gates.json")

    def test_no_nli_cannot_use_observed_entailment(self):
        gate = self.lock["gates"]
        for absent in (False, True, None):
            answers = {ev.choose_b("fuzzy_without_nli", gate, "trial", score, absent) for score in (0, .6, 1)}
            self.assertEqual(len(answers), 1)
        self.assertTrue(ev.choose_b("fuzzy_without_nli", gate, "trial", .8, True))
        self.assertFalse(ev.choose_b("fuzzy_without_nli", gate, "trial", .8, False))

    def test_no_bridge_cannot_use_observed_bridge(self):
        gate = self.lock["gates"]
        for entailment in (0, .6, 1):
            answers = {ev.choose_b("fuzzy_without_bridge", gate, "trial", entailment, absent)
                       for absent in (False, True, None)}
            self.assertEqual(len(answers), 1)
        self.assertFalse(ev.bridge_absence({"context": [["One", ["Two is present"]], ["Two", ["Example"]]]}, [0, 1]))
        self.assertTrue(ev.bridge_absence(EXAMPLE, [0, 1]))
        self.assertIsNone(ev.bridge_absence(EXAMPLE, [0]))

    def test_nli_writer_keeps_answer_and_nli_model_identities(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            args = SimpleNamespace(out=path, nli_model="fixture-nli", nli_device="cpu")
            with (path / "answers_test_v2.jsonl").open("w") as out:
                for branch in gen.BRANCHES:
                    gen.append_record(out, {"model": gen.MODEL, "_id": EXAMPLE["_id"], "branch": branch,
                                            "answer": "Alpha", "paragraph_indices": [0], "citations": [1]})
            mocked_result = {"model": "fixture-nli", "probs": {"entailment": .7}}
            with patch.object(ev.pilot, "HFNliScorer") as scorer:
                scorer.return_value.score_many.return_value = [mocked_result, mocked_result]
                ev.score_nli(args, [EXAMPLE])
            scores, expected = ev.branch_cache(args, [EXAMPLE], ("A", "B"), "nli_test_v2.jsonl")
            self.assertEqual(scores.keys(), expected)
            self.assertEqual({row["nli_model"] for row in scores.values()}, {"fixture-nli"})
            self.assertEqual({row["probs"]["entailment"] for row in scores.values()}, {.7})

    def test_official_cache_replay(self):
        ex = EXAMPLE
        first, extra = ev.cm.retrieve_indices(ex, 2, 1)
        scorer = gen.load_official(ROOT / "step5_v2/hotpot_evaluate_v1.py")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            for file, keys, records in (
                ("answers_test_v2.jsonl", gen.BRANCHES, [{"paragraph_indices": first, "answer": "Other", "parse_ok": True},
                 {"paragraph_indices": first + extra, "answer": "Alpha", "parse_ok": True},
                 {"paragraph_indices": [0, 1], "answer": "Alpha", "parse_ok": True}]),
                ("evidence_test_v2.jsonl", gen.BRANCHES, [{"sp": [], "evidence_calls": []},
                 {"sp": ex["supporting_facts"], "evidence_calls": []}, {"sp": [], "evidence_calls": []}]),
                ("nli_test_v2.jsonl", ("A", "B"), [{"probs": {"entailment": .1}, "truncated": False, "used_fallback": False}] * 2),
            ):
                with (path / file).open("w") as out:
                    for branch, record in zip(keys, records):
                        gen.append_record(out, {"model": gen.MODEL, "_id": ex["_id"], "branch": branch, **record})
            ev.replay(SimpleNamespace(out=path), [ex], self.lock, scorer)
            methods = gen.read_json(path / "quality_summary.json")["methods"]
            self.assertEqual(methods["never"]["f1"], 0)
            self.assertEqual(methods["always"]["sp_f1"], 1)
            self.assertEqual(methods["full"]["retrieval_rate"], 0)
            self.assertEqual(methods["oracle"]["selected_labels"]["improved"], 1)
            self.assertEqual(methods["fuzzy"]["gate_recall"], 1)
            self.assertEqual(json.loads((path / "predictions" / "always.json").read_text())["sp"][ex["_id"]],
                             ex["supporting_facts"])


if __name__ == "__main__":
    unittest.main()

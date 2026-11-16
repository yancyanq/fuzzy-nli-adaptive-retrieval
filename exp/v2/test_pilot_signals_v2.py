"""Synthetic tests only. No real pilot data or network calls."""

import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

import analyze_pilot_signals_v2 as check


ROOT = Path(__file__).resolve().parent


def load_mock_server():
    path = ROOT.parent / "step3" / "test_mock_server.py"
    spec = importlib.util.spec_from_file_location("step3_mock_server", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_exports():
    server = load_mock_server()
    pilot, branches, table = [], [], []
    for index in range(100):
        qid = f"synthetic-{index:03d}"
        question = f"Synthetic question {index}?"
        answer = "Synthetic answer"
        body = "It mentioned Target (2001)." if index < 25 or 50 <= index < 75 else "Unrelated text."
        ex = {
            "_id": qid,
            "type": "bridge",
            "question": question,
            "answer": answer,
            "context": [["Source", [body]], ["Target (2001)", ["Some text."]], ["Extra", ["Extra text."]]],
        }
        pilot.append(ex)
        pair = {}
        fake_gold = {question: answer} if 25 <= index < 50 else {}
        with patch.object(server, "GOLD", fake_gold):
            for tag, indices in (("A", [0, 1]), ("B", [0, 1, 2])):
                response = server.completion_body({"messages": check.cm.build_messages(ex, indices)}, qid)
                content = response["choices"][0]["message"]["content"]
                generated = check.cm.parse_response(content)["answer"]
                f1, _, _ = check.cm.f1_score(generated, answer)
                pair[tag] = {"F1": f1, "paragraph_indices": indices}
        label = "improved" if 25 <= index < 50 else "tie"
        e = 0.1 if index < 50 else 0.9
        branches.append({
            "_id": qid, **pair, "r1_indices": [0, 1], "delta_class": label,
            "nli": {"A": {"probs": {"entailment": e}}},
        })
        table.append({
            "_id": qid, "nli_entailment_A": e, "F1_A": pair["A"]["F1"],
            "F1_B": pair["B"]["F1"], "delta_class": label,
        })
    return pilot, branches, table


class PilotSignalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = fake_exports()

    def test_bridge_matches_normalized_complete_title_in_both_directions(self):
        context = [["Source", ["I saw ＣＡＦÉ (2001)."]], ["Café (2001)", ["From SOURCE."]]]
        self.assertEqual(check.bridge_matches(context, [0, 1]), [(0, 1, 0), (1, 0, 0)])

    def test_bridge_rejects_substrings_shorthand_and_cross_sentence_phrases(self):
        context = [["Source", ["Target.", "2001 is next.", "Retarget 2001."]], ["Target (2001)", ["Text."]]]
        self.assertEqual(check.bridge_matches(context, [0, 1]), [])

    def test_unavailable_bridge_has_distinct_representation(self):
        context = [["Source", ["Text."]], ["Target", []]]
        self.assertIsNone(check.bridge_matches(context, [0, 1]))
        self.assertIsNone(check.bridge_matches(context, [0, 0]))
        self.assertIsNone(check.bridge_matches(context, [0, 9]))

    def test_average_tied_ranks_and_undefined_singleton(self):
        self.assertEqual(
            check.midpercentiles({"a": 0, "b": 0, "c": 1, "d": 1}),
            {"a": Fraction(1, 6), "b": Fraction(1, 6), "c": Fraction(5, 6), "d": Fraction(5, 6)},
        )
        self.assertEqual(check.midpercentiles({"a": 0}), {})

    def test_stable_selection_at_boundary(self):
        ids = [f"mock-{i}" for i in range(25)]
        expected = sorted(ids, key=lambda qid: hashlib.sha256(f"42:{qid}".encode()).digest())[:20]
        self.assertEqual(check.select(dict.fromkeys(ids, 1)), expected)
        self.assertEqual(check.select(dict.fromkeys(reversed(ids), 1)), expected)

    def test_inconsistent_labels_fail_and_missing_bridge_falls_back(self):
        pilot, branches, table = [check.records_by_id(rows, "synthetic") for rows in self.data]
        qid = "synthetic-025"
        modified_branches = dict(branches)
        record = branches[qid]
        modified_branches[qid] = {**record, "r1_indices": [0], "A": {**record["A"], "paragraph_indices": [0]}}
        _, details = check.analyze(pilot, modified_branches, table)
        row = next(item for item in details if item["_id"] == qid)
        self.assertIsNone(row["bridge_link"])
        self.assertEqual(row["combined_score"], row["nli_risk_percentile"])
        modified_table = {**table, qid: {**table[qid], "delta_class": "tie"}}
        with self.assertRaisesRegex(ValueError, "CSV delta class"):
            check.analyze(pilot, branches, modified_table)

    def test_class_labels_do_not_affect_selection(self):
        pilot, branches, table = [check.records_by_id(rows, "synthetic") for rows in self.data]
        original, _ = check.analyze(pilot, branches, table)
        qid = original["strategies"]["nli_plus_bridge"]["selected_ids"][0]
        record = branches[qid]
        branches[qid] = {
            **record, "A": {**record["A"], "F1": 1.0},
            "B": {**record["B"], "F1": 0.0}, "delta_class": "degraded",
        }
        table[qid] = {**table[qid], "F1_A": 1.0, "F1_B": 0.0, "delta_class": "degraded"}
        changed, _ = check.analyze(pilot, branches, table)
        for name in original["strategies"]:
            self.assertEqual(original["strategies"][name]["selected_ids"], changed["strategies"][name]["selected_ids"])
        self.assertEqual(changed["strategies"]["nli_plus_bridge"]["counts"]["degraded"], 1)

    def test_cli_with_fake_step3_responses(self):
        pilot, branches, table = self.data
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / "pilot.json").write_text(json.dumps(pilot), encoding="utf-8")
            (path / "branches.jsonl").write_text(
                "\n".join(json.dumps(record) for record in branches), encoding="utf-8"
            )
            with (path / "per_question.csv").open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=list(table[0]))
                writer.writeheader()
                writer.writerows(table)
            args = [
                sys.executable, str(ROOT / "analyze_pilot_signals_v2.py"),
                "--pilot", "pilot.json", "--branches", "branches.jsonl",
                "--per-question", "per_question.csv",
            ]
            subprocess.run(args, cwd=temp, check=True, capture_output=True)
            destination = path / "pilot_signals_v2"
            first = (destination / "summary.json").read_bytes()
            summary = json.loads(first)
            self.assertEqual(summary["pilot_class_counts"], {"improved": 25, "tie": 75, "degraded": 0})
            self.assertEqual(summary["uniform_random_expected_counts"]["improved"], 5.0)
            self.assertEqual(summary["strategies"]["nli_plus_bridge"]["counts"]["improved"], 20)
            self.assertEqual(summary["strategies"]["nli_only"]["n_selected"], 20)
            self.assertTrue((destination / "per_question_selection.csv").is_file())
            again = subprocess.run(args, cwd=temp, capture_output=True)
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual((destination / "summary.json").read_bytes(), first)
            forbidden = subprocess.run(args + ["--out", "cache.jsonl"], cwd=temp, capture_output=True)
            self.assertNotEqual(forbidden.returncode, 0)
            self.assertFalse((path / "cache.jsonl").exists())


if __name__ == "__main__":
    unittest.main()

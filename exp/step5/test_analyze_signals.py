#!/usr/bin/env python3
import csv, json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_signals as a


class TestAuc(unittest.TestCase):
    def test_perfect_separation(self):
        # higher score = positive; positives all larger
        self.assertAlmostEqual(a.auc_score([3, 4, 5], [0, 1, 2]), 1.0)

    def test_chance(self):
        # identical distributions
        self.assertAlmostEqual(a.auc_score([1, 2, 3], [1, 2, 3]), 0.5)

    def test_inverted_is_zero(self):
        self.assertAlmostEqual(a.auc_score([0, 1], [2, 3]), 0.0)

    def test_ties(self):
        # all equal -> 0.5
        self.assertAlmostEqual(a.auc_score([1, 1], [1, 1]), 0.5)


class TestAnalyze(unittest.TestCase):
    def _rows(self):
        # 4 improved with low entailment, 6 ties with high entailment
        rows = []
        for i, e in enumerate([0.2, 0.3, 0.25, 0.35]):
            rows.append({"_id": f"imp{i}", "delta_class": "improved",
                         "nli_entailment_A": e, "mean_logprob_A": -2.0 - i, "min_logprob_A": -3.0})
        for i, e in enumerate([0.9, 0.85, 0.95, 0.88, 0.92, 0.99]):
            rows.append({"_id": f"tie{i}", "delta_class": "tie",
                         "nli_entailment_A": e, "mean_logprob_A": -0.2, "min_logprob_A": -0.4})
        rows.append({"_id": "deg0", "delta_class": "degraded",
                     "nli_entailment_A": 0.7, "mean_logprob_A": -1.0, "min_logprob_A": -1.5})
        return rows

    def test_auc_high_when_low_entailment_marks_improved(self):
        s = a.analyze(self._rows(), bootstrap_samples=200, bootstrap_seed=42)
        auc = s["signals"]["nli_entailment_A"]["auc_improved_vs_tie"]
        self.assertGreater(auc, 0.9)
        self.assertEqual(s["n_by_class"]["improved"], 4)
        self.assertEqual(s["n_by_class"]["tie"], 6)
        self.assertEqual(s["n_by_class"]["degraded"], 1)
        # mean entailment of improved should be lower
        self.assertLess(
            s["signals"]["nli_entailment_A"]["mean_improved_minus_tie"], 0
        )
        lo, hi = s["signals"]["nli_entailment_A"]["auc_ci95"]
        self.assertLessEqual(lo, auc)
        self.assertLessEqual(auc, hi)

    def test_end_to_end_writes(self):
        rows = self._rows()
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "per_question.csv")
            with open(p, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)
            rc = a.main(["--dir", d, "--bootstrap-samples", "100"])
            self.assertEqual(rc, 0)
            with open(os.path.join(d, "signal_summary.json"), encoding="utf-8") as f:
                s = json.load(f)
            self.assertIn("Diagnostic only", s["note"])
            self.assertTrue(os.path.isfile(os.path.join(d, "signal_by_class.csv")))


if __name__ == "__main__":
    unittest.main(verbosity=2)

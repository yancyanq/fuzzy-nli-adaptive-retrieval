"""Synthetic checks of formal paired inference and case selection."""
from copy import deepcopy
import unittest

import analyze_step6_v2 as step


class Step6AnalysisTest(unittest.TestCase):
    def test_constant_paired_difference(self):
        # Marginal values vary greatly. The paired difference is fixed.
        cases = [{"fuzzy_f1": x + .125, "crisp_f1": x, "nli_only_f1": x,
                  "never_f1": x, "oracle_f1": x+.25, "full_f1": x+.25}
                 for x in (0., .25, .5, .75)]
        for row in step.contrasts(cases, n_boot=32):
            self.assertEqual(row["estimate"], row["lower"])
            self.assertEqual(row["upper"], row["lower"])

    def test_audit_strata_use_cited_paragraphs_and_gate_choice(self):
        question = {"_id": "toy", "question": "Who?", "answer": "C", "context": [
                    ["Distractor", ["A"]], ["Gold 1", ["B"]], ["Gold 2", ["C"]]],
                    "supporting_facts": [["Gold 1", 0], ["Gold 2", 0]]}
        a = {"answer": "A", "paragraph_indices": [0, 1], "citations": [2]}
        b = {"answer": "C", "paragraph_indices": [0, 1, 2], "citations": [2, 3]}
        row = {"_id": "toy", "fuzzy_branch": "A", "crisp_branch": "B", "delta_f1": "1",
               "delta_class": "improved", "never_f1": "0", "always_f1": "1",
               "never_em": "0", "always_em": "1", "entailment_A": ".7", "entailment_B": ".8",
               "bridge_absent": "True", "nli_truncated_A": "False", "nli_fallback_A": "False"}
        answers = {("toy","A"): a, ("toy","B"): b}
        evidence = {key: {"sp": []} for key in answers}
        audit, coverage, overlap = step.sample_audit([question], [row], answers, evidence)
        self.assertEqual(overlap, {"A/B": 1})
        self.assertEqual(coverage["missed_improved"]["added_gold_title"], 1)
        self.assertEqual(audit["missing_hop_candidate"]["cases"][0]["A"]["cited_titles"], ["Gold 1"])
        self.assertEqual(audit["wrong_citation_candidate"]["eligible"], 0)
        contradictory = deepcopy(row)
        contradictory["delta_class"] = "tie"
        with self.assertRaises(ValueError):
            step.sample_audit([question], [contradictory], answers, evidence)


if __name__ == "__main__":
    unittest.main()

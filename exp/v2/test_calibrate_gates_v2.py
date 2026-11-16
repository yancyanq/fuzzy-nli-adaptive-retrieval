import json
import unittest

from calibrate_gates_v2 import Pair, calibrate, candidate_grid, gate_score, should_retrieve


class GateCalibrationTests(unittest.TestCase):
    def test_soft_and_hard_membership_share_the_same_rule_endpoints(self):
        parameters = {"lo": 0.0, "hi": 1.0, "bridge_weight": 0.25}
        for kind in ("fuzzy", "crisp"):
            self.assertEqual(gate_score(kind, parameters, 0.0, False), 0.0)
            self.assertEqual(gate_score(kind, parameters, 0.0, True), 0.25)
            self.assertEqual(gate_score(kind, parameters, 1.0, False), 0.75)
            self.assertEqual(gate_score(kind, parameters, 1.0, True), 1.0)
        self.assertEqual(gate_score("fuzzy", parameters, 0.25, True), 0.4375)
        self.assertEqual(gate_score("crisp", parameters, 0.25, True), 0.25)
        self.assertEqual(gate_score("fuzzy", parameters, 0.25, None), 0.25)

    def test_serialized_boundary_keeps_budget_and_applies_per_question(self):
        rows = [
            Pair("a", 0.875, False, 0.0, 1.0, 0, 1),
            Pair("b", 0.875, False, 0.0, 1.0, 0, 1),
            Pair("c", 0.875, False, 1.0, 0.0, 1, 0),
            Pair("d", 0.125, True, 1.0, 1.0, 1, 1),
            Pair("e", 0.125, None, 1.0, 1.0, 1, 1),
        ]
        gates, summary, selections = calibrate(rows, 2)
        gates = json.loads(json.dumps(gates))
        for name, gate in gates.items():
            from_boundary = {
                p.qid for p in rows if should_retrieve(gate, p.qid, 1 - p.risk, p.bridge_absent)
            }
            self.assertEqual(from_boundary, selections[name])
            self.assertEqual(summary["policies"][name]["n_retrieved"], 2)
            self.assertFalse(should_retrieve(gate, "very-low-risk-new-id", 1.0, False))
        self.assertEqual(summary["policies"]["never"]["retrieval_rate"], 0.0)
        self.assertEqual(summary["policies"]["always"]["retrieval_rate"], 1.0)
        self.assertEqual(summary["policies"]["oracle"]["f1"], 1.0)
        self.assertEqual(calibrate(list(reversed(rows)), 2)[0], gates)

    def test_constant_nli_risk_still_yields_a_valid_grid(self):
        rows = [Pair(str(i), 0.5, None, 0.0, 0.0, 0, 0) for i in range(5)]
        self.assertEqual(len(candidate_grid(rows)), 3)
        self.assertEqual(calibrate(rows, 2)[1]["policies"]["fuzzy"]["n_retrieved"], 2)


if __name__ == "__main__":
    unittest.main()

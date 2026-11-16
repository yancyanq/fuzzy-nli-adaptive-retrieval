"""Synthetic tests only. The existing HTTP mock runs with a local opt-in selector response."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import httpx

import generate_test_v2 as gen


ROOT = Path(__file__).resolve().parent
EXAMPLE = {"_id": "synthetic", "question": "Who is the subject?", "answer": "Alpha",
           "context": [["Alpha", ["Wrong sentence.", "Correct sentence."]], ["Beta", ["Other document."]]],
           "supporting_facts": [["Alpha", 1]]}


class TinyTokenizer:
    def apply_chat_template(self, messages, **_):
        return messages[-1]["content"].split()


class GenerationTest(unittest.TestCase):
    def test_mock_answer_to_sentence_to_official_score(self):
        path = ROOT.parent / "step3" / "test_mock_server.py"
        spec = importlib.util.spec_from_file_location("step3_mock", path)
        mock = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mock)
        def completion(request):
            body = json.loads(request.content)
            response = mock.completion_body(body, "mock")
            if body["messages"][0]["content"].startswith("Identify the minimum"):
                response["choices"][0]["message"]["content"] = json.dumps({"sentence_ids": [2, 2, 3, True]})
            return httpx.Response(200, json=response)

        with httpx.Client(transport=httpx.MockTransport(completion)) as transport:
            client = gen.cm.make_client("http://127.0.0.1:8000/v1", None, True).with_options(http_client=transport)
            answer = gen.answer_request(client, EXAMPLE, [0, 1])
            evidence = gen.select_evidence(client, TinyTokenizer(), EXAMPLE, answer)
        self.assertEqual(answer["answer"], "Alpha")
        self.assertEqual(evidence["sp"], [["Alpha", 1]])
        self.assertEqual(evidence["evidence_calls"][0]["invalid_ids"], 2)
        scorer = gen.load_official(ROOT / "step5_v2/hotpot_evaluate_v1.py")
        quality = gen.scoring_row(scorer, EXAMPLE, answer["answer"], evidence["sp"])
        self.assertEqual((quality["f1"], quality["em"], quality["sp_f1"]), (1, 1, 1))

    def test_no_citations_need_no_api_call(self):
        self.assertEqual(gen.select_evidence(None, None, EXAMPLE, {"paragraph_indices": [0], "citations": []}),
                         {"sp": [], "evidence_calls": [], "candidate_count": 0})

    def test_invalid_output_and_cache_resumption(self):
        self.assertEqual(gen.parse_selector('{"sentence_ids": "1"}', {1: None}), ([], False, 0))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "resumable.jsonl"
            path.write_bytes(b'{"k":1}\n{"k":')
            self.assertEqual(gen.read_cache(path, ("k",), {(1,)}), {(1,): {"k": 1}})
            self.assertEqual(path.read_bytes(), b'{"k":1}\n')
            with self.assertRaises(ValueError):
                gen.read_cache(path, ("k",), {(2,)})

    def test_locked_sources(self):
        lock = gen.load_lock(ROOT / "step4_dev/gates/locked_gates.json", ROOT / "step4_dev/.serve-step4.sh")
        self.assertEqual(lock["dev_target_count"], 100)


if __name__ == "__main__":
    unittest.main()

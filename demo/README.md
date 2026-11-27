# FNLI QA Chatbot · Group 13

The interface compares direct 2+1 retrieval with the locked P5 NLI + Sugeno policy. It shows the first two BM25 passages, the draft answer, DeBERTa's three NLI probabilities, the bridge signal, the gate score and boundary, any added passages, and the selected sentence citations. Each turn uses its own candidate pool.

## Run the P5 archive demo

From the repository root:

```sh
python3 demo/app.py
```

Open http://127.0.0.1:7860. The archive runs with the Python standard library. It replays the 300 primary P5 questions using the archived route outputs, gate decisions and extracted citations. The two featured questions illustrate triggering and retaining the first answer. Token statistics show successful Qwen calls, including generation and sentence selection. They exclude NLI input tokens.

## Run real inference

Use the P5 runtime environment and the pinned Qwen and DeBERTa snapshots listed in the [P5 protocol](../exp/v3/p5/protocol.json). The backend expects a vLLM server advertising `Qwen/Qwen2.5-7B-Instruct` with an 8,192-token context. The supplied Qwen tokenizer is checked against the frozen prompt audit and DeBERTa weights are checked against their recorded hash.

```sh
python3 demo/app.py --live --port 7860 \
  --model-url http://127.0.0.1:18083/v1 \
  --tokenizer /absolute/path/to/Qwen2.5-7B-Instruct \
  --snapshot /absolute/path/to/deberta-b3546ea
```

In live mode, choose a P5 question or supply an English question and 2–30 English candidate paragraphs. The same gate parameters and calibrated boundary apply to custom input. The 20% budget identifies the calibration setting. The observed trigger rate varies with the questions.

The demo listens on loopback. For a remote server, open an SSH tunnel from your machine using the account and hostname of that server:

```sh
ssh -N -L 127.0.0.1:7861:127.0.0.1:7860 account@hostname
```

Then open http://127.0.0.1:7861. Keep the tunnel open while using the demo.

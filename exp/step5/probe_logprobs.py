#!/usr/bin/env python3
"""Tiny probe: does the API return non-zero token logprobs?

Makes 2 prompts x 2 temperatures (0 and 1) = 4 calls by default.
Requests logprobs=True and top_logprobs=5, then reports per call:
number of tokens, how many logprobs are exactly 0.0, min / mean logprob,
and whether the top-5 alternatives carry non-zero values.

The key is read only from an environment variable and never printed.

Usage (YangQS):
    python probe_logprobs.py --preset deepseek
Outputs: probe_logprobs.json (raw token logprobs, no key).
"""
import argparse
import json
import os
import sys

PRESETS = {
    "deepseek": ("https://api.deepseek.com", "deepseek-chat", "DEEPSEEK_API_KEY"),
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini", "OPENAI_API_KEY"),
}

PROMPTS = [
    # short factual, low uncertainty
    "Answer with one word: What is the capital of France?",
    # open-ended, higher uncertainty
    "Name one random fruit. Answer with one word only.",
]


def get_tokens(resp):
    ch = resp.choices[0]
    lp = getattr(ch, "logprobs", None)
    if lp is None or not getattr(lp, "content", None):
        return None
    out = []
    for t in lp.content:
        tops = []
        for alt in (getattr(t, "top_logprobs", None) or []):
            tops.append({"token": getattr(alt, "token", ""), "logprob": getattr(alt, "logprob", None)})
        out.append({"token": getattr(t, "token", ""), "logprob": getattr(t, "logprob", None), "top": tops})
    return out


def stats(tokens):
    lps = [t["logprob"] for t in tokens if t["logprob"] is not None]
    alts = [a["logprob"] for t in tokens for a in t["top"] if a["logprob"] is not None]
    return {
        "n_tokens": len(tokens),
        "n_logprob_exactly_zero": sum(1 for x in lps if x == 0.0),
        "min_logprob": min(lps) if lps else None,
        "mean_logprob": (sum(lps) / len(lps)) if lps else None,
        "n_top_alternatives": len(alts),
        "n_top_alternatives_nonzero": sum(1 for x in alts if x != 0.0),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", choices=list(PRESETS) + ["custom"], default="deepseek")
    ap.add_argument("--base-url")
    ap.add_argument("--model")
    ap.add_argument("--key-env")
    ap.add_argument("--temps", default="0,1", help="comma-separated temperatures")
    ap.add_argument("--top-logprobs", type=int, default=5)
    ap.add_argument("--out", default="probe_logprobs.json")
    a = ap.parse_args()

    if a.preset == "custom":
        base, model, key_env = a.base_url, a.model, a.key_env or "OPENAI_API_KEY"
        if not base or not model:
            sys.exit("--preset custom needs --base-url and --model")
    else:
        base, model, key_env = PRESETS[a.preset]
        base = a.base_url or base
        model = a.model or model
        key_env = a.key_env or key_env
    key = os.environ.get(key_env)
    print(f"{key_env}={'set' if key else 'MISSING'}  model={model}")
    if not key:
        sys.exit(f"Set the environment variable {key_env} first.")
    try:
        from openai import OpenAI
    except ImportError:
        sys.exit("pip install openai")
    client = OpenAI(api_key=key, base_url=base)

    temps = [float(x) for x in a.temps.split(",") if x.strip()]
    results = []
    print()
    print(f"{'temp':>5} {'prompt':>7} {'tokens':>7} {'lp==0':>6} {'min_lp':>10} {'mean_lp':>10} {'top!=0':>8}  answer")
    for temp in temps:
        for pi, prompt in enumerate(PROMPTS):
            rec = {"temperature": temp, "prompt_index": pi, "prompt": prompt}
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temp,
                    max_tokens=8,
                    logprobs=True,
                    top_logprobs=a.top_logprobs,
                )
            except Exception as e:  # report but continue
                msg = str(e).replace(key, "***") if key else str(e)
                rec["error"] = msg[:300]
                results.append(rec)
                print(f"{temp:5.1f} {pi:7d}  ERROR: {rec['error']}")
                continue
            content = resp.choices[0].message.content or ""
            toks = get_tokens(resp)
            rec["answer"] = content
            if toks is None:
                rec["logprobs_returned"] = False
                print(f"{temp:5.1f} {pi:7d}  no logprobs returned  answer={content!r}")
            else:
                rec["logprobs_returned"] = True
                rec["tokens"] = toks
                s = stats(toks)
                rec["stats"] = s
                print(
                    f"{temp:5.1f} {pi:7d} {s['n_tokens']:7d} {s['n_logprob_exactly_zero']:6d} "
                    f"{(s['min_logprob'] if s['min_logprob'] is not None else float('nan')):10.4f} "
                    f"{(s['mean_logprob'] if s['mean_logprob'] is not None else float('nan')):10.4f} "
                    f"{s['n_top_alternatives_nonzero']:4d}/{s['n_top_alternatives']:<3d}  {content!r}"
                )
            results.append(rec)

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"model": model, "base_url": base, "results": results}, f, indent=2, ensure_ascii=False)
    print()
    print(f"wrote {a.out}")
    print("Read: if lp==0 equals tokens on every row and top!=0 is 0, the API returns degenerate (all-zero) logprobs.")
    print("If temperature 1 rows show negative values, zeros at temperature 0 are a vendor behaviour under greedy decoding.")


if __name__ == "__main__":
    main()

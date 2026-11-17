"""Write a method-blinded citation packet from locked cases and generated answers only."""

import argparse
import csv
import hashlib
from html import escape
import json
from pathlib import Path

from evaluate import HERE, PRIMARY, ROUTES, load_panel, policy_registry, visible_references

DEFAULT_METHODS = (PRIMARY, "fixed_fuzzy", "ridge", "direct_2plus4", "full")
GUIDE = """# P5 引用充分性盲审

每条回答的系统名称已经隐藏。请根据所列引用判断它能否让读者核实回答、以及是否覆盖回答问题所需的完整证据链。相邻句帮助理解代词和语境，请以标记为“引用”的句子为评分依据。遇到相同回答也请独立填写。请按答复编号填写 TSV，保留原列与编号。

- `answer_supported`：引用能支持答案填 `yes`，不能填 `no`，无法判定填 `unknown`。
- `chain_complete`：引用覆盖完整证据链填 `yes`，缺少必要步骤填 `no`，无法判定填 `unknown`。
- `reviewer` 填姓名或固定缩写。用 `notes` 记下缺失的步骤、间接证据或无法判定的理由。

评审时请以当前包为准。双人评审的题目请分别完成各自的表格。
"""


def quote(value):
    return "> " + escape(" ".join(value.splitlines()))


def answer_material(pool, row):
    visible = visible_references(pool, row)
    lines = [quote(row["answer"]) if row["answer"] else "（答复为空）"]
    if not row["sp"]:
        return [*lines, "", "（没有有效句级引用）"]
    for number, (title, index) in enumerate(row["sp"], start=1):
        lines += ["", f"**原文 {number} · {escape(title)}**"]
        previous = visible.get((title, index - 1))
        following = visible.get((title, index + 1))
        if previous is not None:
            lines += ["", "相邻上文", "", quote(previous)]
        lines += ["", "引用", "", quote(visible[title, index])]
        if following is not None:
            lines += ["", "相邻下文", "", quote(following)]
    return lines


def packets(split, pools, quality, decisions, cfg):
    methods = cfg.get("human_methods", DEFAULT_METHODS)
    if len(methods) < 2 or len(set(methods)) != len(methods):
        raise ValueError("Frozen blind review method list is invalid")
    size, budget, seed = cfg["primary_size"], cfg["primary_budget_percent"], cfg["draw_seed"]
    double = set(split["human_dual_qids"])
    cases = []
    for number, qid in enumerate(split["human_qids"], start=1):
        pool = pools[qid, size]
        case_id = f"P5-{number:03d}"
        text_lines = [f"## {case_id}", "", quote(pool["input"]["question"])]
        shortlist = sorted(
            methods, key=lambda method: hashlib.sha256(f"p5-blind:{seed}:{qid}:{method}".encode()).digest()
        )
        mapping = []
        for ordinal, method in enumerate(shortlist, start=1):
            item_id = f"{case_id}-{ordinal}"
            method_budget = -1 if method == "v2_native" else budget
            route = method if method in ROUTES else decisions[qid, size, method, method_budget]["final_route"]
            row = quality[qid, size, route]
            text_lines += ["", f"### 答复 {item_id}", "", *answer_material(pool, row)]
            mapping.append({"item_id": item_id, "qid": qid, "pool_size": size, "method": method,
                            "route": route, "budget_percent": None if method in ROUTES else method_budget})
        cases.append((qid in double, text_lines, mapping))
    return cases


def write_review(packet_dir, filename, cases):
    packet = packet_dir / f"{filename}.md"
    blocks = ["\n".join(text_lines) for _, text_lines, _ in cases]
    packet.write_text("\n\n".join([GUIDE, *blocks]) + "\n", encoding="utf-8")
    with (packet_dir / f"{filename}.tsv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(["item_id", "answer_supported", "chain_complete", "reviewer", "notes"])
        writer.writerows([row["item_id"], "", "", "", ""] for _, _, mapping in cases for row in mapping)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--input", required=True, type=Path)
    cli.add_argument("--raw", required=True, type=Path)
    cli.add_argument("--out", required=True, type=Path, help="Reviewer-facing Markdown and TSV files")
    cli.add_argument("--mapping", required=True, type=Path, help="Private method key outside the reviewer packet")
    cli.add_argument("--protocol", type=Path, default=HERE / "protocol.json")
    cli.add_argument("--policy-lock", type=Path)
    args = cli.parse_args()
    if args.mapping.resolve().is_relative_to(args.out.resolve()):
        cli.error("The method key must be outside the reviewer packet")
    if args.mapping.exists():
        cli.error("The method key already exists")

    cfg = json.loads(args.protocol.read_text(encoding="utf-8"))
    registry = policy_registry(args.policy_lock or args.protocol.with_name("policy_lock.json"), args.protocol, cfg)
    split, _, pools, quality, decisions = load_panel(args.input, args.raw, cfg, registry)
    cases = packets(split, pools, quality, decisions, cfg)
    args.out.mkdir(parents=True, exist_ok=False)
    write_review(args.out, "reviewer_1", cases)
    double = [case for case in cases if case[0]]
    write_review(args.out, "reviewer_2", double)
    mapping = [row | {"double_review": doubled} for doubled, _, rows in cases for row in rows]
    args.mapping.parent.mkdir(parents=True, exist_ok=True)
    with args.mapping.open("x", encoding="utf-8") as stream:
        for row in mapping:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Generated {len(cases)} blinded cases, {len(double)} for dual review.")


if __name__ == "__main__":
    main()

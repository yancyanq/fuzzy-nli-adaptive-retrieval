"""Build the locked 30-case reviewer packet without scores or gold."""

import argparse
import csv
import json
from pathlib import Path

from prepare import HERE, jsonl
from verify import indexed


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--nli", type=Path, required=True)
    cli.add_argument("--out", type=Path, required=True)
    args = cli.parse_args()
    panel = {r["qid"]: r for r in jsonl(HERE / "input/panel.jsonl")}
    frozen = json.loads((HERE / "input/manifest.json").read_text())["human_sample_qids"]
    nli = {r["qid"]: r for r in jsonl(args.nli)}
    if panel.keys() != nli.keys() or len(frozen) != 30 or len(set(frozen)) != 30:
        raise ValueError("Unexpected or missing P2 review IDs")
    text = [
        "# P2 · 人工语义核验包（30 道开发题）", "",
        "只依据这份材料内的首轮原文。评分表以 case_id 和 unit 对应。逐项判断关系是否忠实于问题与草稿、"
        "证据是否支持关系、关系组合是否完整，以及原整题陈述是否获其实际输入支持。保留不同判定，允许填 unknown。",
        "材料隐藏金标、补查结果和机器 NLI 分数。人工忠实率按 yes / (yes + no) 报告，同时列出 unknown 和未评数。", "",
        "若整题输入标记截断，仍按呈现的原文做语义标注，这类条目单列，不汇入同输入的一致率。", "",
    ]
    sheet = []
    for k, qid in enumerate(frozen, 1):
        case = f"P2-{k:02d}"
        row, result = panel[qid], nli[qid]
        refs = indexed(row)
        text.extend([f"## {case} · {qid}", "",
                     f"**问题**　{row['question']}", "",
                     f"**首答**　{row['draft_answer']}　引用段号 {row['draft_citations']}", "",
                     "### 可见原文", ""])
        for key, ref in refs.items():
            text.append(f"- **{key} · {ref['title']}**　{ref['text']}")
        text.extend(["", "### V2 整题核验", "",
                     f"陈述　{result['old_whole']['hypothesis']}",
                     f"原始输入是否发生 512 token 截断　{result['old_whole']['truncated']}", "",
                     result["old_whole"]["premise"], "", "### 必要关系与实际局部证据", ""])
        sheet.extend([(case, qid, "whole", "whole", "", "", "", "", ""),
                      (case, qid, "question", "coverage", "", "", "", "", "")])
        rel = result["relation_validation"]
        if not rel["ok"]:
            text.extend([f"结构校验失败　{', '.join(rel['errors'])}", ""])
        else:
            for claim, plan in zip(rel["record"]["requirements"], result["local_claims"], strict=True):
                rid = claim["id"]
                text.extend([f"- **{rid} · {claim['relation']}**　{claim['status']}／{claim['uncertainty']}",
                             f"  - 主体　{claim['subject']}", f"  - 对象　{claim['object']}",
                             f"  - 陈述　{claim['claim']}", f"  - 关系引用　{claim['evidence_ids']}"])
                if plan["bundles"]:
                    for i, bundle in enumerate(plan["bundles"], 1):
                        text.append(f"  - 局部证据束 {i}　{bundle['status']}　{bundle['evidence_ids']}")
                else:
                    text.append(f"  - 局部证据　{plan['kind']}")
                sheet.append((case, qid, "relation", rid, "", "", "", "", ""))
            text.extend(["", f"桥接实体字段　{rel['record']['bridge_entity']}", ""])

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "review_packet.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    with (args.out / "human_ratings.tsv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(("case_id", "qid", "unit", "item", "faithful", "support", "coverage", "reviewer", "notes"))
        writer.writerows(sheet)
    print(f"Prepared {len(frozen)} independent cases with {len(sheet)} blank human judgments.")


if __name__ == "__main__":
    main()

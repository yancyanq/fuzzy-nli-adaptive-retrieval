"""Generate the GitHub progress page from the append-only experiment log."""

import argparse
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "exp" / "EXPERIMENT_LOG.md"
PROGRESS = ROOT / "PROGRESS.md"
ENTRY = re.compile(r"^## (\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?) — (.+)$")
SECRET_MARKER = re.compile(
    r"(?<![\w-])(?:sk-(?:proj-|or-v1-)?[A-Za-z0-9_-]{16,}"
    r"|hf_[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{30,}|AKIA[A-Z0-9]{16}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{25,}"
    r"|xox[baprs]-[A-Za-z0-9-]{12,})"
    r"|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"|(?i:bearer +[A-Za-z0-9_./+=-]{18,})"
    r"|(?i:(?:api[_ -]?key|access[_ -]?token|authorization)\s*[:=]"
    r"\s*['\"]?[A-Za-z0-9_./+=-]{20,})"
)


def write_if_changed(path, content):
    if path.exists() and path.read_bytes() == content:
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-log", type=Path, help="Optional original experiment log to import")
    args = parser.parse_args()

    current = LOG.read_bytes()
    proposed = args.source_log.read_bytes() if args.source_log else current
    if not proposed.startswith(current):
        raise SystemExit("源日志与仓库日志已经分叉，请人工核对后再同步。")

    log_text = proposed.decode("utf-8")
    if SECRET_MARKER.search(log_text):
        raise SystemExit("日志包含疑似凭据格式，请在本机检查后再同步。")

    entries = []
    for line_number, line in enumerate(log_text.splitlines(), start=1):
        if match := ENTRY.fullmatch(line):
            entries.append((line_number, *match.groups()))
    if not entries:
        raise SystemExit("日志中找不到带日期的进度条目。")

    for _, _, title in entries:
        if "<" in title or ">" in title:
            raise SystemExit("日志标题包含 HTML 标记，请人工核对后再同步。")

    lines = [
        "# 实验进度", "",
        "按记录顺序从新到旧展示。时间为北京时间。判定、数据和参数以权威日志各条目为准。", "",
        "| 时间 | 条目 | 日志位置 |",
        "| --- | --- | --- |",
    ]
    for line_number, date, title in reversed(entries):
        safe_title = title.replace("|", r"\|")
        lines.append(f"| {date} | {safe_title} | [原始条目](exp/EXPERIMENT_LOG.md#L{line_number}) |")
    lines.extend(["", "[返回项目 README](README.md) · [查看完整实验日志](exp/EXPERIMENT_LOG.md)", ""])
    write_if_changed(LOG, proposed)
    write_if_changed(PROGRESS, "\n".join(lines).encode("utf-8"))


if __name__ == "__main__":
    main()

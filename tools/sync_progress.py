"""Publish an experiment log without timestamps and generate its progress page."""

import argparse
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "exp" / "EXPERIMENT_LOG.md"
PROGRESS = ROOT / "PROGRESS.md"
DATE = r"\d{4}-\d{2}-\d{2}"
CLOCK = r"(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d+)?)?"
STAMP = rf"{DATE}(?:[ T]{CLOCK}(?:Z|[+-]\d{{2}}:\d{{2}})?)?"
ZONE = r"(?:[A-Za-z]+(?:[ _-][A-Za-z]+)*/[A-Za-z_+-]+|Beijing time|(?:UTC|GMT)(?:[+-]\d{1,2}(?::\d{2})?)?)"
DATED_ENTRY = re.compile(rf"^## (?P<stamp>{STAMP})(?: \({ZONE}\)| {ZONE})? — (?P<title>.+)$")
ENTRY = re.compile(r"^## (.+)$")
MONTH_AND_DAY = (
    r"(?i:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r" \d{1,2}(?:, \d{4})?"
)
TIMESTAMP = re.compile(
    rf"(?<![\w.:/-])(?:{STAMP}|(?:{MONTH_AND_DAY} )?{CLOCK}|{MONTH_AND_DAY})"
    rf"(?: \({ZONE}\)| {ZONE})?(?: on {MONTH_AND_DAY})?(?![\w:]|\.\d)"
)
ENTRY_REFERENCE = re.compile(
    rf"\bthe (?:{MONTH_AND_DAY} )?(?P<clock>{CLOCK})"
    r" (?P<label>pre-registration|probe entry|entry|candidate settings)\b"
)
RUN_TIMES = re.compile(rf"The run started {CLOCK} and completed {CLOCK} \(Asia/Shanghai\)\. ")
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


def render_log(log_text):
    entries_by_clock = {}
    rendered = []

    def link_to_entry(match):
        line_numbers = entries_by_clock.get(match["clock"], [])
        if len(line_numbers) != 1:
            return f"the {match['label']}"
        (line_number,) = line_numbers
        return f"the [{match['label']}](?plain=1#L{line_number})"

    for line_number, original in enumerate(log_text.splitlines(keepends=True), start=1):
        line = original.rstrip("\r\n")
        ending = original[len(line):]
        if match := DATED_ENTRY.fullmatch(line):
            if clock := re.search(CLOCK, match["stamp"]):
                entries_by_clock.setdefault(clock[0], []).append(line_number)
            line = f"## {match['title']}"
        if line == "Times in Asia/Shanghai (UTC+8).":
            line = "Entries are listed in recording order."
        line = RUN_TIMES.sub("", line)
        line = ENTRY_REFERENCE.sub(link_to_entry, line)
        line = TIMESTAMP.sub("[time omitted]", line)
        rendered.append(line + ending)
    return "".join(rendered)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-log", type=Path, help="Optional original experiment log to import")
    parser.add_argument("--check", action="store_true", help="Check whether either output needs updating")
    args = parser.parse_args()

    current = LOG.read_text(encoding="utf-8")
    source = args.source_log.read_text(encoding="utf-8") if args.source_log else current
    if SECRET_MARKER.search(source):
        raise SystemExit("日志包含疑似凭据格式，请在本机检查后再同步。")
    log_text = render_log(source)
    if not log_text.startswith(render_log(current)):
        raise SystemExit("源日志与仓库日志已经分叉，请人工核对后再同步。")

    entries = []
    for line_number, line in enumerate(log_text.splitlines(), start=1):
        if match := ENTRY.fullmatch(line):
            entries.append((line_number, *match.groups()))
    if not entries:
        raise SystemExit("日志中找不到进度条目。")

    for _, title in entries:
        if "<" in title or ">" in title:
            raise SystemExit("日志标题包含 HTML 标记，请人工核对后再同步。")

    lines = [
        "# 实验进度", "",
        "按记录顺序从新到旧展示。每个条目链接到对应的实验记录。", "",
        "| 条目 | 日志位置 |",
        "| --- | --- |",
    ]
    for line_number, title in reversed(entries):
        safe_title = title.replace("|", r"\|")
        lines.append(f"| {safe_title} | [查看条目](exp/EXPERIMENT_LOG.md?plain=1#L{line_number}) |")
    lines.extend(["", "[返回项目 README](README.md) · [查看实验日志](exp/EXPERIMENT_LOG.md)", ""])
    progress = "\n".join(lines).encode("utf-8")
    log = log_text.encode("utf-8")
    if args.check:
        needs_update = log != LOG.read_bytes() or not PROGRESS.is_file() or progress != PROGRESS.read_bytes()
        return 3 if needs_update else 0
    write_if_changed(LOG, log)
    write_if_changed(PROGRESS, progress)


if __name__ == "__main__":
    raise SystemExit(main())

"""Cheap, conservative checks on an answer and its first-round source passages."""
from dataclasses import dataclass
import html
import re
import unicodedata


WORD = re.compile(r"[^\W_]+", re.UNICODE)
YEAR = re.compile(r"\b(?:1[0-9]{3}|20[0-9]{2})\b")
NUMBER = re.compile(r"(?<!\w)\d+(?:[,.]\d+)*(?!\w)")
MONTHS = frozenset("january february march april may june july august september october november december".split())
COUNT_WORDS = frozenset(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety "
    "hundred thousand million billion dozen half".split()
)
DATE_WORDS = MONTHS | {"bc", "bce", "ad", "ce"}
ABSTAIN = {"no answer", "no information", "unknown", "insufficient information", "not enough information"}
CHOICE = re.compile(r"\b(?:which|what)\s*[,?:]\s*([\w-]+)\s+or\s+([\w-]+)\s*[?.!]?$", re.I)
NUMERIC_QUESTION = re.compile(r"^(?:how many|how old|how long|how far|how tall|how much)\b", re.I)
DATE_QUESTION = re.compile(
    r"\b(?:first air date|what (?:was the )?(?:year|date)|in (?:what|which) year|on (?:what|which) date)\b",
    re.I,
)
QUOTED = re.compile(r'["“]([^"”\n]+)["”]')


@dataclass(frozen=True)
class Signals:
    answer_type: str | None
    type_mismatch: int
    missing: tuple[str, ...]

    @property
    def gap(self):
        return float(bool(self.missing) or self.type_mismatch)


def words(s):
    return WORD.findall(unicodedata.normalize("NFKC", html.unescape(s)).casefold())


def explicit_type(question, answer):
    """Return only checks with unambiguous answer formats; abstain on broad categories."""
    q = question.lstrip().casefold()
    text = html.unescape(answer).strip()
    a = words(text)
    normalized = " ".join(a)
    if normalized in ABSTAIN or not normalized:
        return None, False

    choice = CHOICE.search(q)
    if choice:
        return "choice", normalized not in {" ".join(words(x)) for x in choice.groups()}
    if q.startswith("when ") or DATE_QUESTION.search(q):
        has_date = bool(NUMBER.search(text) or set(a) & DATE_WORDS or any(w.endswith("s") and w[:-1].isdigit() for w in a))
        return "date", not has_date
    if NUMERIC_QUESTION.match(q):
        return "quantity", not bool(NUMBER.search(text) or set(a) & COUNT_WORDS)
    return None, False


def contains_sequence(haystack, phrase):
    return f" {phrase} " in f" {haystack} "


def compute(question, answer, first_round_text):
    answer_type, mismatch = explicit_type(question, answer)
    evidence = " ".join(words(first_round_text))
    years = set(YEAR.findall(question))
    titles = {" ".join(words(title)) for title in QUOTED.findall(question)}
    anchors = years | (titles - {""})
    missing = tuple(sorted(a for a in anchors if not contains_sequence(evidence, a)))
    return Signals(answer_type, int(mismatch), missing)

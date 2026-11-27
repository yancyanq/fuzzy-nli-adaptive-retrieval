"""Repair clear time expressions while preserving the existing constraint checks."""
from dataclasses import replace
import html
import re

from constraints import compute as original_compute


ORDINAL = r"(?:[0-9]{1,2}(?:st|nd|rd|th)|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|eighteenth|nineteenth|twentieth|twenty[- ]first)"
CENTURY = re.compile(rf"\b{ORDINAL}\s+centur(?:y|ies)\b", re.I)
DECADE = re.compile(r"\b(?:zeroes|aughts|tens|twenties|thirties|forties|fifties|sixties|seventies|eighties|nineties)\b|(?<!\w)['’][0-9]{2}s\b", re.I)


def compute(question, answer, first_round_text):
    signal = original_compute(question, answer, first_round_text)
    if signal.answer_type == "date" and signal.type_mismatch:
        text = html.unescape(answer)
        if CENTURY.search(text) or DECADE.search(text):
            return replace(signal, type_mismatch=0)
    return signal

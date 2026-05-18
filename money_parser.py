"""Deterministic multi-amount extraction for Chilean pesos."""

from __future__ import annotations

import re
from dataclasses import dataclass

from text_normalizer import normalize_text

MONEY_UNITS = {"peso", "pesos", "clp", "luca", "lucas", "mil", "miles", "k"}
CONNECTORS = {"y", "con", "de", "unos", "un", "una", "como", "aprox", "aproximadamente"}
STOP_WORDS = {
    "gaste",
    "pague",
    "compre",
    "compro",
    "compramos",
    "costo",
    "costaron",
    "sali",
    "salio",
    "por",
    "en",
    "de",
    "el",
    "la",
    "los",
    "las",
    "un",
    "una",
    "unos",
    "unas",
    "despues",
    "luego",
    "y",
    "me",
}
NUMBER_WORDS: dict[str, int] = {
    "cero": 0,
    "un": 1,
    "uno": 1,
    "una": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
    "once": 11,
    "doce": 12,
    "trece": 13,
    "catorce": 14,
    "quince": 15,
    "dieciseis": 16,
    "diecisiete": 17,
    "dieciocho": 18,
    "diecinueve": 19,
    "veinte": 20,
    "veintiun": 21,
    "veintiuno": 21,
    "veintiuna": 21,
    "veintidos": 22,
    "veintitres": 23,
    "veinticuatro": 24,
    "veinticinco": 25,
    "veintiseis": 26,
    "veintisiete": 27,
    "veintiocho": 28,
    "veintinueve": 29,
    "treinta": 30,
    "cuarenta": 40,
    "cincuenta": 50,
    "sesenta": 60,
    "setenta": 70,
    "ochenta": 80,
    "noventa": 90,
    "cien": 100,
    "ciento": 100,
    "doscientos": 200,
    "trescientos": 300,
    "cuatrocientos": 400,
    "quinientos": 500,
    "seiscientos": 600,
    "setecientos": 700,
    "ochocientos": 800,
    "novecientos": 900,
}


@dataclass(frozen=True)
class MoneySegment:
    """A money amount found inside a normalized utterance."""

    amount_clp: int
    description: str
    start_token: int
    end_token: int
    confidence: float


def extract_money_segments(text: str) -> list[MoneySegment]:
    """Extract one or more CLP amounts with local descriptions."""
    normalized = normalize_text(text)
    tokens = normalized.split()
    segments: list[MoneySegment] = []
    index = 0
    while index < len(tokens):
        parsed = _parse_amount_at(tokens, index)
        if parsed is None:
            index += 1
            continue
        amount, end_index, confidence = parsed
        if amount > 0:
            segments.append(
                MoneySegment(
                    amount_clp=amount,
                    description=_description_for_amount(tokens, index, end_index),
                    start_token=index,
                    end_token=end_index,
                    confidence=confidence,
                )
            )
        index = max(end_index, index + 1)
    return _deduplicate_segments(segments)


def _parse_amount_at(tokens: list[str], index: int) -> tuple[int, int, float] | None:
    token = tokens[index]
    if token in {"mil", "miles"}:
        return 1000, _consume_currency(tokens, index + 1), 0.80
    number = _parse_numeric_token(token)
    if number is None:
        word_number = _parse_number_words(tokens, index)
        if word_number is None:
            return None
        number, next_index = word_number
    else:
        next_index = index + 1

    unit = tokens[next_index] if next_index < len(tokens) else ""
    if unit in {"luca", "lucas", "k"}:
        amount = number * 1000
        end_index = next_index + 1
        if end_index + 1 < len(tokens) and tokens[end_index] == "y" and tokens[end_index + 1] == "media":
            amount += 500
            end_index += 2
        elif end_index < len(tokens):
            remainder = _parse_numeric_token(tokens[end_index])
            if remainder is not None and remainder < 1000:
                amount += remainder
                end_index += 1
        return amount, _consume_currency(tokens, end_index), 0.95

    if unit in {"mil", "miles"}:
        amount = number * 1000
        end_index = next_index + 1
        if end_index < len(tokens):
            remainder_numeric = _parse_numeric_token(tokens[end_index])
            remainder_words = _parse_number_words(tokens, end_index)
            if remainder_numeric is not None and remainder_numeric < 1000:
                amount += remainder_numeric
                end_index += 1
            elif remainder_words is not None and remainder_words[0] < 1000:
                amount += remainder_words[0]
                end_index = remainder_words[1]
        return amount, _consume_currency(tokens, end_index), 0.95

    if unit in {"peso", "pesos", "clp"}:
        return number, next_index + 1, 0.90

    # Plain large numbers are usually CLP in this application; small bare numbers are ambiguous.
    if number >= 1000:
        return number, next_index, 0.75
    return None


def _parse_numeric_token(token: str) -> int | None:
    cleaned = token.replace(".", "")
    if not cleaned.isdigit():
        return None
    return int(cleaned)


def _parse_number_words(tokens: list[str], index: int) -> tuple[int, int] | None:
    total = 0
    consumed = 0
    cursor = index
    while cursor < len(tokens):
        token = tokens[cursor]
        if token in NUMBER_WORDS:
            total += NUMBER_WORDS[token]
            consumed += 1
            cursor += 1
            continue
        if token == "y" and consumed > 0 and cursor + 1 < len(tokens) and tokens[cursor + 1] in NUMBER_WORDS:
            cursor += 1
            continue
        break
    if consumed == 0:
        return None
    return total, cursor


def _consume_currency(tokens: list[str], index: int) -> int:
    if index < len(tokens) and tokens[index] in {"peso", "pesos", "clp"}:
        return index + 1
    return index


def _description_for_amount(tokens: list[str], start: int, end: int) -> str:
    left_boundary = _find_left_boundary(tokens, start)
    right_boundary = _find_right_boundary(tokens, end)
    before = tokens[left_boundary:start]
    after = tokens[end:right_boundary]
    words = [word for word in before + after if word not in STOP_WORDS and word not in MONEY_UNITS and _parse_numeric_token(word) is None]
    return " ".join(words).strip() or "sin descripcion"


def _find_left_boundary(tokens: list[str], start: int) -> int:
    for index in range(start - 1, -1, -1):
        if tokens[index] in {"despues", "luego", "tambien", "ademas"}:
            return index + 1
        if tokens[index] in {"y"} and index > 0 and _token_looks_like_amount(tokens[index - 1]):
            return index + 1
    return max(0, start - 5)


def _find_right_boundary(tokens: list[str], end: int) -> int:
    for index in range(end, min(len(tokens), end + 6)):
        if tokens[index] in {"despues", "luego", "tambien", "ademas"}:
            return index
        if tokens[index] in {"y"} and index + 1 < len(tokens) and _token_looks_like_amount(tokens[index + 1]):
            return index
    return min(len(tokens), end + 5)


def _token_looks_like_amount(token: str) -> bool:
    return _parse_numeric_token(token) is not None or token in NUMBER_WORDS


def _deduplicate_segments(segments: list[MoneySegment]) -> list[MoneySegment]:
    result: list[MoneySegment] = []
    last_end = -1
    for segment in segments:
        if segment.start_token < last_end:
            continue
        result.append(segment)
        last_end = segment.end_token
    return result

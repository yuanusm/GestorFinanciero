"""Deterministic Spanish transaction parser for Chilean pesos."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from database import Transaction
from money_parser import MONEY_UNITS, NUMBER_WORDS, MoneySegment, extract_money_segments
from text_normalizer import normalize_text

LOGGER = logging.getLogger(__name__)

EXPENSE_KEYWORDS = (
    "compre",
    "compramos",
    "gaste",
    "gasto",
    "pague",
    "pago",
    "salio",
    "costo",
    "costaron",
    "pedi",
    "consumi",
    "encargue",
    "me compre",
)
INCOME_KEYWORDS = (
    "me transferi",  # common whisper error for "me transfirio"
    "me transfirio",
    "me transfirieron",
    "me pagaron",
    "recibi",
    "me devolvieron",
    "devolvieron",
    "depositaron",
    "me depositaron",
    "me dieron",
    "me ingresaron",
    "sueldo",
    "salario",
    "honorarios",
    "reembolsaron",
    "me reembolsaron",
    "ingreso",
)
# Outgoing transfers are expenses only when there is no leading "me" recipient cue.
OUTGOING_TRANSFER_KEYWORDS = ("transferi", "envie", "mande")
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "food": (
        "sushi",
        "cafe",
        "cafecito",
        "hamburguesa",
        "hamburguesas",
        "pan",
        "comida",
        "almuerzo",
        "cena",
        "desayuno",
        "restaurant",
        "restaurante",
        "supermercado",
    ),
    "transport": ("uber", "taxi", "metro", "bus", "micro", "bencina", "combustible", "peaje", "transporte"),
    "housing": ("arriendo", "dividendo", "gasto comun", "gastos comunes", "luz", "agua", "gas", "internet"),
    "health": ("farmacia", "doctor", "medico", "clinica", "isapre", "fonasa"),
    "entertainment": ("cine", "netflix", "spotify", "juego", "concierto", "bar"),
    "transfer": (
        "devolvieron",
        "transferencia",
        "transferi",
        "transfirio",
        "transfirieron",
        "depositaron",
        "prestamo",
        "reembolso",
    ),
    "salary": ("sueldo", "salario", "honorarios"),
}


@dataclass(frozen=True)
class ParsedTransaction:
    """A parsed transaction with deterministic confidence metadata."""

    transaction: Transaction
    confidence: float
    amount_segment: MoneySegment
    local_fragment: str
    transaction_type_confidence: float
    category_confidence: float


def parse_transactions(raw_text: str) -> list[ParsedTransaction]:
    """Parse one or more transactions from a Spanish financial phrase."""
    normalized = normalize_text(raw_text)
    segments = extract_money_segments(normalized)
    if not segments:
        LOGGER.warning("Could not parse any amount from transcription: %s", raw_text)
        return []

    parsed: list[ParsedTransaction] = []
    tokens = normalized.split()
    for segment in segments:
        context = _segment_context(tokens, segment)
        transaction_type, type_confidence = _extract_transaction_type(context, normalized)
        category, category_confidence = _extract_category(segment.description, context, transaction_type)
        description = _clean_description(segment.description, context)
        confidence = min(segment.confidence, type_confidence, category_confidence)
        parsed.append(
            ParsedTransaction(
                transaction=Transaction(
                    raw_text=raw_text,
                    amount_clp=segment.amount_clp,
                    transaction_type=transaction_type,
                    category=category,
                    description=description,
                ),
                confidence=confidence,
                amount_segment=segment,
                local_fragment=context,
                transaction_type_confidence=type_confidence,
                category_confidence=category_confidence,
            )
        )
    return parsed


def parse_transaction(raw_text: str) -> Transaction | None:
    """Backward-compatible helper returning the first parsed transaction, if any."""
    parsed = parse_transactions(raw_text)
    return parsed[0].transaction if parsed else None


def _segment_context(tokens: list[str], segment: MoneySegment) -> str:
    start = max(0, segment.start_token - 7)
    end = min(len(tokens), segment.end_token + 7)
    return " ".join(tokens[start:end])


def _extract_transaction_type(context: str, full_text: str) -> tuple[str, float]:
    context_has_income = any(keyword in context for keyword in INCOME_KEYWORDS)
    context_has_expense = any(keyword in context for keyword in EXPENSE_KEYWORDS) or _has_outgoing_transfer(context)
    if context_has_income and not context_has_expense:
        return "income", 0.96
    if context_has_expense and not context_has_income:
        return "expense", 0.96
    if context_has_income and context_has_expense:
        return "income", 0.55

    full_has_income = any(keyword in full_text for keyword in INCOME_KEYWORDS)
    full_has_expense = any(keyword in full_text for keyword in EXPENSE_KEYWORDS) or _has_outgoing_transfer(full_text)
    if full_has_income and not full_has_expense:
        return "income", 0.78
    if full_has_expense and not full_has_income:
        return "expense", 0.78
    if full_has_income and full_has_expense:
        return "expense", 0.55
    return "expense", 0.45


def _has_outgoing_transfer(text: str) -> bool:
    if any(income_phrase in text for income_phrase in ("me transfirio", "me transfirieron", "me transferi")):
        return False
    return any(keyword in text for keyword in OUTGOING_TRANSFER_KEYWORDS)


def _extract_category(description: str, context: str, transaction_type: str) -> tuple[str, float]:
    haystack = f"{description} {context}"
    haystack_tokens = set(haystack.split())
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(_keyword_matches(keyword, haystack, haystack_tokens) for keyword in keywords):
            return category, 0.95
    if transaction_type == "income":
        if any(keyword in haystack for keyword in ("sueldo", "salario", "honorarios")):
            return "salary", 0.95
        return "transfer", 0.85
    return "other", 0.50


def _keyword_matches(keyword: str, haystack: str, haystack_tokens: set[str]) -> bool:
    if " " in keyword:
        return keyword in haystack
    return keyword in haystack_tokens


def _clean_description(description: str, context: str) -> str:
    description = description.strip()
    if description and description != "sin descripcion":
        cleaned_description = _drop_noise_words(description)
        if cleaned_description:
            return cleaned_description
    stop_words = set(EXPENSE_KEYWORDS) | set(INCOME_KEYWORDS) | set(OUTGOING_TRANSFER_KEYWORDS) | {
        "por",
        "en",
        "de",
        "me",
        "mi",
        "y",
        "despues",
        "luego",
        "un",
        "una",
        "pesos",
        "peso",
        "clp",
    }
    words = [word for word in context.split() if word not in stop_words and not _is_amount_noise(word)]
    return " ".join(words).strip() or "sin descripcion"


def _drop_noise_words(text: str) -> str:
    return " ".join(word for word in text.split() if not _is_amount_noise(word)).strip()


def _is_amount_noise(word: str) -> bool:
    return word.replace(".", "").isdigit() or word in MONEY_UNITS or word in NUMBER_WORDS or word == "media"

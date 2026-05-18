"""Deterministic Spanish transaction parser for Chilean pesos."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from database import Transaction
from money_parser import MoneySegment, extract_money_segments
from text_normalizer import normalize_text

LOGGER = logging.getLogger(__name__)

EXPENSE_KEYWORDS = (
    "gaste",
    "pague",
    "compre",
    "compramos",
    "salio",
    "costo",
    "costaron",
    "transferi",
    "envie",
)
INCOME_KEYWORDS = (
    "recibi",
    "me pagaron",
    "me devolvieron",
    "devolvieron",
    "depositaron",
    "ingreso",
    "llego",
    "reembolsaron",
)
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "food": ("sushi", "hamburguesa", "hamburguesas", "pan", "comida", "almuerzo", "cena", "desayuno", "restaurant", "restaurante", "supermercado"),
    "transport": ("uber", "taxi", "metro", "bus", "bencina", "combustible", "peaje", "transporte"),
    "housing": ("arriendo", "dividendo", "gasto comun", "gastos comunes", "luz", "agua", "gas", "internet"),
    "health": ("farmacia", "doctor", "medico", "clinica", "isapre", "fonasa"),
    "entertainment": ("cine", "netflix", "spotify", "juego", "concierto", "bar"),
    "transfer": ("devolvieron", "transferencia", "transferi", "depositaron", "prestamo"),
    "salary": ("sueldo", "salario", "honorarios", "pago"),
}


@dataclass(frozen=True)
class ParsedTransaction:
    """A parsed transaction with deterministic confidence metadata."""

    transaction: Transaction
    confidence: float
    amount_segment: MoneySegment


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
            )
        )
    return parsed


def parse_transaction(raw_text: str) -> Transaction | None:
    """Backward-compatible helper returning the first parsed transaction, if any."""
    parsed = parse_transactions(raw_text)
    return parsed[0].transaction if parsed else None


def _segment_context(tokens: list[str], segment: MoneySegment) -> str:
    start = max(0, segment.start_token - 6)
    end = min(len(tokens), segment.end_token + 6)
    return " ".join(tokens[start:end])


def _extract_transaction_type(context: str, full_text: str) -> tuple[str, float]:
    if any(keyword in context for keyword in INCOME_KEYWORDS):
        return "income", 0.95
    if any(keyword in context for keyword in EXPENSE_KEYWORDS):
        return "expense", 0.95
    if any(keyword in full_text for keyword in INCOME_KEYWORDS):
        return "income", 0.75
    if any(keyword in full_text for keyword in EXPENSE_KEYWORDS):
        return "expense", 0.75
    return "expense", 0.45


def _extract_category(description: str, context: str, transaction_type: str) -> tuple[str, float]:
    haystack = f"{description} {context}"
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return category, 0.95
    if transaction_type == "income":
        return "transfer", 0.80
    return "other", 0.45


def _clean_description(description: str, context: str) -> str:
    description = description.strip()
    if description and description != "sin descripcion":
        return description
    stop_words = set(EXPENSE_KEYWORDS) | {"por", "en", "de", "me", "y", "despues", "luego"}
    words = [word for word in context.split() if word not in stop_words and not word.isdigit()]
    return " ".join(words).strip() or "sin descripcion"

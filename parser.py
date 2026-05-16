"""Deterministic Spanish transaction parser for Chilean pesos."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from database import Transaction

LOGGER = logging.getLogger(__name__)

EXPENSE_KEYWORDS = (
    "gasté",
    "gaste",
    "pagué",
    "pague",
    "compré",
    "compre",
    "salió",
    "salio",
    "me costó",
    "me costo",
)
INCOME_KEYWORDS = (
    "recibí",
    "recibi",
    "me pagaron",
    "me devolvieron",
    "depositaron",
    "ingresó",
    "ingreso",
    "transferencia recibida",
)
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "food": ("sushi", "comida", "almuerzo", "cena", "desayuno", "restaurant", "restaurante", "supermercado"),
    "transport": ("uber", "taxi", "metro", "bus", "bencina", "combustible", "peaje"),
    "housing": ("arriendo", "dividendo", "gasto común", "gastos comunes", "luz", "agua", "gas", "internet"),
    "health": ("farmacia", "doctor", "médico", "medico", "clínica", "clinica", "isapre", "fonasa"),
    "entertainment": ("cine", "netflix", "spotify", "juego", "concierto", "bar"),
    "transfer": ("devolvieron", "transferencia", "depositaron", "prestamo", "préstamo"),
    "salary": ("sueldo", "salario", "honorarios", "pago"),
}
AMOUNT_RE = re.compile(
    r"(?P<number>\d{1,3}(?:[\.]\d{3})*|\d+)(?:\s*(?P<unit>lucas?|mil|miles|k|pesos?|clp))?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParseResult:
    """Parsed transaction fields."""

    amount_clp: int
    transaction_type: str
    category: str
    description: str


def parse_transaction(raw_text: str) -> Transaction | None:
    """Parse a Spanish financial phrase into a transaction, or return None if no amount is found."""
    normalized = _normalize(raw_text)
    amount = _extract_amount(normalized)
    if amount is None:
        LOGGER.warning("Could not parse amount from transcription: %s", raw_text)
        return None

    transaction_type = _extract_transaction_type(normalized)
    category = _extract_category(normalized, transaction_type)
    description = _clean_description(normalized)
    result = ParseResult(
        amount_clp=amount,
        transaction_type=transaction_type,
        category=category,
        description=description,
    )
    return Transaction(raw_text=raw_text, **result.__dict__)


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _extract_amount(text: str) -> int | None:
    for match in AMOUNT_RE.finditer(text):
        number_text = match.group("number").replace(".", "")
        unit = (match.group("unit") or "").lower()
        try:
            number = int(number_text)
        except ValueError:
            continue
        if unit in {"luca", "lucas", "mil", "miles", "k"}:
            return number * 1000
        return number
    return None


def _extract_transaction_type(text: str) -> str:
    if any(keyword in text for keyword in INCOME_KEYWORDS):
        return "income"
    if any(keyword in text for keyword in EXPENSE_KEYWORDS):
        return "expense"
    return "expense"


def _extract_category(text: str, transaction_type: str) -> str:
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return category
    return "transfer" if transaction_type == "income" else "other"


def _clean_description(text: str) -> str:
    without_amount = AMOUNT_RE.sub("", text, count=1)
    stop_words = ("gasté", "gaste", "pagué", "pague", "compré", "compre", "en", "por", "me", "devolvieron")
    words = [word for word in without_amount.split() if word not in stop_words]
    return " ".join(words).strip() or text

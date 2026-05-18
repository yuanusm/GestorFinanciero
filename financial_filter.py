"""Lightweight financial relevance filter used before any local LLM fallback."""

from __future__ import annotations

import re

from text_normalizer import normalize_text

MONEY_RE = re.compile(r"\b\d+(?:[\.]\d{3})*(?:\s*(?:clp|peso|pesos|luca|lucas|mil|miles|k))?\b")
MONEY_WORDS = {
    "peso",
    "pesos",
    "clp",
    "luca",
    "lucas",
    "mil",
    "miles",
    "plata",
    "dinero",
}
SPENDING_VERBS = {
    "gaste",
    "pague",
    "compre",
    "compro",
    "compramos",
    "costo",
    "costaron",
    "sali",
    "salio",
    "transferi",
    "envie",
}
INCOME_VERBS = {
    "recibi",
    "devolvieron",
    "pagaron",
    "depositaron",
    "ingreso",
    "llego",
    "reembolsaron",
}
DASHBOARD_WORDS = {
    "dashboard",
    "resumen",
    "reporte",
    "informe",
    "grafico",
    "graficos",
    "historico",
    "historial",
    "semanal",
    "mensual",
}
FINANCIAL_NOUNS = {
    "gasto",
    "gastos",
    "ingreso",
    "ingresos",
    "egreso",
    "egresos",
    "cuenta",
    "presupuesto",
    "balance",
    "finanzas",
}


def is_financially_relevant(text: str) -> bool:
    """Return True only for text that is likely financial or dashboard-related."""
    normalized = normalize_text(text)
    if not normalized:
        return False
    tokens = set(normalized.split())
    if MONEY_RE.search(normalized) and tokens.intersection(MONEY_WORDS | SPENDING_VERBS | INCOME_VERBS | FINANCIAL_NOUNS):
        return True
    if tokens.intersection(MONEY_WORDS | SPENDING_VERBS | INCOME_VERBS | DASHBOARD_WORDS | FINANCIAL_NOUNS):
        return True
    if "me devolvieron" in normalized or "gastos semanales" in normalized or "gastos mensuales" in normalized:
        return True
    return False

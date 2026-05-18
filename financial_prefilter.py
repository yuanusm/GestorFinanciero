"""Financial pre-filter for offline Telegram messages.

This module keeps casual/non-financial messages away from Qwen and the database.
It accepts dashboard/report requests and transaction-like utterances that contain a
money amount or explicit financial verbs/nouns.
"""

from __future__ import annotations

import re

from money_parser import extract_money_segments
from text_normalizer import normalize_text

MONEY_RE = re.compile(r"\b\d+(?:[\.]\d{3})*(?:\s*(?:clp|peso|pesos|luca|lucas|gamba|gambas|palo|palos|mil|miles|k))?\b")
MONEY_WORDS = {
    "peso",
    "pesos",
    "clp",
    "luca",
    "lucas",
    "gamba",
    "gambas",
    "palo",
    "palos",
    "mil",
    "miles",
    "plata",
    "dinero",
}
SPENDING_VERBS = {
    "gaste",
    "gasto",
    "pague",
    "pago",
    "compre",
    "compro",
    "compramos",
    "costo",
    "costaron",
    "sali",
    "salio",
    "pedi",
    "consumi",
    "transferi",
    "envie",
    "mande",
}
INCOME_VERBS = {
    "recibi",
    "devolvieron",
    "pagaron",
    "depositaron",
    "transfirio",
    "transfirieron",
    "ingreso",
    "ingresaron",
    "llego",
    "reembolsaron",
    "sueldo",
    "salario",
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
    "diario",
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
    "transaccion",
    "transacciones",
}


def is_financially_relevant(text: str) -> bool:
    """Return True only for text that is likely financial or dashboard-related."""
    normalized = normalize_text(text)
    if not normalized:
        return False
    tokens = set(normalized.split())
    if tokens.intersection(DASHBOARD_WORDS):
        return True
    # Transaction creation requires at least one deterministic amount. This prevents
    # casual or incomplete phrases such as "compré sushi" from reaching Qwen or DB.
    if extract_money_segments(normalized):
        return True
    if MONEY_RE.search(normalized) and tokens.intersection(MONEY_WORDS | SPENDING_VERBS | INCOME_VERBS | FINANCIAL_NOUNS):
        return True
    return False

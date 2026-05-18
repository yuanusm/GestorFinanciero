"""Intent routing for Spanish Telegram text or transcribed voice commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from text_normalizer import normalize_text

IntentType = Literal["transaction", "report", "ignore"]
ReportPeriod = Literal["daily", "weekly", "monthly", "historical"]


@dataclass(frozen=True)
class Intent:
    """A simple deterministic intent classification."""

    intent_type: IntentType
    report_period: ReportPeriod | None = None
    confidence: float = 0.0


def route_intent(text: str) -> Intent:
    """Route a Spanish phrase to transaction storage, report generation, or ignore."""
    normalized = normalize_text(text)
    if not normalized:
        return Intent("ignore")

    report_words = ("dashboard", "resumen", "reporte", "informe", "grafico", "graficos", "muestrame", "mostrar")
    spending_report_phrases = ("como gaste", "cuanto gaste", "gastos semanales", "gastos mensuales", "mis gastos")
    if any(word in normalized for word in report_words) or any(phrase in normalized for phrase in spending_report_phrases):
        if any(word in normalized for word in ("historico", "historial", "todo", "total", "completo")):
            return Intent("report", "historical", 0.95)
        if any(word in normalized for word in ("mensual", "mensuales", "mes")):
            return Intent("report", "monthly", 0.95)
        if any(word in normalized for word in ("semanal", "semanales", "semana")):
            return Intent("report", "weekly", 0.95)
        return Intent("report", "daily", 0.80)
    return Intent("transaction", confidence=0.60)

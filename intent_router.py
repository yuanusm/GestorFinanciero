"""Intent routing for Spanish Telegram text or transcribed voice commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

IntentType = Literal["transaction", "report"]
ReportPeriod = Literal["daily", "weekly", "monthly", "historical"]


@dataclass(frozen=True)
class Intent:
    """A simple deterministic intent classification."""

    intent_type: IntentType
    report_period: ReportPeriod | None = None


def route_intent(text: str) -> Intent:
    """Route a Spanish phrase to transaction storage or report generation."""
    normalized = " ".join(text.lower().strip().split())
    if any(word in normalized for word in ("resumen", "reporte", "informe", "gráfico", "grafico")):
        if any(word in normalized for word in ("histórico", "historico", "todo", "total", "completo")):
            return Intent("report", "historical")
        if any(word in normalized for word in ("mensual", "mes")):
            return Intent("report", "monthly")
        if any(word in normalized for word in ("semanal", "semana")):
            return Intent("report", "weekly")
        return Intent("report", "daily")
    return Intent("transaction")

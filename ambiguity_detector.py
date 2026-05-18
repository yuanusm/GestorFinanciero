"""Determine whether deterministic parsing is good enough to avoid Qwen."""

from __future__ import annotations

from dataclasses import dataclass

from parser import ParsedTransaction


@dataclass(frozen=True)
class AmbiguityResult:
    """Ambiguity analysis for deterministic parsing."""

    needs_qwen: bool
    reason: str


def detect_ambiguity(parsed: list[ParsedTransaction], *, is_dashboard_intent: bool = False) -> AmbiguityResult:
    """Return whether optional local Qwen fallback is justified."""
    if is_dashboard_intent:
        return AmbiguityResult(False, "dashboard intent is deterministic")
    if not parsed:
        return AmbiguityResult(True, "no deterministic transaction parsed")
    for item in parsed:
        tx = item.transaction
        if item.confidence < 0.70:
            return AmbiguityResult(True, "low deterministic confidence")
        if item.transaction_type_confidence < 0.70 or tx.transaction_type not in {"expense", "income"}:
            return AmbiguityResult(True, "unclear transaction type")
        if tx.category == "other" and item.category_confidence < 0.70:
            return AmbiguityResult(True, "unclear category")
        if tx.description == "sin descripcion":
            return AmbiguityResult(True, "unclear description")
    return AmbiguityResult(False, "deterministic parsing is sufficient")

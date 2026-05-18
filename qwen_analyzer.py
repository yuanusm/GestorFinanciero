"""Optional local Qwen fallback executed through llama.cpp.

Qwen is never the primary parser. Callers must run the financial pre-filter,
deterministic parser, and ambiguity detector before using this module.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from typing import Any, Literal

from config import Settings

LOGGER = logging.getLogger(__name__)
VALID_TYPES = {"expense", "income"}
VALID_INTENTS = {"create_transaction", "dashboard", "ignore"}
ReportPeriod = Literal["daily", "weekly", "monthly", "historical"]


@dataclass(frozen=True)
class QwenTransaction:
    """One transaction proposed by the local fallback model."""

    amount_clp: int | None
    transaction_type: str | None
    category: str | None
    description: str | None


@dataclass(frozen=True)
class SemanticAnalysis:
    """Strict JSON output proposed by Qwen fallback."""

    intent: str | None
    transactions: list[QwenTransaction]
    report_period: ReportPeriod | None
    confidence: float


class QwenAnalysisError(RuntimeError):
    """Raised when the local Qwen runner fails unexpectedly."""


def analyze_with_qwen(text: str, settings: Settings) -> SemanticAnalysis | None:
    """Run local Qwen fallback with short output limits and parse strict JSON."""
    if not settings.qwen_enabled:
        LOGGER.info("Local Qwen fallback disabled")
        return None
    if not settings.qwen_runner_binary.exists() or not settings.qwen_model_path.exists():
        LOGGER.warning("Local Qwen runner/model missing; skipping fallback")
        return None

    command = [
        str(settings.qwen_runner_binary),
        "-m",
        str(settings.qwen_model_path),
        "-p",
        _build_prompt(text),
        "-n",
        str(settings.qwen_max_tokens),
        "-c",
        str(settings.qwen_context_tokens),
        "-t",
        str(settings.qwen_threads),
        "--temp",
        "0",
    ]
    LOGGER.info("Running local Qwen fallback")
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=settings.qwen_timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise QwenAnalysisError("Local Qwen fallback timed out") from exc
    except OSError as exc:
        raise QwenAnalysisError(f"Failed to execute local Qwen runner: {exc}") from exc

    if completed.returncode != 0:
        raise QwenAnalysisError(f"Local Qwen runner failed: {completed.stderr.strip()}")
    return _parse_semantic_json(completed.stdout)


def _build_prompt(text: str) -> str:
    return (
        "Responde SOLO JSON.\n"
        f"Texto:\n{json.dumps(text, ensure_ascii=False)}\n"
        "Formato:\n"
        "{\"intent\":\"create_transaction|dashboard|ignore\","
        "\"amount_clp\":12000,\"transaction_type\":\"expense\","
        "\"category\":\"food\",\"report_period\":null}"
    )


def _parse_semantic_json(output: str) -> SemanticAnalysis | None:
    payload = _extract_first_json_object(output)
    if payload is None:
        LOGGER.warning("Local Qwen output did not contain a JSON object")
        return None

    intent = payload.get("intent")
    transaction = _transaction_from_payload(payload)
    transactions_payload = payload.get("transactions")
    transactions: list[QwenTransaction] = []
    if isinstance(transactions_payload, list):
        transactions = [_transaction_from_payload(item) for item in transactions_payload if isinstance(item, dict)]
    elif transaction.amount_clp is not None or transaction.category is not None or transaction.transaction_type is not None:
        transactions = [transaction]

    report_period = payload.get("report_period")
    confidence = payload.get("confidence", 0.70 if intent in VALID_INTENTS else 0.0)
    return SemanticAnalysis(
        intent=intent if isinstance(intent, str) and intent in VALID_INTENTS else None,
        transactions=transactions,
        report_period=report_period if report_period in {"daily", "weekly", "monthly", "historical"} else None,
        confidence=float(confidence) if isinstance(confidence, int | float) else 0.0,
    )


def _transaction_from_payload(payload: dict[str, Any]) -> QwenTransaction:
    amount = payload.get("amount_clp")
    transaction_type = payload.get("transaction_type")
    category = payload.get("category")
    description = payload.get("description")
    return QwenTransaction(
        amount_clp=amount if isinstance(amount, int) and amount >= 0 else None,
        transaction_type=transaction_type if isinstance(transaction_type, str) and transaction_type in VALID_TYPES else None,
        category=category.strip() if isinstance(category, str) and category.strip() else None,
        description=description.strip() if isinstance(description, str) and description.strip() else None,
    )


def _extract_first_json_object(output: str) -> dict[str, Any] | None:
    start = output.find("{")
    end = output.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(output[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None

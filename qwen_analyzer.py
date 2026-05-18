"""Optional local Qwen semantic analysis executed through a local subprocess.

This module does not call cloud APIs. It expects a local CPU-capable runner, such
as `llama.cpp/build/bin/llama-cli`, and a locally downloaded Qwen GGUF model.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from typing import Any

from config import Settings

LOGGER = logging.getLogger(__name__)
VALID_TYPES = {"expense", "income"}


@dataclass(frozen=True)
class SemanticAnalysis:
    """Structured output proposed by the local semantic model."""

    amount_clp: int | None
    transaction_type: str | None
    category: str | None
    description: str | None
    confidence: float


class QwenAnalysisError(RuntimeError):
    """Raised when the local Qwen runner fails unexpectedly."""


def analyze_with_qwen(text: str, settings: Settings) -> SemanticAnalysis | None:
    """Run optional local Qwen analysis and parse its JSON response.

    Returns None when Qwen is disabled or unavailable, so the deterministic parser
    remains the primary low-RAM path.
    """
    if not settings.qwen_enabled:
        LOGGER.info("Local Qwen analysis disabled; using deterministic parser only")
        return None
    if not settings.qwen_runner_binary.exists() or not settings.qwen_model_path.exists():
        LOGGER.warning("Local Qwen runner/model missing; using deterministic parser only")
        return None

    prompt = _build_prompt(text)
    command = [
        str(settings.qwen_runner_binary),
        "-m",
        str(settings.qwen_model_path),
        "-p",
        prompt,
        "-n",
        str(settings.qwen_max_tokens),
        "-t",
        str(settings.qwen_threads),
        "--temp",
        "0",
    ]
    LOGGER.info("Running local Qwen semantic analysis")
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=settings.qwen_timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise QwenAnalysisError("Local Qwen semantic analysis timed out") from exc
    except OSError as exc:
        raise QwenAnalysisError(f"Failed to execute local Qwen runner: {exc}") from exc

    if completed.returncode != 0:
        raise QwenAnalysisError(f"Local Qwen runner failed: {completed.stderr.strip()}")

    return _parse_semantic_json(completed.stdout)


def _build_prompt(text: str) -> str:
    return (
        "Analiza esta frase financiera chilena y responde SOLO JSON válido. "
        "No agregues texto fuera del JSON. Campos: amount_clp entero o null, "
        "transaction_type 'expense' o 'income' o null, category string o null, "
        "description string o null, confidence número entre 0 y 1. "
        "Asume CLP si no se especifica moneda. Frase: "
        f"{json.dumps(text, ensure_ascii=False)}"
    )


def _parse_semantic_json(output: str) -> SemanticAnalysis | None:
    payload = _extract_first_json_object(output)
    if payload is None:
        LOGGER.warning("Local Qwen output did not contain a JSON object")
        return None

    amount = payload.get("amount_clp")
    transaction_type = payload.get("transaction_type")
    category = payload.get("category")
    description = payload.get("description")
    confidence = payload.get("confidence", 0)

    return SemanticAnalysis(
        amount_clp=amount if isinstance(amount, int) and amount >= 0 else None,
        transaction_type=transaction_type if isinstance(transaction_type, str) and transaction_type in VALID_TYPES else None,
        category=category.strip() if isinstance(category, str) and category.strip() else None,
        description=description.strip() if isinstance(description, str) and description.strip() else None,
        confidence=float(confidence) if isinstance(confidence, int | float) else 0.0,
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

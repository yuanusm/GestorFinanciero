"""Fusion layer combining deterministic parsing with optional local Qwen output."""

from __future__ import annotations

from database import Transaction
from qwen_analyzer import SemanticAnalysis



def fuse_transaction(raw_text: str, deterministic: Transaction | None, semantic: SemanticAnalysis | None) -> Transaction | None:
    """Create the final transaction while preferring deterministic parser values.

    The deterministic regex parser is authoritative for the amount when it found
    one. Local Qwen can fill missing fields or improve generic categories when it
    has enough confidence, but it cannot turn an existing parsed transaction into
    arbitrary SQL or commands.
    """
    if deterministic is None and semantic is None:
        return None
    if deterministic is None:
        return _transaction_from_semantic(raw_text, semantic)
    if semantic is None or semantic.confidence < 0.70:
        return deterministic

    category = deterministic.category
    if category in {"other", "transfer"} and semantic.category:
        category = semantic.category

    description = deterministic.description
    if description == raw_text.lower().strip() and semantic.description:
        description = semantic.description

    transaction_type = deterministic.transaction_type
    if semantic.transaction_type and deterministic.transaction_type == "expense":
        transaction_type = semantic.transaction_type

    return Transaction(
        raw_text=raw_text,
        amount_clp=deterministic.amount_clp,
        transaction_type=transaction_type,
        category=category,
        description=description,
        timestamp=deterministic.timestamp,
    )


def _transaction_from_semantic(raw_text: str, semantic: SemanticAnalysis | None) -> Transaction | None:
    if semantic is None or semantic.confidence < 0.80:
        return None
    if semantic.amount_clp is None or semantic.transaction_type is None:
        return None
    return Transaction(
        raw_text=raw_text,
        amount_clp=semantic.amount_clp,
        transaction_type=semantic.transaction_type,
        category=semantic.category or ("transfer" if semantic.transaction_type == "income" else "other"),
        description=semantic.description or raw_text,
    )

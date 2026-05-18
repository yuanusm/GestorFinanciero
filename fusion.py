"""Fusion helpers for deterministic parsing plus optional local Qwen fallback."""

from __future__ import annotations

from database import Transaction
from parser import ParsedTransaction
from qwen_analyzer import SemanticAnalysis


def fuse_transactions(raw_text: str, deterministic: list[ParsedTransaction], semantic: SemanticAnalysis | None) -> list[Transaction]:
    """Return final transactions while keeping deterministic parsing authoritative."""
    if not deterministic and semantic is None:
        return []
    if not deterministic:
        return _transactions_from_semantic(raw_text, semantic)
    if semantic is None or semantic.confidence < 0.70:
        return [item.transaction for item in deterministic]

    semantic_items = semantic.transactions
    fused: list[Transaction] = []
    for index, parsed in enumerate(deterministic):
        tx = parsed.transaction
        semantic_tx = semantic_items[index] if index < len(semantic_items) else None
        category = tx.category
        description = tx.description
        transaction_type = tx.transaction_type
        if semantic_tx is not None:
            if category == "other" and semantic_tx.category:
                category = semantic_tx.category
            if description == "sin descripcion" and semantic_tx.description:
                description = semantic_tx.description
            if parsed.confidence < 0.70 and semantic_tx.transaction_type:
                transaction_type = semantic_tx.transaction_type
        fused.append(
            Transaction(
                raw_text=raw_text,
                amount_clp=tx.amount_clp,
                transaction_type=transaction_type,
                category=category,
                description=description,
                timestamp=tx.timestamp,
            )
        )
    return fused


def fuse_transaction(raw_text: str, deterministic: Transaction | None, semantic: SemanticAnalysis | None) -> Transaction | None:
    """Backward-compatible single-transaction fusion helper."""
    if deterministic is not None:
        return deterministic
    transactions = _transactions_from_semantic(raw_text, semantic)
    return transactions[0] if transactions else None


def _transactions_from_semantic(raw_text: str, semantic: SemanticAnalysis | None) -> list[Transaction]:
    if semantic is None or semantic.confidence < 0.80 or semantic.intent != "create_transaction":
        return []
    transactions: list[Transaction] = []
    for item in semantic.transactions:
        if item.amount_clp is None or item.transaction_type is None:
            continue
        transactions.append(
            Transaction(
                raw_text=raw_text,
                amount_clp=item.amount_clp,
                transaction_type=item.transaction_type,
                category=item.category or ("transfer" if item.transaction_type == "income" else "other"),
                description=item.description or "sin descripcion",
            )
        )
    return transactions

"""Text normalization helpers for Chilean Spanish financial messages."""

from __future__ import annotations

import re
import unicodedata

SPACE_RE = re.compile(r"\s+")
# Keep dots inside numbers (12.500) and currency markers, remove noisy punctuation.
PUNCTUATION_RE = re.compile(r"[;:¡!¿?\(\)\[\]\{\}\"“”‘’]+")

SLANG_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\blukas\b"), " lucas "),
    (re.compile(r"\bluka\b"), " luca "),
    (re.compile(r"\blucas\b"), " lucas "),
    (re.compile(r"\bluca\b"), " luca "),
    (re.compile(r"\bgambas\b"), " gambas "),
    (re.compile(r"\bgamba\b"), " gamba "),
    (re.compile(r"\bpalos\b"), " palos "),
    (re.compile(r"\bpalo\b"), " palo "),
    (re.compile(r"\bpesitos\b"), " pesos "),
    (re.compile(r"\bpesito\b"), " peso "),
    (re.compile(r"\bclp\b"), " clp "),
)


def normalize_text(text: str, *, strip_accents: bool = True) -> str:
    """Normalize text before deterministic filtering and parsing.

    The normalizer is intentionally conservative: it lowercases, removes accents,
    cleans punctuation and duplicate spaces, and canonicalizes common Chilean money
    slang while preserving amount-bearing tokens such as ``12.500`` and ``2k``.
    """
    normalized = text.lower().strip()
    if strip_accents:
        normalized = remove_accents(normalized)
    normalized = normalized.replace("$", " pesos ")
    normalized = PUNCTUATION_RE.sub(" ", normalized)
    normalized = normalized.replace(",", ".")
    # Split compact k amounts (2k -> 2 k) for deterministic parsing.
    normalized = re.sub(r"\b(\d+(?:\.\d+)?)\s*k\b", r"\1 k", normalized)
    for pattern, replacement in SLANG_REPLACEMENTS:
        normalized = pattern.sub(replacement, normalized)
    return SPACE_RE.sub(" ", normalized).strip()


def remove_accents(text: str) -> str:
    """Return text without diacritics while keeping ASCII punctuation/numbers."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")

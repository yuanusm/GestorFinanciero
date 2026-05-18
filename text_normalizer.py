"""Text normalization helpers for Chilean Spanish financial messages."""

from __future__ import annotations

import re
import unicodedata

SPACE_RE = re.compile(r"\s+")
PUNCTUATION_RE = re.compile(r"[;:¡!¿?\(\)\[\]\{\}\"]+")
SLANG_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\blukas\b"), " lucas "),
    (re.compile(r"\bluka\b"), " luca "),
    (re.compile(r"\blucas\b"), " lucas "),
    (re.compile(r"\bluca\b"), " luca "),
    (re.compile(r"\bpesitos\b"), " pesos "),
    (re.compile(r"\bpesito\b"), " peso "),
    (re.compile(r"\bclp\b"), " clp "),
    (re.compile(r"\bgaste\b"), " gaste "),
    (re.compile(r"\bpague\b"), " pague "),
    (re.compile(r"\bcompre\b"), " compre "),
)


def normalize_text(text: str, *, strip_accents: bool = True) -> str:
    """Normalize text before deterministic filtering and parsing."""
    normalized = text.lower().strip()
    if strip_accents:
        normalized = remove_accents(normalized)
    normalized = PUNCTUATION_RE.sub(" ", normalized)
    normalized = normalized.replace("$", " pesos ")
    normalized = normalized.replace(",", ".")
    for pattern, replacement in SLANG_REPLACEMENTS:
        normalized = pattern.sub(replacement, normalized)
    return SPACE_RE.sub(" ", normalized).strip()


def remove_accents(text: str) -> str:
    """Return text without diacritics while keeping ASCII punctuation/numbers."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")

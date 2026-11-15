"""Backend text in the operator's language, set by ``DAYFOLD_LANGUAGE`` (``pt`` or ``en``).

This covers what the server writes for the dashboard: API error details, server side labels and
job log lines. The newspaper's own language is the ``newspaper.language`` setting and is
independent of this one, so an English dashboard can still publish a Portuguese paper.
"""

from __future__ import annotations

from .config import config


def language() -> str:
    return config.language


def tr(pt: str, en: str) -> str:
    """Pick the string for the configured language. Portuguese is the source language, so an
    unknown setting keeps the Portuguese text instead of leaving a message empty."""
    return en if config.language == "en" else pt

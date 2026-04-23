from __future__ import annotations

from loguru import logger

from app.storage.vocabulary import VocabularyStore


def build_hints(language: str | None, limit: int = 80) -> list[str]:
    terms = VocabularyStore().terms_for_language(language, limit=limit)
    if terms:
        logger.info("Using {} vocabulary hints for language {}", len(terms), language or "auto")
    return terms

"""Translation via deep-translator (Google Translate, no API key needed)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

_MAX_TRANSLATION_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 1.0
_PROVIDER_ERROR_MARKERS = (
    "error 500 (server error)",
    "that's an error",
    "there was an error. please try again later",
    "that's all we know",
)


def _looks_like_provider_error(text: str) -> bool:
    normalized = text.lower().replace("\u2019", "'")
    return any(marker in normalized for marker in _PROVIDER_ERROR_MARKERS)


def _translate_chunk(translator: Any, text: str) -> str:
    translated = str(translator.translate(text))
    if _looks_like_provider_error(translated):
        raise RuntimeError(f"Translation provider returned an error: {translated}")
    return translated


def _translate_chunk_with_retries(translator: Any, text: str) -> str:
    last_error: Exception | None = None
    for attempt in range(_MAX_TRANSLATION_ATTEMPTS):
        try:
            return _translate_chunk(translator, text)
        except Exception as e:
            last_error = e
            if attempt < _MAX_TRANSLATION_ATTEMPTS - 1:
                time.sleep(_RETRY_DELAY_SECONDS * (attempt + 1))

    if last_error is not None:
        raise last_error
    raise RuntimeError("Translation failed without an error")


def translate_text(
    text: str,
    target_lang: str,
    on_error: Callable[[Exception], None] | None = None,
) -> str:
    """Translate *text* to *target_lang* using Google Translate.

    Requires no API key. The deep-translator library queries Google
    Translate directly from the caller's network. An empty string or
    whitespace-only input is returned unchanged.
    """
    if not text or not text.strip():
        return text

    from deep_translator import GoogleTranslator  # type: ignore[import-untyped]

    try:
        translator = GoogleTranslator(source="auto", target=target_lang)
        # deep-translator has a 5000-character limit per call; split if needed.
        if len(text) <= 4900:
            return _translate_chunk_with_retries(translator, text)

        # Split long text by sentences to stay under the limit.
        chunks = _split_text(text, 4900)
        translated_chunks: list[str] = []
        for chunk in chunks:
            translated_chunks.append(_translate_chunk_with_retries(translator, chunk))
        return " ".join(translated_chunks)
    except Exception as e:
        if on_error is not None:
            on_error(e)
        # If translation fails for any reason, return the original text
        # so the pipeline continues without breaking.
        return text


def _split_text(text: str, max_len: int) -> list[str]:
    """Split *text* into chunks no longer than *max_len*, at sentence boundaries."""
    import re

    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current: str = ""

    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= max_len:
            current = f"{current} {sentence}".strip() if current else sentence
        else:
            if current:
                chunks.append(current)
            current = sentence if len(sentence) <= max_len else sentence[:max_len]

    if current:
        chunks.append(current)

    return chunks or [text[:max_len]]

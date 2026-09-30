"""Translation via deep-translator (Google Translate, no API key needed)."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any

_MAX_TRANSLATION_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 1.0
_RATE_LIMIT_RETRY_DELAY_SECONDS = 2.0

# Per-provider request size limits (deep-translator enforces these itself).
_GOOGLE_MAX_CHARS = 4900
# deep-translator validates MyMemory input with len(text) < 500.
_MYMEMORY_MAX_CHARS = 499

_PROVIDER_ERROR_MARKERS = (
    "error 500 (server error)",
    "that's an error",
    "there was an error. please try again later",
    "that's all we know",
    "too many requests",
)
_RATE_LIMIT_ERROR_MARKERS = ("too many requests",)
_MYMEMORY_TARGET_LOCALES = {
    "ar": "ar-SA",
    "de": "de-DE",
    "en": "en-US",
    "es": "es-ES",
    "fr": "fr-FR",
    "it": "it-IT",
    "ja": "ja-JP",
    "ko": "ko-KR",
    "pt": "pt-PT",
    "ru": "ru-RU",
    "tr": "tr-TR",
    "uk": "uk-UA",
    "zh": "zh-CN",
}


def _looks_like_provider_error(text: str) -> bool:
    normalized = text.lower().replace("\u2019", "'")
    return any(marker in normalized for marker in _PROVIDER_ERROR_MARKERS)


def _is_rate_limit_error(error: BaseException) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in _RATE_LIMIT_ERROR_MARKERS)


def _retry_delay_seconds(attempt: int, error: BaseException) -> float:
    if _is_rate_limit_error(error):
        return _RATE_LIMIT_RETRY_DELAY_SECONDS * (attempt + 1)
    return _RETRY_DELAY_SECONDS * (attempt + 1)


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
                time.sleep(_retry_delay_seconds(attempt, e))

    if last_error is not None:
        raise last_error
    raise RuntimeError("Translation failed without an error")


def _translate_chunked(translator: Any, text: str, max_chars: int) -> str:
    """Translate *text*, splitting it into chunks no longer than *max_chars*."""
    if len(text) <= max_chars:
        return _translate_chunk_with_retries(translator, text)
    return " ".join(
        _translate_chunk_with_retries(translator, chunk)
        for chunk in _split_text(text, max_chars)
    )


def _mymemory_target_locale(target_lang: str) -> str:
    lang = target_lang.strip()
    if not lang:
        return lang
    if "-" in lang:
        return lang
    return _MYMEMORY_TARGET_LOCALES.get(lang.lower(), lang)


def _translate_with_google(text: str, target_lang: str) -> str:
    from deep_translator import GoogleTranslator  # type: ignore[import-untyped]

    translator = GoogleTranslator(source="auto", target=target_lang)
    return _translate_chunked(translator, text, _GOOGLE_MAX_CHARS)


def _translate_with_mymemory(text: str, target_lang: str) -> str:
    from deep_translator import MyMemoryTranslator

    translator = MyMemoryTranslator(
        source="en-US",
        target=_mymemory_target_locale(target_lang),
    )
    return _translate_chunked(translator, text, _MYMEMORY_MAX_CHARS)


def _short_error(error: BaseException, limit: int = 200) -> str:
    message = str(error)
    if len(message) <= limit:
        return message
    return message[:limit] + "…"


def _translate_chunk_with_fallbacks(text: str, target_lang: str) -> str:
    errors: list[Exception] = []
    for provider in (_translate_with_google, _translate_with_mymemory):
        try:
            return provider(text, target_lang)
        except Exception as e:
            errors.append(e)

    messages = "; ".join(_short_error(error) for error in errors)
    raise RuntimeError(f"All translation providers failed: {messages}")


def translate_text(
    text: str,
    target_lang: str,
    on_error: Callable[[Exception], None] | None = None,
) -> str:
    """Translate *text* to *target_lang*, falling back from Google to MyMemory.

    Requires no API key. The deep-translator library queries the providers
    directly from the caller's network. An empty string or whitespace-only
    input is returned unchanged, and a total failure returns the original text.
    """
    if not text or not text.strip():
        return text

    try:
        return _translate_chunk_with_fallbacks(text, target_lang)
    except Exception as e:
        if on_error is not None:
            on_error(e)
        # If translation fails for any reason, return the original text
        # so the pipeline continues without breaking.
        return text


def _split_text(text: str, max_len: int) -> list[str]:
    """Split *text* into chunks no longer than *max_len*, at sentence boundaries.

    Sentences longer than *max_len* are additionally hard-split so no content
    is dropped.
    """
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current: str = ""

    for sentence in sentences:
        for piece in _hard_split(sentence, max_len):
            if not current:
                current = piece
            elif len(current) + len(piece) + 1 <= max_len:
                current = f"{current} {piece}"
            else:
                chunks.append(current)
                current = piece

    if current:
        chunks.append(current)

    return chunks or [text[:max_len]]


def _hard_split(sentence: str, max_len: int) -> list[str]:
    """Split a single sentence into pieces no longer than *max_len*."""
    if len(sentence) <= max_len:
        return [sentence]
    return [sentence[i : i + max_len] for i in range(0, len(sentence), max_len)]

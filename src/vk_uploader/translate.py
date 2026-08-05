"""Translation via deep-translator (Google Translate, no API key needed)."""

from __future__ import annotations

from collections.abc import Callable


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
            return str(translator.translate(text))

        # Split long text by sentences to stay under the limit.
        chunks = _split_text(text, 4900)
        translated = [str(translator.translate(chunk)) for chunk in chunks]
        return " ".join(translated)
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

"""Tests for translate.py."""

from __future__ import annotations

from vk_uploader.translate import translate_text


def test_empty_text_returns_empty():
    assert translate_text("", "ru") == ""
    assert translate_text("   ", "ru") == "   "


def test_translate_returns_string(mocker):
    mocker.patch(
        "deep_translator.GoogleTranslator.translate",
        return_value="Привет, мир",
    )

    result = translate_text("Hello world", "ru")
    assert result == "Привет, мир"
    assert isinstance(result, str)


def test_translate_splits_long_text(mocker):
    mocker.patch(
        "deep_translator.GoogleTranslator.translate",
        return_value="Перевод",
    )

    long_text = "A. " * 3000
    result = translate_text(long_text, "ru")
    assert isinstance(result, str)
    assert len(result) > 0


def test_translate_failure_returns_original(mocker):
    mocker.patch(
        "deep_translator.GoogleTranslator.translate",
        side_effect=Exception("Network error"),
    )

    result = translate_text("Hello world", "ru")
    assert result == "Hello world"


def test_translate_failure_calls_error_callback(mocker):
    error = RuntimeError("Network error")
    mocker.patch(
        "deep_translator.GoogleTranslator.translate",
        side_effect=error,
    )
    on_error = mocker.MagicMock()

    result = translate_text("Hello world", "ru", on_error=on_error)

    assert result == "Hello world"
    on_error.assert_called_once_with(error)

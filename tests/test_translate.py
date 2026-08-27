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


def test_google_failure_falls_back_to_mymemory(mocker):
    provider_error = (
        "Error 500 (Server Error)!!1500.That’s an error."
        "There was an error. Please try again later.That’s all we know."
    )
    sleep = mocker.patch("vk_uploader.translate.time.sleep")
    google_translate = mocker.patch(
        "deep_translator.GoogleTranslator.translate",
        return_value=provider_error,
    )
    mymemory_translate = mocker.patch(
        "deep_translator.MyMemoryTranslator.translate",
        return_value="Привет, мир",
    )

    result = translate_text("Hello world", "ru")

    assert result == "Привет, мир"
    assert google_translate.call_count == 3
    mymemory_translate.assert_called_once()
    assert sleep.call_count == 2


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
    mocker.patch("vk_uploader.translate.time.sleep")
    mocker.patch(
        "deep_translator.GoogleTranslator.translate",
        side_effect=Exception("Network error"),
    )
    mocker.patch(
        "deep_translator.MyMemoryTranslator.translate",
        side_effect=Exception("Fallback network error"),
    )

    result = translate_text("Hello world", "ru")
    assert result == "Hello world"


def test_translate_failure_calls_error_callback(mocker):
    error = RuntimeError("Network error")
    mocker.patch("vk_uploader.translate.time.sleep")
    mocker.patch(
        "deep_translator.GoogleTranslator.translate",
        side_effect=error,
    )
    mocker.patch(
        "deep_translator.MyMemoryTranslator.translate",
        side_effect=RuntimeError("Fallback error"),
    )
    on_error = mocker.MagicMock()

    result = translate_text("Hello world", "ru", on_error=on_error)

    assert result == "Hello world"
    on_error.assert_called_once()
    assert "All translation providers failed" in str(on_error.call_args.args[0])


def test_provider_error_body_returns_original_when_fallback_fails(mocker):
    mocker.patch("vk_uploader.translate.time.sleep")
    provider_error = (
        "Error 500 (Server Error)!!1500.That’s an error."
        "There was an error. Please try again later.That’s all we know."
    )
    mocker.patch(
        "deep_translator.GoogleTranslator.translate",
        return_value=provider_error,
    )
    mocker.patch(
        "deep_translator.MyMemoryTranslator.translate",
        side_effect=RuntimeError("Fallback error"),
    )
    on_error = mocker.MagicMock()

    result = translate_text("Hello world", "ru", on_error=on_error)

    assert result == "Hello world"
    on_error.assert_called_once()
    assert "Translation provider returned an error" in str(on_error.call_args.args[0])


def test_provider_error_body_is_retried(mocker):
    provider_error = (
        "Error 500 (Server Error)!!1500.That’s an error."
        "There was an error. Please try again later.That’s all we know."
    )
    sleep = mocker.patch("vk_uploader.translate.time.sleep")
    translate = mocker.patch(
        "deep_translator.GoogleTranslator.translate",
        side_effect=[provider_error, "Привет, мир"],
    )
    mymemory_translate = mocker.patch("deep_translator.MyMemoryTranslator.translate")

    result = translate_text("Hello world", "ru")

    assert result == "Привет, мир"
    assert translate.call_count == 2
    mymemory_translate.assert_not_called()
    sleep.assert_called_once_with(1.0)

"""Tests for translate.py."""

from __future__ import annotations

import pytest

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


def test_mymemory_fallback_chunks_long_text(mocker):
    mocker.patch("vk_uploader.translate.time.sleep")
    mocker.patch(
        "deep_translator.GoogleTranslator.translate",
        side_effect=Exception("rate limited"),
    )
    mymemory_translate = mocker.patch(
        "deep_translator.MyMemoryTranslator.translate",
        return_value="Перевод",
    )

    long_text = "Hello world. " * 60  # 780 characters
    result = translate_text(long_text, "ru")

    assert result
    assert mymemory_translate.call_count >= 2
    for call in mymemory_translate.call_args_list:
        assert len(call.args[0]) < 500


@pytest.mark.parametrize("length", [499, 500, 501, 998, 1000, 1200])
def test_mymemory_fallback_respects_real_length_validation(mocker, length):
    mocker.patch("vk_uploader.translate.time.sleep")
    mocker.patch(
        "deep_translator.GoogleTranslator.translate",
        side_effect=RuntimeError("Google unavailable"),
    )
    response = mocker.Mock(status_code=200)
    response.json.return_value = {"responseData": {"translatedText": "Перевод"}}
    sent_chunks = []

    def request(url, *, params, proxies):
        # Capture each payload now: the translator reuses its params dictionary.
        sent_chunks.append(params["q"])
        return response

    # Keep MyMemory.translate and its input validation real; mock only HTTP.
    mocker.patch("deep_translator.mymemory.requests.get", side_effect=request)
    on_error = mocker.Mock()
    text = "A" * length

    result = translate_text(text, "ru", on_error=on_error)

    on_error.assert_not_called()
    assert sent_chunks
    assert all(0 < len(chunk) < 500 for chunk in sent_chunks)
    assert "".join(sent_chunks) == text
    assert result == " ".join("Перевод" for _ in sent_chunks)


def test_rate_limit_uses_longer_backoff(mocker):
    from deep_translator.exceptions import TooManyRequests

    sleep = mocker.patch("vk_uploader.translate.time.sleep")
    mocker.patch(
        "deep_translator.GoogleTranslator.translate",
        side_effect=TooManyRequests(),
    )
    mocker.patch(
        "deep_translator.MyMemoryTranslator.translate",
        return_value="Перевод",
    )

    translate_text("Hello world", "ru")

    assert sleep.call_count == 2
    sleep.assert_has_calls([mocker.call(2.0), mocker.call(4.0)])


def test_split_text_preserves_content_for_long_sentences():
    from vk_uploader.translate import _split_text

    text = "A" * 1200  # a single sentence with no punctuation
    chunks = _split_text(text, 500)

    assert all(len(chunk) <= 500 for chunk in chunks)
    assert "".join(chunks) == text

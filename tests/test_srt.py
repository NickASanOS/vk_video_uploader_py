"""Tests for srt.py."""

from __future__ import annotations

from pathlib import Path

from vk_uploader.srt import (
    SRTEntry,
    parse_srt,
    translate_srt_entries,
    write_srt,
)


class TestParseSrt:
    def test_parses_basic_srt(self, tmp_path: Path):
        p = tmp_path / "test.srt"
        p.write_text("1\n00:00:01,000 --> 00:00:04,000\nHello world\n\n")

        entries = parse_srt(p)
        assert len(entries) == 1
        assert entries[0].index == 1
        assert entries[0].start == "00:00:01,000"
        assert entries[0].end == "00:00:04,000"
        assert entries[0].text == "Hello world"

    def test_parses_multiline_text(self, tmp_path: Path):
        p = tmp_path / "test.srt"
        p.write_text(
            "1\n00:00:01,000 --> 00:00:04,000\nLine one\nLine two\n\n"
            "2\n00:00:05,000 --> 00:00:08,000\nLine three\n\n"
        )

        entries = parse_srt(p)
        assert len(entries) == 2
        assert entries[0].text == "Line one\nLine two"
        assert entries[1].text == "Line three"

    def test_parses_crlf_srt(self, tmp_path: Path):
        p = tmp_path / "crlf.srt"
        p.write_text(
            "1\r\n00:00:01,000 --> 00:00:04,000\r\nLine one\r\nLine two\r\n\r\n"
            "2\r\n00:00:05,000 --> 00:00:08,000\r\nLine three\r\n\r\n"
        )

        entries = parse_srt(p)

        assert len(entries) == 2
        assert entries[0].text == "Line one\nLine two"
        assert entries[1].text == "Line three"

    def test_parses_empty_file(self, tmp_path: Path):
        p = tmp_path / "empty.srt"
        p.write_text("\n\n")

        entries = parse_srt(p)
        assert entries == []

    def test_skips_malformed_blocks(self, tmp_path: Path):
        p = tmp_path / "test.srt"
        p.write_text(
            "1\n00:00:01,000 --> 00:00:04,000\nGood entry\n\n"
            "bad_block\n\n"
            "3\n00:00:10,000 --> 00:00:15,000\nAnother good\n\n"
        )

        entries = parse_srt(p)
        assert len(entries) == 2
        assert entries[0].text == "Good entry"
        assert entries[1].text == "Another good"


class TestWriteSrt:
    def test_roundtrip(self, tmp_path: Path):
        original = [
            SRTEntry(index=1, start="00:00:01,000", end="00:00:04,000", text="Hello"),
            SRTEntry(index=2, start="00:00:05,000", end="00:00:08,000", text="World"),
        ]
        p = tmp_path / "roundtrip.srt"
        write_srt(original, p)

        parsed = parse_srt(p)
        assert len(parsed) == 2
        assert parsed[0] == original[0]
        assert parsed[1] == original[1]

    def test_preserves_multiline_text(self, tmp_path: Path):
        original = [
            SRTEntry(index=1, start="00:00:01,000", end="00:00:04,000", text="A\nB\nC"),
        ]
        p = tmp_path / "multiline.srt"
        write_srt(original, p)

        parsed = parse_srt(p)
        assert parsed[0].text == "A\nB\nC"


class TestTranslateSrtEntries:
    def test_translates_non_empty_entries(self, mocker):
        mocker.patch(
            "vk_uploader.srt.translate_text",
            side_effect=lambda t, lang: t.upper(),
        )
        entries = [
            SRTEntry(index=1, start="00:00:01,000", end="00:00:04,000", text="hello"),
            SRTEntry(index=2, start="00:00:05,000", end="00:00:08,000", text="world"),
        ]

        result = translate_srt_entries(entries, "ru")
        assert result[0].text == "HELLO"
        assert result[1].text == "WORLD"

    def test_preserves_timestamps_after_translation(self, mocker):
        mocker.patch(
            "vk_uploader.srt.translate_text",
            return_value="перевод",
        )
        entries = [
            SRTEntry(index=1, start="00:00:01,500", end="00:00:04,000", text="original"),
        ]

        result = translate_srt_entries(entries, "ru")
        assert result[0].index == 1
        assert result[0].start == "00:00:01,500"
        assert result[0].end == "00:00:04,000"

    def test_empty_texts_pass_through(self, mocker):
        mocker.patch("vk_uploader.srt.translate_text")
        entries = [
            SRTEntry(index=1, start="00:00:01,000", end="00:00:04,000", text="hello"),
            SRTEntry(index=2, start="00:00:05,000", end="00:00:08,000", text=""),
            SRTEntry(index=3, start="00:00:09,000", end="00:00:12,000", text="  "),
        ]

        result = translate_srt_entries(entries, "ru")
        assert result[0].text != "hello"  # translated
        assert result[1].text == ""  # unchanged
        assert result[2].text == "  "  # unchanged

    def test_batching_handles_many_entries(self, mocker):
        # Create 200 entries — enough to trigger batching.
        entries = []
        for i in range(200):
            text = f"This is subtitle entry number {i} with some content."
            entries.append(
                SRTEntry(
                    index=i + 1,
                    start="00:00:01,000",
                    end="00:00:04,000",
                    text=text,
                )
            )

        def fake_translate(text: str, lang: str) -> str:
            # Return uppercase to verify translation happened.
            return text.upper()

        mocker.patch("vk_uploader.srt.translate_text", side_effect=fake_translate)

        result = translate_srt_entries(entries, "ru")
        assert len(result) == 200
        for i, e in enumerate(result):
            assert e.text == entries[i].text.upper()
            assert e.start == entries[i].start
            assert e.end == entries[i].end

    def test_fallback_to_individual_on_split_mismatch(self, mocker):
        """If the separator gets mangled, fall back to individual translation."""
        call_count = 0

        def fake_translate(text: str, lang: str) -> str:
            nonlocal call_count
            call_count += 1
            # First call (batched): return a mangled result.
            # Subsequent calls (individual): return properly.
            if call_count == 1:
                return "mangled result without separator"
            return f"[{text}]"

        mocker.patch("vk_uploader.srt.translate_text", side_effect=fake_translate)

        entries = [
            SRTEntry(index=1, start="00:00:01,000", end="00:00:04,000", text="first"),
            SRTEntry(index=2, start="00:00:05,000", end="00:00:08,000", text="second"),
        ]

        result = translate_srt_entries(entries, "ru")
        assert len(result) == 2
        # Individual fallback: each text wrapped in brackets.
        assert result[0].text == "[first]"
        assert result[1].text == "[second]"

    def test_bare_separator_text_does_not_split_batch(self, mocker):
        """A literal [TSRT] in subtitle text is not the internal separator."""
        mock_translate = mocker.patch(
            "vk_uploader.srt.translate_text",
            side_effect=lambda text, lang: text,
        )
        entries = [
            SRTEntry(
                index=1,
                start="00:00:01,000",
                end="00:00:04,000",
                text="literal [TSRT] marker",
            ),
            SRTEntry(index=2, start="00:00:05,000", end="00:00:08,000", text="second"),
        ]

        result = translate_srt_entries(entries, "ru")

        assert result[0].text == "literal [TSRT] marker"
        assert result[1].text == "second"
        assert mock_translate.call_count == 1

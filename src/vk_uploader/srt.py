"""SRT subtitle file parsing, writing, and translation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from vk_uploader.translate import translate_text


@dataclass
class SRTEntry:
    index: int
    start: str  # "00:00:01,000"
    end: str  # "00:00:04,000"
    text: str  # may be multiline


_TIMESTAMP_RE = re.compile(
    r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})"
)


def parse_srt(file_path: Path) -> list[SRTEntry]:
    """Parse an SRT file into a list of SRTEntry objects."""
    content = file_path.read_text(encoding="utf-8")
    blocks = content.strip().split("\n\n")
    entries: list[SRTEntry] = []

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 2:
            continue

        # Line 0: index
        try:
            index = int(lines[0].strip())
        except ValueError:
            continue

        # Line 1: timestamp
        m = _TIMESTAMP_RE.search(lines[1])
        if not m:
            continue
        start, end = m.group(1), m.group(2)

        # Remaining lines: text
        text = "\n".join(lines[2:])

        entries.append(SRTEntry(index=index, start=start, end=end, text=text))

    return entries


def write_srt(entries: list[SRTEntry], file_path: Path) -> None:
    """Write SRT entries to a file."""
    blocks = []
    for e in entries:
        blocks.append(f"{e.index}\n{e.start} --> {e.end}\n{e.text}")
    file_path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


_TSRT_SEP = "\n\n[TSRT]\n\n"


def translate_srt_entries(
    entries: list[SRTEntry], target_lang: str
) -> list[SRTEntry]:
    """Translate SRT entries, preserving timestamps. Batches to stay under API limit.

    Empty-text entries pass through unchanged.
    """
    # Separate empty and non-empty entries.
    non_empty: list[tuple[int, SRTEntry]] = []
    result: list[SRTEntry] = []

    for i, e in enumerate(entries):
        if e.text.strip():
            non_empty.append((i, e))
            result.append(SRTEntry(0, e.start, e.end, ""))  # placeholder
        else:
            result.append(SRTEntry(e.index, e.start, e.end, e.text))

    if not non_empty:
        return result

    # Batch non-empty entries under ~4000 chars.
    batches: list[list[SRTEntry]] = []
    current_batch: list[SRTEntry] = []
    current_len = 0

    for _, e in non_empty:
        entry_len = len(e.text) + len(_TSRT_SEP)
        if current_len + entry_len > 4000 and current_batch:
            batches.append(current_batch)
            current_batch = []
            current_len = 0
        current_batch.append(e)
        current_len += entry_len

    if current_batch:
        batches.append(current_batch)

    # Translate each batch.
    translated: list[SRTEntry] = []
    for batch in batches:
        combined = _TSRT_SEP.join(e.text for e in batch)
        translated_text = translate_text(combined, target_lang)

        # Split back.
        parts = translated_text.split(_TSRT_SEP.strip())
        if len(parts) == len(batch):
            for e, part in zip(batch, parts, strict=True):
                translated.append(SRTEntry(e.index, e.start, e.end, part.strip()))
        else:
            # Batch split mismatch — translate individually.
            for e in batch:
                t = translate_text(e.text, target_lang)
                translated.append(SRTEntry(e.index, e.start, e.end, t))

    # Fill translated entries back into result.
    for (i, _), te in zip(non_empty, translated, strict=True):
        result[i] = te

    return result

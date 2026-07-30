from __future__ import annotations

from dataclasses import dataclass
import re


_HARD_BREAK = re.compile(r"(?:\r\n|\r|\n)[ \t]*(?:\r\n|\r|\n)")


@dataclass(frozen=True)
class EvidenceAlignment:
    raw_start: int
    raw_end: int
    excerpt: str


@dataclass(frozen=True)
class EvidenceTextView:
    text: str
    raw_ranges: tuple[tuple[int, int], ...]

    def align(self, quote: str, raw_text: str) -> EvidenceAlignment | None:
        if not quote or quote != quote.strip() or _HARD_BREAK.search(quote):
            return None
        start = self.text.find(quote)
        while start >= 0:
            end = start + len(quote)
            raw_start = self.raw_ranges[start][0]
            raw_end = self.raw_ranges[end - 1][1]
            excerpt = raw_text[raw_start:raw_end]
            if not _HARD_BREAK.search(excerpt):
                return EvidenceAlignment(raw_start=raw_start, raw_end=raw_end, excerpt=excerpt)
            start = self.text.find(quote, start + 1)
        return None


def evidence_text_view(raw_text: str) -> EvidenceTextView:
    """Build the single model/compiler view of a persisted Raw unit."""

    characters: list[str] = []
    ranges: list[tuple[int, int]] = []
    offset = 0
    while offset < len(raw_text):
        character = raw_text[offset]
        if character not in {"\r", "\n"}:
            characters.append(character)
            ranges.append((offset, offset + 1))
            offset += 1
            continue

        break_start = offset
        line_breaks = 0
        while offset < len(raw_text):
            if raw_text.startswith("\r\n", offset):
                offset += 2
                line_breaks += 1
            elif raw_text[offset] in {"\r", "\n"}:
                offset += 1
                line_breaks += 1
            else:
                break
            while offset < len(raw_text) and raw_text[offset] in {" ", "\t"}:
                offset += 1

        if line_breaks > 1:
            for raw_offset in range(break_start, offset):
                characters.append(raw_text[raw_offset])
                ranges.append((raw_offset, raw_offset + 1))
            continue

        left = raw_text[break_start - 1] if break_start else ""
        right = raw_text[offset] if offset < len(raw_text) else ""
        if not left or not right:
            for raw_offset in range(break_start, offset):
                characters.append(raw_text[raw_offset])
                ranges.append((raw_offset, raw_offset + 1))
        elif _is_structural_line_start(raw_text, offset):
            for raw_offset in range(break_start, offset):
                characters.append(raw_text[raw_offset])
                ranges.append((raw_offset, raw_offset + 1))
        elif _east_asian_attached_boundary(left, right):
            continue
        else:
            characters.append(" ")
            ranges.append((break_start, offset))

    return EvidenceTextView(text="".join(characters), raw_ranges=tuple(ranges))


def canonical_evidence_text(raw_text: str) -> str:
    return evidence_text_view(raw_text).text


def align_evidence_quote(raw_text: str, quote: str) -> EvidenceAlignment | None:
    return evidence_text_view(raw_text).align(quote, raw_text)


def _east_asian_attached_boundary(left: str, right: str) -> bool:
    return (_is_east_asian_script(left) or _is_east_asian_script(right)) and not (
        left.isspace() or right.isspace()
    )


def _is_structural_line_start(raw_text: str, offset: int) -> bool:
    remainder = raw_text[offset:]
    return bool(re.match(r"(?:#{1,6}\s|[-+*>]\s|\d+[.)]\s|\||```|~~~)", remainder))


def _is_east_asian_script(character: str) -> bool:
    codepoint = ord(character)
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
        or 0x3040 <= codepoint <= 0x30FF
        or 0xAC00 <= codepoint <= 0xD7AF
    )

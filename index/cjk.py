"""CJK token helpers for V1 grep-style search."""

from __future__ import annotations


def contains_cjk(value: str) -> bool:
    return any(_is_cjk(char) for char in value)


def cjk_bigrams(value: str) -> set[str]:
    """Return overlapping CJK bigrams after dropping non-CJK separators."""

    chars = [char for char in value if _is_cjk(char)]
    return {chars[index] + chars[index + 1] for index in range(len(chars) - 1)}


def cjk_bigram_match(query: str, text: str) -> bool:
    query_bigrams = cjk_bigrams(query)
    if not query_bigrams:
        return False
    text_bigrams = cjk_bigrams(text)
    overlap = len(query_bigrams & text_bigrams)
    required = max(1, (len(query_bigrams) + 1) // 2)
    return overlap >= required


def _is_cjk(char: str) -> bool:
    codepoint = ord(char)
    return (
        0x4E00 <= codepoint <= 0x9FFF
        or 0x3400 <= codepoint <= 0x4DBF
        or 0xF900 <= codepoint <= 0xFAFF
    )

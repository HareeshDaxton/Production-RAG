"""Token counting for chunk sizing / context budgeting (tiktoken)."""
from __future__ import annotations

from functools import lru_cache


@lru_cache
def _encoder():
    import tiktoken

    # cl100k is a fine, stable choice for length estimation across chat models.
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoder().encode(text))


def split_by_tokens(text: str, max_tokens: int, overlap: int) -> list[str]:
    """Split raw text into token windows of <= max_tokens with `overlap` token overlap."""
    enc = _encoder()
    ids = enc.encode(text)
    if len(ids) <= max_tokens:
        return [text]
    step = max(1, max_tokens - overlap)
    windows: list[str] = []
    for start in range(0, len(ids), step):
        piece = ids[start : start + max_tokens]
        if not piece:
            break
        windows.append(enc.decode(piece))
        if start + max_tokens >= len(ids):
            break
    return windows

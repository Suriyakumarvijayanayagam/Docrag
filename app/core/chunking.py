"""
Recursive chunking: split on paragraph -> sentence -> word boundaries,
never mid-sentence unless forced. Token count approximated by whitespace
split (good enough for chunk sizing, not for billing).
"""
import re

SEPARATORS = ["\n\n", "\n", ". ", " "]


def _approx_tokens(text: str) -> int:
    return len(text.split())


def _split_on(text: str, sep: str) -> list[str]:
    parts = text.split(sep)
    return [p + sep if i < len(parts) - 1 else p for i, p in enumerate(parts)]


def _recursive_split(text: str, max_tokens: int, seps: list[str]) -> list[str]:
    if _approx_tokens(text) <= max_tokens or not seps:
        return [text]

    sep, rest_seps = seps[0], seps[1:]
    pieces = _split_on(text, sep)

    chunks, buf = [], ""
    for piece in pieces:
        if _approx_tokens(buf + piece) <= max_tokens:
            buf += piece
        else:
            if buf:
                chunks.append(buf)
            if _approx_tokens(piece) > max_tokens:
                chunks.extend(_recursive_split(piece, max_tokens, rest_seps))
                buf = ""
            else:
                buf = piece
    if buf:
        chunks.append(buf)
    return chunks


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """
    Splits text into chunks of ~chunk_size tokens, with ~overlap tokens
    repeated at the start of each chunk (except the first) for context continuity.
    """
    raw_chunks = _recursive_split(text.strip(), chunk_size, SEPARATORS)
    raw_chunks = [c.strip() for c in raw_chunks if c.strip()]

    if overlap <= 0 or len(raw_chunks) <= 1:
        return raw_chunks

    overlapped = [raw_chunks[0]]
    for i in range(1, len(raw_chunks)):
        prev_words = raw_chunks[i - 1].split()
        carry = " ".join(prev_words[-overlap:]) if len(prev_words) > overlap else raw_chunks[i - 1]
        overlapped.append((carry + " " + raw_chunks[i]).strip())
    return overlapped


def chunk_document(pages: list[dict], chunk_size: int, overlap: int, unit_key: str) -> list[dict]:
    """
    pages: list of {"page"/"section": N, "text": "..."}
    unit_key: "page" or "section" - which key to preserve as source locator.
    Returns list of {"text": ..., unit_key: N, "chunk_index": M}
    """
    results = []
    for unit in pages:
        chunks = chunk_text(unit["text"], chunk_size, overlap)
        for idx, c in enumerate(chunks):
            results.append({
                "text": c,
                unit_key: unit[unit_key],
                "chunk_index": idx,
            })
    return results

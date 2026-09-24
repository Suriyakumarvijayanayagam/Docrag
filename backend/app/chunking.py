import re
from dataclasses import dataclass

@dataclass
class TextBlock:
    text: str
    page: int | None = None
    section: str = ""


@dataclass
class Chunk:
    content: str
    token_count: int
    page_start: int | None
    page_end: int | None
    section: str


def token_count(text: str) -> int:
    """Local conservative token estimate; never downloads a tokenizer at runtime."""
    pieces = re.findall(r"\w+|[^\w\s]", text)
    count = 0
    for piece in pieces:
        if piece.isalnum() or "_" in piece:
            count += max(1, (len(piece) + 5) // 6)
        else:
            count += 1
    return max(1, count)


def _split_oversized(text: str, max_tokens: int, overlap: int) -> list[str]:
    if token_count(text) <= max_tokens:
        return [text]
    words = text.split()
    result: list[str] = []
    start = 0
    while start < len(words):
        end = start
        while end < len(words) and token_count(" ".join(words[start:end + 1])) <= max_tokens:
            end += 1
        if end == start:
            end += 1
        result.append(" ".join(words[start:end]))
        if end == len(words):
            break
        overlap_start = end
        overlap_tokens = 0
        while overlap_start > start and overlap_tokens < min(max_tokens // 2, overlap):
            overlap_start -= 1
            overlap_tokens += token_count(words[overlap_start])
        start = max(start + 1, overlap_start)
    return result


def chunk_blocks(blocks: list[TextBlock], max_tokens: int = 420, overlap: int = 60) -> list[Chunk]:
    """Pack structure-aware blocks while retaining page/section provenance."""
    chunks: list[Chunk] = []
    current: list[TextBlock] = []
    overlap_only = False

    def flush(keep_overlap: bool = True) -> None:
        nonlocal current, overlap_only
        if not current:
            return
        text = "\n\n".join(block.text.strip() for block in current if block.text.strip())
        if text:
            pages = [block.page for block in current if block.page is not None]
            sections = list(dict.fromkeys(block.section for block in current if block.section))
            chunks.append(Chunk(
                content=text,
                token_count=token_count(text),
                page_start=min(pages) if pages else None,
                page_end=max(pages) if pages else None,
                section=" / ".join(sections),
            ))
        if keep_overlap and overlap and current:
            retained: list[TextBlock] = []
            accumulated = 0
            for block in reversed(current):
                block_tokens = token_count(block.text)
                if block_tokens > overlap * 2 or accumulated + block_tokens > overlap * 2:
                    break
                retained.insert(0, block)
                accumulated += block_tokens
                if accumulated >= overlap:
                    break
            current = retained
            overlap_only = bool(retained)
        else:
            current = []
            overlap_only = False

    for block in blocks:
        clean = re.sub(r"\s+", " ", block.text).strip()
        if not clean:
            continue
        parts = _split_oversized(clean, max_tokens, overlap)
        for part in parts:
            next_block = TextBlock(part, block.page, block.section)
            proposed = current + [next_block]
            combined = "\n\n".join(item.text for item in proposed)
            if current and token_count(combined) > max_tokens:
                if not overlap_only:
                    flush()
                while current and token_count("\n\n".join([item.text for item in current] + [part])) > max_tokens:
                    current.pop(0)
                current.append(next_block)
                overlap_only = False
            else:
                current = proposed
                overlap_only = False
    flush(keep_overlap=False)
    return chunks

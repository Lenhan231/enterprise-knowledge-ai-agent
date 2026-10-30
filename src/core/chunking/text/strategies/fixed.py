"""Fixed character-window chunking."""


def split_ranges(text: str, size: int, overlap: int, base: int = 0) -> list[tuple[int, int]]:
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("chunk size must be positive and overlap smaller than size")
    ranges = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start, end)
            if boundary > start:
                end = boundary
        if text[start:end].strip():
            ranges.append((base + start, base + end))
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return ranges

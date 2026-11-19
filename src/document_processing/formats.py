"""File extensions and media types accepted by document processing."""

LEGACY_OFFICE_FORMATS = {".doc": ".docx", ".xls": ".xlsx", ".ppt": ".pptx"}
NORMALIZED_RASTER_FORMATS = {
    ".bmp": "BMP", ".gif": "GIF", ".webp": "WEBP",
    ".heic": "HEIF", ".heif": "HEIF", ".avif": "AVIF",
}
MODERN_IMAGE_FORMATS = frozenset({".heic", ".heif", ".avif"})
IMAGE_FORMATS = frozenset({
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".svg", *NORMALIZED_RASTER_FORMATS,
})
MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".avif": "image/avif",
}
SUPPORTED_FORMATS = frozenset(MEDIA_TYPES)

_OFFICE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_SIGNATURES = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".tif": (b"II*\x00", b"MM\x00*"),
    ".tiff": (b"II*\x00", b"MM\x00*"),
    ".bmp": (b"BM",),
    ".gif": (b"GIF87a", b"GIF89a"),
    **dict.fromkeys(LEGACY_OFFICE_FORMATS, (_OFFICE_SIGNATURE,)),
}
_AVIF_BRANDS = {b"avif", b"avis"}
_HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heis", b"hevm", b"hevs", b"heim", b"mif1", b"msf1"}


def matches_signature(content: bytes, suffix: str) -> bool:
    """Check container signatures without decoding the upload."""
    if suffix == ".webp":
        return content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    if suffix in MODERN_IMAGE_FORMATS:
        if content[4:8] != b"ftyp":
            return False
        end = int.from_bytes(content[:4], "big")
        if not 16 <= end <= min(len(content), 4096) or end % 4:
            return False
        brands = {content[8:12], *(content[i:i + 4] for i in range(16, end, 4))}
        if suffix == ".avif":
            return bool(brands & _AVIF_BRANDS)
        return not brands & _AVIF_BRANDS and bool(brands & _HEIF_BRANDS)
    signatures = _SIGNATURES.get(suffix)
    return signatures is None or content.startswith(signatures)

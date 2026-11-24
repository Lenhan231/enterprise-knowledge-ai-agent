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


def _is_compound_office_file(content: bytes) -> bool:
    """Check the CFB header, FAT references, and sector alignment."""
    if len(content) < 512 or not content.startswith(_OFFICE_SIGNATURE):
        return False

    major_version = int.from_bytes(content[26:28], "little")
    byte_order = int.from_bytes(content[28:30], "little")
    sector_shift = int.from_bytes(content[30:32], "little")
    mini_sector_shift = int.from_bytes(content[32:34], "little")
    expected_shift = {3: 9, 4: 12}.get(major_version)
    if byte_order != 0xFFFE or expected_shift is None or sector_shift != expected_shift:
        return False
    if mini_sector_shift != 6 or content[34:40] != bytes(6):
        return False

    sector_size = 1 << sector_shift
    if len(content) < 512 + sector_size or (len(content) - 512) % sector_size:
        return False

    sector_count = (len(content) - 512) // sector_size
    directory_sector_count = int.from_bytes(content[40:44], "little")
    fat_sector_count = int.from_bytes(content[44:48], "little")
    first_directory_sector = int.from_bytes(content[48:52], "little")
    mini_stream_cutoff = int.from_bytes(content[56:60], "little")
    first_difat_sector = int.from_bytes(content[68:72], "little")
    difat_sector_count = int.from_bytes(content[72:76], "little")
    if major_version == 3 and directory_sector_count != 0:
        return False
    if major_version == 4 and directory_sector_count == 0:
        return False
    if fat_sector_count == 0 or fat_sector_count > sector_count:
        return False
    if first_directory_sector >= sector_count or mini_stream_cutoff != 4096:
        return False

    difat = (
        int.from_bytes(content[offset:offset + 4], "little")
        for offset in range(76, 512, 4)
    )
    referenced_fat_sectors = sum(sector_id < sector_count for sector_id in difat)
    if referenced_fat_sectors < min(fat_sector_count, 109):
        return False
    if fat_sector_count > 109 and (difat_sector_count == 0 or first_difat_sector >= sector_count):
        return False
    if difat_sector_count and first_difat_sector >= sector_count:
        return False
    return True


def matches_signature(content: bytes, suffix: str) -> bool:
    """Check container signatures without decoding the upload."""
    if suffix == ".pdf":
        return content[:1024].lstrip(b"\x00\t\n\f\r ").startswith(b"%PDF-")
    if suffix in LEGACY_OFFICE_FORMATS:
        return _is_compound_office_file(content)
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

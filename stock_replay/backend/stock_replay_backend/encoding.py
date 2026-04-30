from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from charset_normalizer import from_bytes


ENCODING_FALLBACKS = ("utf-8-sig", "gb18030", "utf-8")


@dataclass(frozen=True)
class CleanedText:
    text: str
    encoding: str
    null_bytes_removed: int


def read_clean_text(path: Path) -> CleanedText:
    raw_bytes = path.read_bytes()
    null_bytes_removed = raw_bytes.count(b"\x00")
    cleaned_bytes = raw_bytes.replace(b"\x00", b"")
    detected_encoding = detect_encoding(cleaned_bytes)
    text = cleaned_bytes.decode(detected_encoding)
    return CleanedText(
        text=text,
        encoding=detected_encoding,
        null_bytes_removed=null_bytes_removed,
    )


def detect_encoding(data: bytes) -> str:
    match = from_bytes(data).best()
    if match and match.encoding:
        return match.encoding

    for encoding in ENCODING_FALLBACKS:
        try:
            data.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue

    raise UnicodeDecodeError("unknown", b"", 0, 1, "unable to detect encoding")


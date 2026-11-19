"""MIME type resolution and content sniffing (docs/ARCHITECTURE.md section 15, Upload)."""

from __future__ import annotations

from pathlib import PurePosixPath

from vlade_rag.core.domain import InvalidArgument

TEXT = "text/plain"
MARKDOWN = "text/markdown"
HTML = "text/html"
PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

EXTENSIONS = {
    ".txt": TEXT,
    ".text": TEXT,
    ".md": MARKDOWN,
    ".markdown": MARKDOWN,
    ".html": HTML,
    ".htm": HTML,
    ".pdf": PDF,
    ".docx": DOCX,
}
TEXT_TYPES = frozenset({TEXT, MARKDOWN, HTML})


def resolve_mime_type(filename: str, declared: str | None, data: bytes) -> str:
    """Pick the MIME type from the declared type or the extension, then check the content."""
    declared = (declared or "").split(";")[0].strip().lower() or None
    if declared in (None, "application/octet-stream"):
        declared = EXTENSIONS.get(PurePosixPath(filename.lower()).suffix)
    if declared is None:
        raise InvalidArgument(f"Cannot determine the file type of '{filename}'.")
    _check_content(declared, data)
    return declared


def _check_content(mime_type: str, data: bytes) -> None:
    if mime_type == PDF and not data.startswith(b"%PDF-"):
        raise InvalidArgument("The file content is not a PDF.")
    if mime_type == DOCX and not data.startswith(b"PK\x03\x04"):
        raise InvalidArgument("The file content is not a DOCX file.")
    if mime_type in TEXT_TYPES:
        if b"\x00" in data[:8192]:
            raise InvalidArgument("The file content is not text.")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InvalidArgument("Text files must use UTF-8.") from exc

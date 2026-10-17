"""
pdf.py — a minimal, dependency-free PDF writer (WS-5).

Why hand-rolled: the backend must stay installable on a free tier with no system
libraries, and a DPR is text and tables. This writes a valid multi-page PDF
(Helvetica, WinAnsi) with no third-party package — the acceptance test for the
DPR is that the file really opens, so it is worth the ~150 lines.

Two honest limits, both documented for callers:

* **Latin-1 only.** ``₹`` becomes ``Rs.`` and other non-Latin glyphs are dropped
  with their line kept intact. Devanagari needs an embedded font and a shaping
  engine, which is why the DPR's PDF is generated in English (banks read English
  files); the on-screen report is localised.
* **No compression.** Streams are plain text, so a PDF is greppable — useful when
  testing that a source URL really made it into the footer.
"""
from __future__ import annotations

import logging
import textwrap
from typing import Dict, List

logger = logging.getLogger(__name__)

PAGE_WIDTH = 595.0  # A4 portrait, points
PAGE_HEIGHT = 842.0
MARGIN_X = 50.0
MARGIN_TOP = 60.0
MARGIN_BOTTOM = 60.0
USABLE_WIDTH = PAGE_WIDTH - 2 * MARGIN_X

# Style → (font key, size, leading, bold)
_STYLES: Dict[str, tuple] = {
    "h1": ("F2", 16.0, 22.0),
    "h2": ("F2", 12.5, 18.0),
    "h3": ("F2", 11.0, 16.0),
    "body": ("F1", 10.0, 14.0),
    "bullet": ("F1", 10.0, 14.0),
    "kv": ("F1", 10.0, 14.0),
    "small": ("F1", 8.5, 12.0),
}

_TRANSLITERATE = {
    "₹": "Rs.",
    "—": "-",
    "–": "-",
    "’": "'",
    "‘": "'",
    "“": '"',
    "”": '"',
    "·": "-",
    "×": "x",
    "≤": "<=",
    "≥": ">=",
    "→": "->",
    "\u00a0": " ",
}


def ascii_safe(text: str) -> str:
    """Latin-1-safe text: transliterate the common glyphs, drop the rest."""
    value = str(text or "")
    for source, target in _TRANSLITERATE.items():
        value = value.replace(source, target)
    return value.encode("latin-1", "ignore").decode("latin-1")


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _wrap(text: str, size: float, indent: int = 0) -> List[str]:
    # Helvetica's average advance is ~0.5 em; the small fudge keeps bold headings
    # inside the margin too.
    per_char = 0.52 * size
    width = max(20, int((USABLE_WIDTH - indent) / per_char))
    wrapped: List[str] = []
    for paragraph in str(text or "").split("\n"):
        if not paragraph.strip():
            wrapped.append("")
            continue
        wrapped.extend(textwrap.wrap(paragraph, width=width) or [""])
    return wrapped


def _content_stream(blocks: List[Dict[str, str]], footer: str) -> List[str]:
    """Return one content stream per page."""
    pages: List[List[str]] = [[]]
    y = PAGE_HEIGHT - MARGIN_TOP
    for block in blocks:
        style = block.get("style", "body")
        font, size, leading = _STYLES.get(style, _STYLES["body"])
        raw = block.get("text", "")
        indent = 12 if style == "bullet" else 0
        prefix = "- " if style == "bullet" else ""
        for index, line in enumerate(_wrap(raw, size, indent)):
            if y - leading < MARGIN_BOTTOM:
                pages.append([])
                y = PAGE_HEIGHT - MARGIN_TOP
            # Every block goes through ascii_safe — computed figures carry ₹, and
            # WinAnsi cannot encode it, so it becomes "Rs." here rather than
            # crashing the writer.
            text = _escape(ascii_safe(f"{prefix if index == 0 else '  ' if prefix else ''}{line}"))
            pages[-1].append(f"BT /{font} {size:.1f} Tf {MARGIN_X + indent:.1f} {y:.1f} Td ({text}) Tj ET")
            y -= leading
        if style in ("h1", "h2"):
            y -= 4

    # Footer on every page: the DPR's provenance line lives here.
    if footer:
        for page in pages:
            page.append(
                f"BT /F1 8.0 Tf {MARGIN_X:.1f} {MARGIN_BOTTOM - 20:.1f} Td "
                f"({_escape(ascii_safe(footer))}) Tj ET"
            )
    return ["\n".join(page) for page in pages]


def render_pdf(title: str, blocks: List[Dict[str, str]], footer: str = "") -> bytes:
    """Build a valid PDF. ``blocks`` is a list of ``{"style", "text"}`` dicts."""
    streams = _content_stream(blocks, footer)
    count = len(streams)

    # Object numbering: 1 catalog, 2 pages, 3 font regular, 4 font bold, then
    # one page object + one content stream per page.
    page_ids = [5 + 2 * index for index in range(count)]
    objects: Dict[int, bytes] = {}
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {count} >>".encode("latin-1")
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    objects[4] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"

    for index, stream in enumerate(streams):
        page_id = page_ids[index]
        stream_id = page_id + 1
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH:.0f} {PAGE_HEIGHT:.0f}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {stream_id} 0 R >>"
        ).encode("latin-1")
        payload = stream.encode("latin-1")
        objects[stream_id] = (
            f"<< /Length {len(payload)} >>\nstream\n".encode("latin-1") + payload + b"\nendstream"
        )

    # Title in the document information dictionary — some readers show it.
    objects[6 + 2 * count] = (
        f"<< /Title ({_escape(ascii_safe(title))}) /Producer (Your AI Business Saathi) >>"
    ).encode("latin-1")
    info_id = 6 + 2 * count

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: Dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n".encode("latin-1") + objects[number] + b"\nendobj\n"

    highest = max(objects)
    xref_at = len(out)
    out += f"xref\n0 {highest + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for number in range(1, highest + 1):
        if number in offsets:
            out += f"{offsets[number]:010d} 00000 n \n".encode("latin-1")
        else:
            out += b"0000000000 65535 f \n"
    out += (
        f"trailer\n<< /Size {highest + 1} /Root 1 0 R /Info {info_id} 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode("latin-1")
    return bytes(out)


__all__ = ["render_pdf", "ascii_safe"]

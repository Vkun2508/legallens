"""Build small text PDFs for tests, so no binary fixtures need to be committed."""

from __future__ import annotations

_LINE_HEIGHT = 14
_TOP = 760


def build_pdf(pages: list[list[str]]) -> bytes:
    """Return a PDF with one Helvetica text line per string; "" leaves a blank line."""
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b""]  # pages object filled in below
    page_ids = []
    for lines in pages:
        content = _content_stream(lines)
        content_id = len(objects) + 1
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content))
        page_ids.append(len(objects) + 1)
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> "
            b"/Contents %d 0 R >>" % content_id
        )
    kids = b" ".join(b"%d 0 R" % i for i in page_ids)
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(page_ids))

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def _content_stream(lines: list[str]) -> bytes:
    ops = []
    for i, line in enumerate(lines):
        if line:
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            ops.append(f"BT /F1 10 Tf 72 {_TOP - i * _LINE_HEIGHT} Td ({escaped}) Tj ET")
    return "\n".join(ops).encode("latin-1")

"""
Write a minimal one-page PDF with plain text lines (no dependencies)

Usage: python scripts/make_text_pdf.py out.pdf "First line" "Second line"
"""

import sys


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(lines) -> bytes:
    """Return the bytes of a one-page PDF showing `lines` in Helvetica"""
    text_ops = ["BT", "/F1 12 Tf", "72 720 Td", "14 TL"]
    for line in lines:
        text_ops.append(f"({_escape(line)}) Tj T*")
    text_ops.append("ET")
    stream = "\n".join(text_ops).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode()
    return bytes(out)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    with open(sys.argv[1], "wb") as f:
        f.write(make_pdf(sys.argv[2:]))

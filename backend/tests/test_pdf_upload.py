from io import BytesIO

from fastapi.testclient import TestClient

from app.config import MAX_UPLOAD_BYTES
from app.main import app

client = TestClient(app)


def make_pdf(lines: list[str]) -> bytes:
    """Build a minimal one-page PDF with each line as text (empty list = blank page)."""

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    ops = "".join(f"({esc(line)}) Tj 0 -16 Td " for line in lines)
    stream = f"BT /F1 12 Tf 72 720 Td {ops}ET".encode() if lines else b""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 5 0 R /Resources << /Font << /F1 4 0 R >> >> >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def post(name: str, data: bytes, content_type: str = "application/pdf"):
    return client.post("/api/upload", files={"file": (name, BytesIO(data), content_type)})


def test_extracts_text_from_pdf():
    pdf = make_pdf(["Aisyah Rahman", "Accounts Executive", "Skills: Reconciliation, Excel, SAP"])
    res = post("resume.pdf", pdf)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["filename"] == "resume.pdf"
    assert body["pages"] == 1
    assert "Accounts Executive" in body["text"]
    assert "Reconciliation, Excel, SAP" in body["text"]
    assert body["chars"] == len(body["text"])
    assert body["warnings"] == []


def test_splits_ligatures():
    from app.services.pdf_extract import _clean

    assert _clean("Logistics ﬁrm, workﬂow") == "Logistics firm, workflow"


def test_rejects_pdf_with_no_text():
    res = post("blank.pdf", make_pdf([]))

    assert res.status_code == 422
    assert "No readable text" in res.json()["detail"]


def test_rejects_unsupported_file_types():
    res = post("photo.heic", b"fake-heic-bytes" * 8, "image/heic")
    assert res.status_code == 415


def test_rejects_file_that_is_not_really_a_pdf():
    res = post("resume.pdf", b"this is not a pdf")
    assert res.status_code == 422


def test_rejects_corrupt_pdf():
    res = post("broken.pdf", b"%PDF-1.4\n" + b"garbage" * 50)
    assert res.status_code == 422


def test_rejects_oversized_file():
    res = post("big.pdf", b"%PDF-1.4\n" + b"0" * MAX_UPLOAD_BYTES)
    assert res.status_code == 413

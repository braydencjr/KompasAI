import re
import unicodedata
from dataclasses import dataclass, field
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class PdfExtractionError(Exception):
    """The file is not a readable PDF (corrupt, encrypted, not a PDF, or has no text)."""


@dataclass
class PdfText:
    text: str
    pages: list[str]
    warnings: list[str] = field(default_factory=list)


def _clean(text: str) -> str:
    # NFKC splits typographic ligatures (ﬁ → fi) so words match skill names later
    text = unicodedata.normalize("NFKC", text).replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf_text(data: bytes) -> PdfText:
    if not data.startswith(b"%PDF"):
        raise PdfExtractionError("File is not a PDF.")

    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            # many "protected" PDFs only restrict editing and open with an empty password
            if not reader.decrypt(""):
                raise PdfExtractionError("PDF is password-protected.")
        pages = [_clean(page.extract_text() or "") for page in reader.pages]
    except PdfExtractionError:
        raise
    except (PdfReadError, ValueError, KeyError) as e:
        raise PdfExtractionError("PDF could not be read; it may be corrupt.") from e

    text = "\n\n".join(p for p in pages if p)
    if not text:
        raise PdfExtractionError("No readable text found in this PDF.")

    warnings = []
    empty = [i + 1 for i, p in enumerate(pages) if not p]
    if empty:
        warnings.append(f"No text found on page(s) {', '.join(map(str, empty))}.")

    return PdfText(text=text, pages=pages, warnings=warnings)

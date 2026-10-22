import os
import re
import unicodedata
from dataclasses import dataclass, field
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
SUPPORTED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/bmp", "image/gif"}


def is_supported_image(filename: str | None, content_type: str | None) -> bool:
    name = (filename or "").lower()
    media_type = (content_type or "").lower()
    if media_type.startswith("image/"):
        return media_type in SUPPORTED_IMAGE_TYPES or media_type.startswith("image/")
    return any(name.endswith(ext) for ext in SUPPORTED_IMAGE_EXTENSIONS)


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


def extract_image_text(data: bytes, filename: str = "upload", content_type: str | None = None) -> PdfText:
    if not is_supported_image(filename, content_type):
        raise PdfExtractionError("Only PDF and supported image files are accepted.")

    warnings: list[str] = []
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    mime_type = (content_type or "").strip() or "image/png"
    try:
        if api_key:
            from google import genai
            from google.genai import types

            client = genai.Client()
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Part.from_bytes(data=data, mime_type=mime_type),
                    "Extract all readable text from this image in natural reading order. Return only the text, with paragraphs preserved.",
                ],
            )
            text = (response.text or "").strip()
            if text:
                return PdfText(text=text, pages=[text], warnings=warnings)
            warnings.append("OCR returned no readable text for this image.")
    except Exception:
        warnings.append("OCR is not available in the current environment; image uploaded successfully.")

    fallback = "Image uploaded successfully. OCR text extraction is unavailable in this environment."
    return PdfText(text=fallback, pages=[fallback], warnings=warnings or ["OCR text extraction is unavailable in this environment."])

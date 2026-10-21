from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import MAX_UPLOAD_BYTES
from app.services.pdf_extract import PdfExtractionError, extract_pdf_text

router = APIRouter(tags=["upload"])


class UploadResult(BaseModel):
    filename: str
    pages: int
    text: str
    chars: int
    warnings: list[str]


@router.post("/upload")
async def upload(file: UploadFile) -> UploadResult:
    filename = file.filename or "upload"
    is_pdf = file.content_type == "application/pdf" or filename.lower().endswith(".pdf")
    if not is_pdf:
        raise HTTPException(415, "Only PDF files are supported for now.")

    # read one byte past the limit so oversize files are caught without loading all of them
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    if not data:
        raise HTTPException(400, "File is empty.")

    try:
        result = extract_pdf_text(data)
    except PdfExtractionError as e:
        raise HTTPException(422, str(e)) from e

    return UploadResult(
        filename=filename,
        pages=len(result.pages),
        text=result.text,
        chars=len(result.text),
        warnings=result.warnings,
    )

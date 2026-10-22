from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import MAX_UPLOAD_BYTES
from app.services.pdf_extract import (
    PdfExtractionError,
    extract_image_text,
    extract_pdf_text,
    is_supported_image,
)

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
    content_type = file.content_type or ""
    is_pdf = content_type == "application/pdf" or filename.lower().endswith(".pdf")
    is_image = is_supported_image(filename, content_type)
    if not (is_pdf or is_image):
        raise HTTPException(415, "Unsupported file type. Upload a PDF or a common image file.")

    # read one byte past the limit so oversize files are caught without loading all of them
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    if not data:
        raise HTTPException(400, "File is empty.")

    try:
        if is_pdf:
            result = extract_pdf_text(data)
        else:
            result = extract_image_text(data, filename, content_type)
    except PdfExtractionError as e:
        raise HTTPException(422, str(e)) from e

    return UploadResult(
        filename=filename,
        pages=len(result.pages),
        text=result.text,
        chars=len(result.text),
        warnings=result.warnings,
    )

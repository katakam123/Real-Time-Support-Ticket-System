
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

UPLOAD_DIR = Path("uploads") / "chat"
MAX_FILE_SIZE = 5 * 1024 * 1024

ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
}


async def save_chat_attachment(file: UploadFile) -> dict:
    content_type = file.content_type or ""

    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Only JPG, PNG, GIF, and PDF files are allowed.",
        )

    # Read one byte beyond the limit to detect oversized uploads.
    data = await file.read(MAX_FILE_SIZE + 1)

    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File size must not exceed 5 MB.",
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Generate a server-side filename; do not use the uploaded filename as a path.
    filename = f"{uuid4().hex}{ALLOWED_TYPES[content_type]}"
    destination = UPLOAD_DIR / filename
    destination.write_bytes(data)

    return {
        "filename": filename,
        "original_filename": file.filename or "attachment",
        "content_type": content_type,
        "size_bytes": len(data),
        "storage_path": str(destination),
    }

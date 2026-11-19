"""Upload route — POST /upload"""
from __future__ import annotations

import logging
import os
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import Campaign

logger = logging.getLogger(__name__)

router = APIRouter()

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/tmp/marketing_crew_uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class UploadResponse(BaseModel):
    campaign_id: str
    original_filename: str
    storage_path: str
    message: str = "File uploaded successfully."


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an .mp3 file and create a Campaign record.",
)
async def upload_audio(
    file: UploadFile = File(..., description="The .mp3 audio file to upload."),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    """Accept an .mp3 upload, save it to disk, and create a Campaign row."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided.",
        )

    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".mp3", ".wav", ".flac", ".ogg", ".m4a"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {suffix!r}. Expected an audio file.",
        )

    unique_name = f"{uuid.uuid4()}{suffix}"
    dest_path = UPLOAD_DIR / unique_name

    try:
        with dest_path.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)
    except OSError as exc:
        logger.error("Failed to save uploaded file %s: %s", unique_name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {exc}",
        ) from exc

    campaign = Campaign(
        original_filename=file.filename,
        storage_path=str(dest_path),
        workflow_status="created",
    )
    db.add(campaign)
    await db.flush()

    logger.info("Uploaded %s → campaign=%s path=%s", file.filename, campaign.id, dest_path)

    return UploadResponse(
        campaign_id=str(campaign.id),
        original_filename=file.filename,
        storage_path=str(dest_path),
    )

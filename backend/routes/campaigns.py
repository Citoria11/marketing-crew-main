"""Campaign routes — GET /campaigns, GET /campaigns/{campaign_id}"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import Campaign

router = APIRouter()


class CampaignSummary(BaseModel):
    campaign_id: str
    original_filename: Optional[str]
    workflow_status: str
    thread_id: Optional[str]
    created_at: str


class CampaignDetail(BaseModel):
    campaign_id: str
    original_filename: Optional[str]
    storage_path: Optional[str]
    duration_seconds: Optional[str]
    sample_rate: Optional[str]
    audio_analysis: Optional[dict]
    lore: Optional[str]
    social_media_proposals: Optional[list]
    selected_proposal_index: Optional[str]
    thread_id: Optional[str]
    workflow_status: str
    created_at: str
    updated_at: str


def _campaign_to_summary(c: Campaign) -> CampaignSummary:
    return CampaignSummary(
        campaign_id=str(c.id),
        original_filename=c.original_filename,
        workflow_status=c.workflow_status,
        thread_id=c.thread_id,
        created_at=c.created_at.isoformat() if c.created_at else "",
    )


def _campaign_to_detail(c: Campaign) -> CampaignDetail:
    return CampaignDetail(
        campaign_id=str(c.id),
        original_filename=c.original_filename,
        storage_path=c.storage_path,
        duration_seconds=c.duration_seconds,
        sample_rate=c.sample_rate,
        audio_analysis=c.audio_analysis,
        lore=c.lore,
        social_media_proposals=c.social_media_proposals,
        selected_proposal_index=c.selected_proposal_index,
        thread_id=c.thread_id,
        workflow_status=c.workflow_status,
        created_at=c.created_at.isoformat() if c.created_at else "",
        updated_at=c.updated_at.isoformat() if c.updated_at else "",
    )


@router.get(
    "/campaigns",
    response_model=list[CampaignSummary],
    summary="List all campaigns.",
)
async def list_campaigns(
    db: AsyncSession = Depends(get_db),
) -> list[CampaignSummary]:
    """Return a summary list of all campaigns ordered by creation date."""
    result = await db.execute(
        select(Campaign).order_by(Campaign.created_at.desc())
    )
    campaigns = result.scalars().all()
    return [_campaign_to_summary(c) for c in campaigns]


@router.get(
    "/campaigns/{campaign_id}",
    response_model=CampaignDetail,
    summary="Return full detail for a campaign.",
)
async def get_campaign(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
) -> CampaignDetail:
    """Return full detail for a single campaign."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign: Optional[Campaign] = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign {campaign_id!r} not found.",
        )
    return _campaign_to_detail(campaign)

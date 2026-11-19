"""Workflow routes — POST /process, GET /state/{thread_id}, POST /resume"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import Campaign
from workflow.graph import get_state, resume_workflow, start_session

router = APIRouter()


class ProcessRequest(BaseModel):
    campaign_id: str = Field(..., description="UUID of the campaign to process.")


class ProcessResponse(BaseModel):
    thread_id: str
    campaign_id: str
    current_node: Optional[str] = None
    audio_analysis: Optional[dict[str, Any]] = None
    social_media_proposals: Optional[list[dict[str, Any]]] = None
    lore: Optional[str] = None
    status: str = "running"


class ResumeRequest(BaseModel):
    thread_id: str = Field(..., description="LangGraph thread_id to resume.")
    selected_proposal_index: int = Field(
        0, description="0-based index of the approved proposal."
    )
    reviewer_notes: str = Field("", description="Optional reviewer feedback.")


class ResumeResponse(BaseModel):
    thread_id: str
    production_assets: Optional[dict[str, Any]] = None
    status: str = "completed"


class StateResponse(BaseModel):
    thread_id: str
    campaign_id: Optional[str] = None
    current_node: Optional[str] = None
    messages: Optional[list[dict]] = None
    goal: Optional[str] = None
    task_type: Optional[str] = None
    audio_analysis: Optional[dict[str, Any]] = None
    audio_analysis_summary: Optional[str] = None
    music_brief: Optional[str] = None
    lore: Optional[str] = None
    social_media_proposals: Optional[list[dict[str, Any]]] = None
    selected_proposal_index: Optional[int] = None
    production_assets: Optional[dict[str, Any]] = None
    waiting_for_input: bool = False
    waiting_for_approval: bool = False
    error: Optional[str] = None


@router.post(
    "/process",
    response_model=ProcessResponse,
    summary="Start the LangGraph workflow for a campaign.",
)
async def process_campaign(
    body: ProcessRequest,
    db: AsyncSession = Depends(get_db),
) -> ProcessResponse:
    """Kick off the LangGraph workflow for the given campaign_id."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == body.campaign_id)
    )
    campaign: Optional[Campaign] = result.scalar_one_or_none()

    if campaign is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign {body.campaign_id!r} not found.",
        )

    if campaign.workflow_status not in {"created", "error"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Campaign is already in state {campaign.workflow_status!r}. "
                "Only 'created' or 'error' campaigns can be re-processed."
            ),
        )

    campaign.workflow_status = "analyzing"

    try:
        thread_id, _ = await start_session(
            campaign_id=str(campaign.id),
            audio_path=campaign.storage_path,
        )
    except Exception as exc:  # noqa: BLE001
        campaign.workflow_status = "error"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Workflow start failed: {exc}",
        ) from exc

    campaign.thread_id = thread_id
    campaign.workflow_status = "awaiting_approval"

    current = await get_state(thread_id)
    campaign.audio_analysis = current.get("audio_analysis")
    campaign.lore = current.get("lore")
    campaign.social_media_proposals = current.get("social_media_proposals")

    return ProcessResponse(
        thread_id=thread_id,
        campaign_id=str(campaign.id),
        current_node=current.get("current_node"),
        audio_analysis=current.get("audio_analysis"),
        social_media_proposals=current.get("social_media_proposals"),
        lore=current.get("lore"),
        status="awaiting_approval",
    )


@router.get(
    "/state/{thread_id}",
    response_model=StateResponse,
    summary="Return the current LangGraph state for a thread.",
)
async def get_workflow_state(thread_id: str) -> StateResponse:
    """Return the live state snapshot for the given LangGraph thread."""
    state = await get_state(thread_id)
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thread {thread_id!r} not found.",
        )
    return StateResponse(
        thread_id=thread_id,
        campaign_id=state.get("campaign_id"),
        current_node=state.get("current_node"),
        messages=state.get("messages"),
        goal=state.get("goal"),
        task_type=state.get("task_type"),
        audio_analysis=state.get("audio_analysis"),
        audio_analysis_summary=state.get("audio_analysis_summary"),
        music_brief=state.get("music_brief"),
        lore=state.get("lore"),
        social_media_proposals=state.get("social_media_proposals"),
        selected_proposal_index=state.get("selected_proposal_index"),
        production_assets=state.get("production_assets"),
        waiting_for_input=state.get("_waiting_for_input", False),
        waiting_for_approval=state.get("_waiting_for_approval", False),
        error=state.get("error"),
    )


@router.post(
    "/resume",
    response_model=ResumeResponse,
    summary="Resume a paused workflow after human approval.",
)
async def resume_campaign(
    body: ResumeRequest,
    db: AsyncSession = Depends(get_db),
) -> ResumeResponse:
    """Inject the human's approval decision and run Execute_Production."""
    try:
        final = await resume_workflow(
            thread_id=body.thread_id,
            selected_proposal_index=body.selected_proposal_index,
            reviewer_notes=body.reviewer_notes,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Resume failed: {exc}",
        ) from exc

    result = await db.execute(
        select(Campaign).where(Campaign.thread_id == body.thread_id)
    )
    campaign: Optional[Campaign] = result.scalar_one_or_none()
    if campaign:
        campaign.workflow_status = "done"
        campaign.selected_proposal_index = str(body.selected_proposal_index)

    production_assets = None
    if isinstance(final, dict):
        for v in final.values():
            if isinstance(v, dict) and "production_assets" in v:
                production_assets = v["production_assets"]
                break

    return ResumeResponse(
        thread_id=body.thread_id,
        production_assets=production_assets,
        status="completed",
    )

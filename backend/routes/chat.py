"""Chat routes — POST /chat/start, POST /chat/message

These are the primary entry points for the conversational UI.

Flow
----
1. POST /chat/start   — upload a campaign (or reference an existing one),
                        creates a LangGraph thread. The graph pauses at
                        chat_intake waiting for the user's first message.
2. POST /chat/message — send a user message (or clarification answer).
                        The graph resumes, runs until the next interrupt or
                        completion, and returns the updated state.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status

logger = logging.getLogger(__name__)
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import Campaign
from workflow.graph import get_state, send_message, start_session

router = APIRouter(prefix="/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class StartChatRequest(BaseModel):
    campaign_id: Optional[str] = Field(
        None,
        description=(
            "UUID of an already-uploaded campaign. "
            "If omitted, a new campaign row is created automatically."
        ),
    )


class StartChatResponse(BaseModel):
    thread_id: str
    campaign_id: str
    waiting_for_input: bool = True
    assistant_message: str = (
        "Hi! I'm your country music marketing assistant. "
        "Tell me what you'd like to create for this track — "
        "an Instagram post, a Twitter caption, a full social media suite, "
        "an image prompt, or something else?"
    )


class MessageRequest(BaseModel):
    thread_id: str = Field(..., description="LangGraph thread_id from /chat/start.")
    message: str = Field(..., min_length=1, description="User message or answer.")


class MessageResponse(BaseModel):
    thread_id: str
    waiting_for_input: bool
    waiting_for_approval: bool
    clarification_needed: str
    assistant_message: str
    task_type: Optional[str] = None
    goal: Optional[str] = None
    social_media_proposals: Optional[list[dict[str, Any]]] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/start",
    response_model=StartChatResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new chat session for a campaign.",
)
async def start_chat(
    body: StartChatRequest,
    db: AsyncSession = Depends(get_db),
) -> StartChatResponse:
    """Create a LangGraph thread and pause at the first chat_intake interrupt.

    If ``campaign_id`` is provided, that campaign must already exist.
    Otherwise a placeholder campaign row is created with ``workflow_status='chat'``.
    """
    # ---- Resolve campaign -----------------------------------------------
    if body.campaign_id:
        result = await db.execute(
            select(Campaign).where(Campaign.id == body.campaign_id)
        )
        campaign: Optional[Campaign] = result.scalar_one_or_none()
        if campaign is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Campaign {body.campaign_id!r} not found.",
            )
    else:
        campaign = Campaign(workflow_status="chat")
        db.add(campaign)
        await db.flush()  # Assign ID without committing

    # ---- Start graph session --------------------------------------------
    try:
        thread_id, greeting = await start_session(
            campaign_id=str(campaign.id),
            audio_path=campaign.storage_path if campaign.storage_path else None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("start_session failed for campaign=%s: %s", campaign.id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialise session: {exc}",
        ) from exc

    logger.info("Chat session started: campaign=%s thread=%s", campaign.id, thread_id)

    campaign.thread_id = thread_id
    campaign.workflow_status = "chat"
    await db.commit()

    return StartChatResponse(
        thread_id=thread_id,
        campaign_id=str(campaign.id),
        waiting_for_input=True,
        assistant_message=greeting or StartChatResponse.model_fields["assistant_message"].default,
    )


@router.post(
    "/message",
    response_model=MessageResponse,
    summary="Send a message or clarification answer to the running session.",
)
async def send_chat_message(
    body: MessageRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Inject a user message and resume the graph until the next interrupt.

    The graph can pause at:
    - ``chat_intake``        — another conversational turn or clarification
    - ``execute_production`` — waiting for human approval of a proposal
    - END                    — fully completed
    """
    # Verify the thread exists
    current = await get_state(body.thread_id)
    if not current:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No session found for thread_id={body.thread_id!r}.",
        )

    try:
        result = await send_message(
            thread_id=body.thread_id,
            content=body.message,
        )
    except RuntimeError as exc:
        logger.warning("send_message conflict on thread=%s: %s", body.thread_id, exc)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("send_message error on thread=%s: %s", body.thread_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Graph execution error: {exc}",
        ) from exc

    state: dict[str, Any] = result.get("state", {})

    # ---- Persist state fields back to Campaign row --------------------------
    campaign_id = state.get("campaign_id")
    if campaign_id:
        db_result = await db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign: Optional[Campaign] = db_result.scalar_one_or_none()
        if campaign:
            if state.get("music_brief"):
                campaign.music_brief = state["music_brief"]
            if state.get("social_media_proposals"):
                campaign.social_media_proposals = state["social_media_proposals"]
            if state.get("lore"):
                campaign.lore = state["lore"]
            if state.get("audio_analysis"):
                campaign.audio_analysis = state["audio_analysis"]
            if state.get("rag_passages"):
                campaign.rag_context = state["rag_passages"]

            # Update workflow_status based on graph progress
            current_node = state.get("current_node", "")
            if result.get("waiting_for_approval"):
                campaign.workflow_status = "awaiting_approval"
            elif current_node in ("analyze_audio",):
                campaign.workflow_status = "analyzing"
            elif current_node in ("music_analyst", "lore_architect", "content_director"):
                campaign.workflow_status = "brainstorming"
            elif current_node == "execute_production":
                campaign.workflow_status = "producing"
            # else: keep existing status (e.g. 'chat' during intake)

            await db.commit()

    return MessageResponse(
        thread_id=body.thread_id,
        waiting_for_input=result.get("waiting_for_input", False),
        waiting_for_approval=result.get("waiting_for_approval", False),
        clarification_needed=result.get("clarification_needed", ""),
        assistant_message=result.get("assistant_message", ""),
        task_type=state.get("task_type"),
        goal=state.get("goal"),
        social_media_proposals=state.get("social_media_proposals"),
        error=state.get("error"),
    )

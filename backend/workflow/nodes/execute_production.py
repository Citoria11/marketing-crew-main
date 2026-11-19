"""execute_production LangGraph node.

Runs after human approval. Assembles the final production-ready assets
from the approved proposal and full workflow context.
Input:  state['selected_proposal_index'], state['reviewer_notes'], full state
Output: state['production_assets']
"""
from __future__ import annotations

import logging
from typing import Any

from workflow.state import WorkflowState

logger = logging.getLogger(__name__)


async def execute_production(state: WorkflowState) -> dict:
    """LangGraph node: assembles final production assets from the approved proposal."""
    proposals: list[dict[str, Any]] = state.get("social_media_proposals", [])
    selected_index: int = state.get("selected_proposal_index", 0)
    reviewer_notes: str = state.get("reviewer_notes", "")

    logger.info(
        "execute_production: assembling assets (proposal=%d of %d)",
        selected_index,
        len(proposals),
    )
    if not proposals:
        logger.warning("execute_production: no proposals found — returning empty assets")
        return {
            "current_node": "execute_production",
            "error": "No proposals available to produce.",
            "production_assets": {},
        }

    safe_index = min(max(selected_index, 0), len(proposals) - 1)

    production_assets: dict[str, Any] = {
        "approved_proposal": proposals[safe_index],
        "all_proposals": proposals,
        "reviewer_notes": reviewer_notes,
        "campaign_id": state.get("campaign_id", ""),
        "audio_path": state.get("audio_path", ""),
        "audio_analysis": state.get("audio_analysis", {}),
        "music_brief": state.get("music_brief", ""),
        "lore": state.get("lore", ""),
        "rag_passages": state.get("rag_passages", []),
        "status": "production_complete",
    }

    logger.info("execute_production: complete for campaign=%s", state.get("campaign_id", ""))
    return {
        "current_node": "execute_production",
        "production_assets": production_assets,
    }

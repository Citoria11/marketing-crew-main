"""Orchestrator LangGraph node — deterministic multi-agent router.

Responsibilities
----------------
1. Detects clarification requests from any node and routes back to chat_intake.
2. After clarification is resolved, routes back to the node that requested it.
3. Deterministically decides which capability node to invoke next based on
   what is present (or missing) in state — no LLM call needed, routing is
   entirely rule-based.

Agent execution order (per task_type)
--------------------------------------
                        analyze_audio → music_analyst ┐
                                                       ├→ content_director → image_generator → video_concept_writer → execute_production
                                       lore_architect ┘

music_analyst and lore_architect are independent of each other but both feed
content_director, so the orchestrator runs one then the other before moving on.

Routing rules
-------------
  1. analyze_audio     if audio_path present and audio_analysis missing
  2. music_analyst     if music_brief missing
  3. lore_architect    if lore missing AND task_type needs lore
  4. content_director  if proposals missing AND task_type needs proposals
                       (requires music_brief AND lore both present)
  5. image_generator   if image_assets missing AND task_type needs visuals
  6. video_concept_writer  if video_scripts missing AND task_type needs video
  7. execute_production  otherwise (all required outputs present)

A MAX_ITERATIONS guard prevents infinite loops regardless of state.
"""
from __future__ import annotations

import logging

from workflow.state import WorkflowState

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 20

# ---- What each task_type requires before we call execute_production ----------
# Keys map to state field names.  The orchestrator checks each in order.
_TASK_PIPELINE: dict[str, list[str]] = {
    "instagram_post":     ["music_brief", "lore", "social_media_proposals", "image_assets"],
    "twitter_post":       ["music_brief", "lore", "social_media_proposals"],
    "tiktok_post":        ["music_brief", "lore", "social_media_proposals", "image_assets", "video_scripts"],
    "social_media_suite": ["music_brief", "lore", "social_media_proposals", "image_assets", "video_scripts"],
    "image_prompt":       ["music_brief", "lore", "image_assets"],
    "video_script":       ["music_brief", "lore", "video_scripts"],
    "audio_analysis_only":["music_brief"],
    "unknown":            ["music_brief", "lore", "social_media_proposals", "image_assets"],
}

# ---- Which state field does each downstream node produce? -------------------
_PRODUCES: dict[str, str] = {
    "analyze_audio":          "audio_analysis",
    "music_analyst":          "music_brief",
    "lore_architect":         "lore",
    "content_director":       "social_media_proposals",
    "image_generator":        "image_assets",
    "video_concept_writer":   "video_scripts",
}

# ---- Which state field(s) must exist before each node can run? --------------
_REQUIRES: dict[str, list[str]] = {
    "analyze_audio":        [],                                   # only needs audio_path
    "music_analyst":        ["audio_analysis"],
    "lore_architect":       [],                                   # can start from summary
    "content_director":     ["music_brief", "lore"],
    "image_generator":      ["social_media_proposals"],
    "video_concept_writer": ["social_media_proposals", "music_brief"],
}


def _choose_next(state: WorkflowState) -> str:
    """Pure function — return the next node name based on current state."""
    task_type = state.get("task_type", "unknown") or "unknown"
    pipeline   = _TASK_PIPELINE.get(task_type, _TASK_PIPELINE["unknown"])

    audio_path  = state.get("audio_path", "")
    has: dict[str, bool] = {
        "audio_analysis":       bool(state.get("audio_analysis")),
        "music_brief":          bool(state.get("music_brief", "")),
        "lore":                 bool(state.get("lore", "")),
        "social_media_proposals": bool(state.get("social_media_proposals")),
        "image_assets":         bool(state.get("image_assets")),
        "video_scripts":        bool(state.get("video_scripts")),
    }

    # Step 0 — audio analysis is a prerequisite for music_analyst; run it first
    # if we have an audio file but haven't analysed it yet.
    if audio_path and not has["audio_analysis"]:
        return "analyze_audio"

    # Steps 1-N — work through the pipeline for this task_type
    for required_output in pipeline:
        if has.get(required_output):
            continue   # already done

        # Find which node produces this output
        producer = next(
            (node for node, produces in _PRODUCES.items() if produces == required_output),
            None,
        )
        if producer is None:
            continue   # no node registered — skip

        # Check that all prerequisites for that node are satisfied
        prereqs = _REQUIRES.get(producer, [])
        if all(has.get(p) for p in prereqs):
            return producer
        # Prerequisites not yet met — keep iterating; a prior pipeline step
        # will produce the missing prereq on the next pass through the loop.

    return "execute_production"


async def run_orchestrator(state: WorkflowState) -> dict:
    """LangGraph node: deterministic multi-agent router."""

    # ---- Clarification pass-through -----------------------------------------
    if state.get("clarification_needed"):
        logger.info("Clarification needed — routing back to chat_intake")
        return {
            "next": "chat_intake",
            "current_node": "orchestrator",
            "iteration_count": state.get("iteration_count", 0),
        }

    # ---- After clarification: resume at the requesting node ------------------
    resume_at = state.get("resume_at", "")
    if resume_at and resume_at != "chat_intake":
        logger.info("Resuming at %s after clarification", resume_at)
        return {
            "next": resume_at,
            "resume_at": "",
            "current_node": "orchestrator",
            "iteration_count": state.get("iteration_count", 0),
        }

    # ---- Guard against infinite loops ----------------------------------------
    iteration_count = state.get("iteration_count", 0) + 1
    if iteration_count > MAX_ITERATIONS:
        return {
            "next": "execute_production",
            "iteration_count": iteration_count,
            "current_node": "orchestrator",
        }

    next_node = _choose_next(state)
    logger.info(
        "Routing → %s  (task_type=%s iteration=%d)",
        next_node,
        state.get("task_type", "unknown"),
        iteration_count,
    )

    return {
        "next": next_node,
        "iteration_count": iteration_count,
        "current_node": "orchestrator",
    }


def route_from_orchestrator(state: WorkflowState) -> str:
    """Conditional edge function: reads state['next'] set by run_orchestrator."""
    return state.get("next", "orchestrator")


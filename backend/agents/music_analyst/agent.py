"""MusicAnalyst LangGraph node.

Interprets raw librosa audio analysis data into a marketing brief using an LLM.
Input:  state['audio_analysis'] + state['audio_analysis_summary'] + state['user_context']
Output: state['music_brief']

Clarification protocol: if audio_analysis is missing and audio_path is also
missing, the node signals the orchestrator to ask the user for an audio file.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel

from agents.base import get_chat_model
from agents.music_analyst.prompts import SYSTEM_PROMPT, build_user_prompt
from workflow.state import WorkflowState

logger = logging.getLogger(__name__)


class MusicBriefOutput(BaseModel):
    brief: str
    mood: str
    marketing_angles: list[str]


async def run_music_analyst(state: WorkflowState) -> dict:
    """LangGraph node: produces a marketing brief from the audio analysis."""
    audio_analysis = state.get("audio_analysis")
    audio_path = state.get("audio_path", "")

    # Clarification protocol — can't proceed without audio data.
    if not audio_analysis and not audio_path:
        return {
            "clarification_needed": (
                "I need an audio file to analyse. "
                "Could you upload an .mp3 file so I can extract the musical features?"
            ),
            "clarification_context": "music_analyst: no audio_analysis or audio_path in state",
            "resume_at": "music_analyst",
            "next": "chat_intake",
            "current_node": "music_analyst",
        }

    user_context = state.get("user_context", {})
    model = get_chat_model(temperature=0.3).with_structured_output(MusicBriefOutput)

    user_prompt = build_user_prompt(
        audio_analysis=audio_analysis or {},
        audio_analysis_summary=state.get("audio_analysis_summary", ""),
        user_context=user_context,
    )
    logger.info("music_analyst: generating marketing brief")
    try:
        result: MusicBriefOutput = await model.ainvoke(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
        )
    except Exception as exc:
        logger.error("music_analyst LLM call failed: %s", exc, exc_info=True)
        raise

    angles_text = "\n".join(f"- {a}" for a in result.marketing_angles)
    full_brief = (
        f"{result.brief}\n\n"
        f"Mood: {result.mood}\n\n"
        f"Marketing angles:\n{angles_text}"
    )

    agents_completed = list(state.get("agents_completed", []))
    if "music_analyst" not in agents_completed:
        agents_completed.append("music_analyst")

    logger.info("music_analyst: brief generated (mood=%s)", result.mood)
    return {
        "music_brief": full_brief,
        "agents_completed": agents_completed,
        "current_node": "music_analyst",
        "clarification_needed": "",
    }

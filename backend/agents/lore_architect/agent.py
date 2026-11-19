"""LoreArchitect LangGraph node.

Retrieves Americana/Outlaw passages from ChromaDB (RAG), then uses an LLM
to generate a 2-3 paragraph backstory grounded in those passages.
Input:  state['music_brief'] (or 'audio_analysis_summary' as fallback) + state['user_context']
Output: state['lore'], state['rag_passages']

Clarification protocol: if user_context lacks a preferred era or tone AND the
passages retrieved are ambiguous, the node can ask the user one focused question.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from agents.base import get_chat_model
from agents.lore_architect.prompts import SYSTEM_PROMPT, build_user_prompt
from agents.lore_architect.tools import retrieve_lore_passages
from workflow.state import WorkflowState

logger = logging.getLogger(__name__)


class LoreOutput(BaseModel):
    backstory: str
    cultural_references: list[str]
    needs_clarification: bool = False
    clarification_question: str = ""


async def run_lore_architect(state: WorkflowState) -> dict:
    """LangGraph node: generates Americana/Outlaw lore using ChromaDB RAG."""
    music_brief = state.get("music_brief", "")
    audio_analysis_summary = state.get("audio_analysis_summary", "")
    user_context: dict[str, Any] = state.get("user_context", {})

    query = music_brief or audio_analysis_summary or "outlaw country Americana"
    passages = await retrieve_lore_passages(query=query, top_k=5)

    model = get_chat_model(temperature=0.7).with_structured_output(LoreOutput)
    logger.info("lore_architect: generating backstory (RAG passages=%d)", len(passages))
    try:
        result: LoreOutput = await model.ainvoke(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_user_prompt(
                        audio_analysis_summary, music_brief, passages, user_context
                    ),
                },
            ]
        )
    except Exception as exc:
        logger.error("lore_architect LLM call failed: %s", exc, exc_info=True)
        raise

    # Clarification protocol
    if result.needs_clarification and result.clarification_question:
        return {
            "clarification_needed": result.clarification_question,
            "clarification_context": "lore_architect: needs more user context to write authentic lore",
            "resume_at": "lore_architect",
            "next": "chat_intake",
            "current_node": "lore_architect",
            "rag_passages": passages,
        }

    agents_completed = list(state.get("agents_completed", []))
    if "lore_architect" not in agents_completed:
        agents_completed.append("lore_architect")

    logger.info("lore_architect: backstory generated (%d chars)", len(result.backstory))
    return {
        "lore": result.backstory,
        "rag_passages": passages,
        "agents_completed": agents_completed,
        "current_node": "lore_architect",
        "clarification_needed": "",
    }

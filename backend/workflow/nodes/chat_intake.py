"""chat_intake LangGraph node — conversational entry point and clarification handler.

This is always the first node when a new session starts. It is also the node
the orchestrator routes back to whenever any other node sets
``state["clarification_needed"]``.

Two modes
---------
1. **Intent gathering** (fresh session or no goal yet):
   The graph is interrupted so the user can send their first message.
   On resume, this node parses the message into ``goal``, ``task_type``,
   and ``user_context``, then clears the interrupt and hands off to the
   orchestrator.

2. **Clarification** (called back by the orchestrator):
   ``state["clarification_needed"]`` is set by another node (e.g.
   lore_architect). The graph interrupts so the user can answer the
   question. On resume, the user's answer is appended to ``messages``,
   merged into ``user_context``, and the clarification fields are cleared
   so the orchestrator routes back to ``state["resume_at"]``.

The interrupt is implemented via ``interrupt_before=["chat_intake"]`` in the
compiled graph. The ``/chat`` endpoint calls ``graph.aupdate_state`` to inject
the user's new message, then resumes the graph.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from agents.base import get_chat_model
from workflow.state import Message, TaskType, WorkflowState

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are the intake assistant for a country music marketing AI platform.
Your job is to understand exactly what the user wants to create and extract all
the information needed to route their request to the right capabilities.

You must determine:
1. task_type — one of:
     instagram_post    → single Instagram caption + hashtags
     twitter_post      → single Twitter/X tweet
     tiktok_post       → single TikTok caption
     social_media_suite → all three platforms
     image_prompt      → a prompt for an AI image generator representing the song
     video_script      → a short (15-30s) video script for the track
     audio_analysis_only → just analyse the track, no content generation
     unknown           → you cannot determine the task yet

2. goal — a clear natural-language description of the desired outcome

3. user_context — any additional facts that will help the content nodes:
     - tone (e.g. "melancholic", "rowdy", "nostalgic")
     - era or historical period (e.g. "1970s outlaw country")
     - band or artist name
     - target audience
     - specific platform preferences
     - any creative direction given by the user

If critical information is missing, you may ask one focused follow-up question.
Set clarification_question to that question, or null if you have enough to proceed.
"""


class IntentOutput(BaseModel):
    task_type: TaskType
    goal: str
    user_context: dict[str, Any]
    clarification_question: str | None = None
    assistant_reply: str


async def run_chat_intake(state: WorkflowState) -> dict:
    """LangGraph node: parses user intent or handles a clarification answer.

    This node always expects a user message to already be appended to
    state["messages"] before it runs. The /chat endpoint is responsible
    for injecting that message via graph.aupdate_state before resuming.
    """
    messages: list[Message] = list(state.get("messages", []))
    clarification_needed = state.get("clarification_needed", "")
    resume_at = state.get("resume_at", "")

    # Build conversation history for the LLM
    llm_messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in messages:
        llm_messages.append({"role": m["role"], "content": m["content"]})

    # If this is a clarification response, give the LLM context
    if clarification_needed:
        llm_messages.append({
            "role": "system",
            "content": (
                f"The user is answering a clarification question from node "
                f"'{resume_at}': \"{clarification_needed}\". "
                "Extract the answer and merge it into user_context. "
                "Set task_type and goal from existing conversation context. "
                "Do NOT ask another clarification question — set clarification_question to null."
            ),
        })

    model = get_chat_model(temperature=0.2).with_structured_output(IntentOutput)
    try:
        result: IntentOutput = await model.ainvoke(llm_messages)
    except Exception as exc:
        logger.error("chat_intake LLM call failed: %s", exc, exc_info=True)
        raise
    logger.info(
        "Intent parsed: task_type=%s clarification=%s",
        result.task_type,
        bool(result.clarification_question),
    )

    # Append assistant reply to conversation history
    messages.append({"role": "assistant", "content": result.assistant_reply})

    # Merge new user_context with existing
    existing_context: dict[str, Any] = dict(state.get("user_context", {}))
    existing_context.update(result.user_context)

    # Determine routing
    if result.clarification_question and not clarification_needed:
        # We still need more info — interrupt again for another user turn.
        # Write the question as an assistant message (already in messages via
        # assistant_reply above). The graph will interrupt at chat_intake again.
        return {
            "messages": messages,
            "goal": result.goal,
            "task_type": result.task_type,
            "user_context": existing_context,
            "clarification_needed": result.clarification_question,
            "clarification_context": "chat_intake: gathering intent",
            "resume_at": "chat_intake",
            "next": "chat_intake",
            "current_node": "chat_intake",
        }

    # Clear clarification fields — we have what we need
    return {
        "messages": messages,
        "goal": result.goal,
        "task_type": result.task_type,
        "user_context": existing_context,
        "clarification_needed": "",
        "clarification_context": "",
        "resume_at": "",
        "next": "orchestrator",
        "current_node": "chat_intake",
    }


def route_from_chat_intake(state: WorkflowState) -> str:
    """Conditional edge: chat_intake routes to orchestrator or loops back."""
    return state.get("next", "orchestrator")

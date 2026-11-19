"""LangGraph graph assembly and public API.

Graph topology
--------------

    START
      │
    chat_intake            [INTERRUPT] — user sends first message / answers question
      │
      ├──(next == "chat_intake") ──► chat_intake  (still gathering intent)
      │
      └──(next == "orchestrator") ─► orchestrator  (LLM router)
              │
              ├──[analyze_audio]   ──► analyze_audio ──► orchestrator
              ├──[music_analyst]   ──► music_analyst  ──► orchestrator
              ├──[lore_architect]  ──► lore_architect ──► orchestrator
              ├──[content_director]──► content_director ──► orchestrator
              │
              ├──[chat_intake]     ──► chat_intake  [INTERRUPT] (clarification)
              │
              └──[execute_production] ──► [INTERRUPT – human approval]
                                                │
                                         execute_production
                                                │
                                               END

Interrupts
----------
``interrupt_before=["chat_intake", "execute_production"]``

- ``chat_intake`` pauses for every user turn (first message + clarifications).
- ``execute_production`` pauses for human approval of the chosen proposal.

Both are resumed by injecting new state via ``graph.aupdate_state`` and then
calling ``graph.astream(None, config)``.

Checkpointing
-------------
Uses AsyncPostgresSaver (psycopg3) instead of MemorySaver, so state
survives container restarts. Initialised in main.py lifespan.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from langgraph.graph import END, StateGraph

from agents.content_director.agent import run_content_director
from agents.lore_architect.agent import run_lore_architect
from agents.music_analyst.agent import run_music_analyst
from workflow.nodes.analyze_audio import analyze_audio
from workflow.nodes.chat_intake import route_from_chat_intake, run_chat_intake
from workflow.nodes.execute_production import execute_production
from workflow.nodes.image_generator import run_image_generator
from workflow.nodes.orchestrator import route_from_orchestrator, run_orchestrator
from workflow.nodes.video_concept_writer import run_video_concept_writer
from workflow.state import Message, WorkflowState

# ---------------------------------------------------------------------------
# Module-level graph singleton (set in main.py lifespan via set_graph)
# ---------------------------------------------------------------------------
_graph = None

logger = logging.getLogger(__name__)


def set_graph(compiled_graph: Any) -> None:
    global _graph
    _graph = compiled_graph


def _get_graph() -> Any:
    if _graph is None:
        raise RuntimeError(
            "Graph not initialized. Ensure the FastAPI lifespan has started."
        )
    return _graph


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_graph(checkpointer: Any) -> Any:
    """Build and compile the LangGraph StateGraph.

    Parameters
    ----------
    checkpointer:
        An AsyncPostgresSaver (or any LangGraph checkpointer) returned by
        ``workflow.config.init_checkpointer()``.
    """
    builder: StateGraph = StateGraph(WorkflowState)

    # ---- Nodes ---------------------------------------------------------------
    builder.add_node("chat_intake", run_chat_intake)
    builder.add_node("orchestrator", run_orchestrator)
    builder.add_node("analyze_audio", analyze_audio)
    builder.add_node("music_analyst", run_music_analyst)
    builder.add_node("lore_architect", run_lore_architect)
    builder.add_node("content_director", run_content_director)
    builder.add_node("image_generator", run_image_generator)
    builder.add_node("video_concept_writer", run_video_concept_writer)
    builder.add_node("execute_production", execute_production)

    # ---- Edges ---------------------------------------------------------------
    builder.set_entry_point("chat_intake")

    # chat_intake loops back if still gathering intent, else hands off
    builder.add_conditional_edges(
        "chat_intake",
        route_from_chat_intake,
        {
            "chat_intake": "chat_intake",
            "orchestrator": "orchestrator",
        },
    )

    # Orchestrator routes dynamically based on state["next"]
    builder.add_conditional_edges(
        "orchestrator",
        route_from_orchestrator,
        {
            "analyze_audio": "analyze_audio",
            "music_analyst": "music_analyst",
            "lore_architect": "lore_architect",
            "content_director": "content_director",
            "image_generator": "image_generator",
            "video_concept_writer": "video_concept_writer",
            "execute_production": "execute_production",
            "chat_intake": "chat_intake",
        },
    )

    # Deterministic audio analysis feeds back to the orchestrator
    builder.add_edge("analyze_audio", "orchestrator")

    # Each agent returns to the orchestrator for the next routing decision
    builder.add_edge("music_analyst", "orchestrator")
    builder.add_edge("lore_architect", "orchestrator")
    builder.add_edge("content_director", "orchestrator")
    builder.add_edge("image_generator", "orchestrator")
    builder.add_edge("video_concept_writer", "orchestrator")
    builder.add_edge("execute_production", END)

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["chat_intake", "execute_production"],
    )


# ---------------------------------------------------------------------------
# Public API used by FastAPI routes
# ---------------------------------------------------------------------------


async def start_session(
    campaign_id: str,
    audio_path: str | None = None,
) -> tuple[str, str]:
    """Create a new thread and advance to the first chat_intake interrupt.

    The graph will pause immediately at ``chat_intake`` waiting for the user's
    opening message.

    Returns
    -------
    (thread_id, assistant_greeting)
        ``thread_id`` is the opaque ID needed for all subsequent /chat calls.
        ``assistant_greeting`` is the welcome message from the system (empty
        string if the node hasn't emitted one yet — handled by the route).
    """
    graph = _get_graph()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    initial: WorkflowState = {
        "campaign_id": campaign_id,
        "audio_path": audio_path or "",
        "messages": [],
        "goal": "",
        "task_type": "unknown",
        "user_context": {},
        "clarification_needed": "",
        "clarification_context": "",
        "resume_at": "",
        "selected_proposal_index": 0,
        "reviewer_notes": "",
        "image_assets": [],
        "video_scripts": [],
        "error": None,
    }

    logger.info("Starting session campaign=%s thread=%s", campaign_id, thread_id)
    # Advance the graph — it will stop at the first chat_intake interrupt
    async for _ in graph.astream(initial, config=config):
        pass

    logger.info("Session ready (paused at chat_intake) thread=%s", thread_id)
    return thread_id, ""


async def send_message(thread_id: str, content: str) -> dict[str, Any]:
    """Inject a user message and resume the graph until the next interrupt.

    The graph pauses at ``chat_intake`` (for conversational turns) or
    ``execute_production`` (for human approval of proposals).

    Returns the updated state snapshot plus helper booleans:
    - ``waiting_for_input``  → True when paused at chat_intake
    - ``waiting_for_approval`` → True when paused at execute_production
    - ``assistant_message``  → last assistant turn from state["messages"]

    Raises ``RuntimeError`` if the thread does not exist or has already finished.
    """
    graph = _get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    # ---- Guard: thread must exist and be paused at an interrupt --------------
    snapshot = await graph.aget_state(config)

    if snapshot is None or not snapshot.values:
        raise RuntimeError(
            f"Thread {thread_id!r} does not exist or has no saved state. "
            "Call start_session() first."
        )

    next_nodes: list[str] = list(snapshot.next) if snapshot.next else []

    if not next_nodes:
        raise RuntimeError(
            f"Thread {thread_id!r} has already completed (reached END). "
            "Start a new session to continue."
        )

    # Only accept user messages when the graph is paused at chat_intake.
    # execute_production is resumed via resume_workflow(), not send_message().
    if "execute_production" in next_nodes:
        raise RuntimeError(
            f"Thread {thread_id!r} is waiting for proposal approval, not a chat message. "
            "Use resume_workflow() to approve a proposal."
        )

    logger.info("send_message: injecting user message on thread=%s", thread_id)
    # ---- Inject the user message into the paused state ----------------------
    current_messages: list[Message] = list(snapshot.values.get("messages", []))
    current_messages.append({"role": "user", "content": content})

    await graph.aupdate_state(config, {"messages": current_messages})

    # ---- Resume — runs until the next interrupt or END ----------------------
    try:
        async for _ in graph.astream(None, config=config):
            pass
    except Exception as exc:
        logger.error("Graph execution error on thread=%s: %s", thread_id, exc, exc_info=True)
        raise

    updated = await graph.aget_state(config)
    state: dict[str, Any] = dict(updated.values) if updated else {}

    # Determine which interrupt we're paused at
    next_nodes: list[str] = list(updated.next) if updated and updated.next else []
    waiting_for_input = "chat_intake" in next_nodes
    waiting_for_approval = "execute_production" in next_nodes

    # Surface the latest assistant message if available
    messages: list[Message] = state.get("messages", [])
    assistant_message = next(
        (m["content"] for m in reversed(messages) if m["role"] == "assistant"),
        "",
    )

    return {
        "thread_id": thread_id,
        "state": state,
        "waiting_for_input": waiting_for_input,
        "waiting_for_approval": waiting_for_approval,
        "clarification_needed": state.get("clarification_needed", ""),
        "assistant_message": assistant_message,
    }


async def get_state(thread_id: str) -> dict[str, Any]:
    """Return the current state snapshot plus waiting-state flags for the given thread."""
    graph = _get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = await graph.aget_state(config)
    if snapshot is None:
        return {}
    values: dict[str, Any] = dict(snapshot.values) if hasattr(snapshot, "values") else {}
    next_nodes: list[str] = list(snapshot.next) if snapshot and snapshot.next else []
    values["_waiting_for_input"] = "chat_intake" in next_nodes
    values["_waiting_for_approval"] = "execute_production" in next_nodes
    return values


async def resume_workflow(
    thread_id: str,
    selected_proposal_index: int,
    reviewer_notes: str = "",
) -> dict[str, Any]:
    """Inject the human's approval and run execute_production to completion.

    Returns the final streamed chunk dict from the graph.
    """
    graph = _get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    await graph.aupdate_state(
        config,
        {
            "selected_proposal_index": selected_proposal_index,
            "reviewer_notes": reviewer_notes,
        },
    )

    logger.info(
        "resume_workflow: thread=%s proposal=%d notes=%r",
        thread_id,
        selected_proposal_index,
        reviewer_notes[:60] if reviewer_notes else "",
    )
    final: dict[str, Any] = {}
    try:
        async for chunk in graph.astream(None, config=config):
            final = chunk
    except Exception as exc:
        logger.error("Workflow resumption failed on thread=%s: %s", thread_id, exc, exc_info=True)
        raise
    logger.info("Workflow complete on thread=%s", thread_id)
    return final

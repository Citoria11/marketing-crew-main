"""Shared WorkflowState TypedDict for the LangGraph graph.

Kept in its own module so both the workflow package and the agents package
can import it without creating circular dependencies.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from typing_extensions import TypedDict

# Supported high-level task types. The orchestrator uses this to decide which
# subgraph of nodes to invoke. New task types can be added here and handled
# in the orchestrator's routing logic.
TaskType = Literal[
    "instagram_post",
    "twitter_post",
    "tiktok_post",
    "social_media_suite",   # all three platforms
    "image_prompt",         # generate image generation prompt
    "video_script",         # write a short video script
    "audio_analysis_only",  # just analyse the track, no content
    "unknown",              # orchestrator needs to clarify
]


class Message(TypedDict):
    """A single chat turn."""
    role: Literal["user", "assistant"]
    content: str


class WorkflowState(TypedDict, total=False):
    # ---- Conversation / intent -----------------------------------------------
    messages: list[Message]
    """Full conversation history between the user and chat_intake."""

    goal: str
    """Parsed natural-language description of what the user wants to achieve."""

    task_type: TaskType
    """Structured task classification parsed from the conversation."""

    user_context: dict[str, Any]
    """Extra facts collected during the conversation (e.g. tone, era, platform
    preferences, band name) that nodes can read to personalise their output."""

    # ---- Clarification protocol (any node can set these) --------------------
    clarification_needed: str
    """If a node cannot proceed, it sets this to the question it needs answered.
    The orchestrator detects this and routes back to chat_intake."""

    clarification_context: str
    """The node that raised the clarification request uses this to give the
    chat_intake node extra context (e.g. 'lore_architect: needs historical era')."""

    resume_at: str
    """After the user answers a clarification, the orchestrator routes back to
    this node name so it can re-run with the enriched state."""

    # ---- Input ---------------------------------------------------------------
    campaign_id: str
    """UUID string of the Campaign row in PostgreSQL."""

    audio_path: str
    """Absolute filesystem path to the uploaded audio file."""

    # ---- analyze_audio node (deterministic, no LLM) -------------------------
    audio_analysis: dict[str, Any]
    """Raw librosa results: BPM, key, hook timestamps, spectral features."""

    audio_analysis_summary: str
    """One-line human-readable summary of the librosa results."""

    # ---- Orchestrator routing -----------------------------------------------
    next: str
    """Routing key read by the conditional edge from the orchestrator node."""

    agents_completed: list[str]
    """Names of agent nodes that have already produced output this run."""

    iteration_count: int
    """Number of times the orchestrator has been called. Guards against loops."""

    # ---- music_analyst node -------------------------------------------------
    music_brief: str
    """Marketing-oriented interpretation of the audio analysis."""

    # ---- lore_architect node ------------------------------------------------
    lore: str
    """2-3 paragraph Americana/Outlaw backstory for the artist and track."""

    rag_passages: list[str]
    """ChromaDB passages retrieved during lore generation (for traceability)."""

    # ---- content_director node ----------------------------------------------
    social_media_proposals: list[dict[str, Any]]
    """List of platform-specific post proposals (Instagram / Twitter-X / TikTok).
    Each proposal includes: copy, hashtags, hook_reference, visual_direction,
    video_concept."""

    # ---- image_generator node -----------------------------------------------
    image_assets: list[dict[str, Any]]
    """DALL-E 3 generated images, one per proposal that had a visual_direction.
    Each item: {proposal_idx, platform, prompt, size, url, error}."""

    # ---- video_concept_writer node ------------------------------------------
    video_scripts: list[dict[str, Any]]
    """Expanded video director treatments + optional Gemini Veo 2 clip URLs.
    Each item: {proposal_idx, platform, concept, script, video_url, error}."""

    # ---- Human approval stage -----------------------------------------------
    selected_proposal_index: int
    """0-based index of the proposal chosen by the human reviewer."""

    reviewer_notes: str
    """Optional freeform reviewer feedback injected before execute_production."""

    # ---- execute_production node --------------------------------------------
    production_assets: dict[str, Any]
    """Final production-ready assets assembled after human approval."""

    # ---- Bookkeeping --------------------------------------------------------
    current_node: str
    """Name of the node currently executing (set by each node at entry)."""

    error: Optional[str]
    """Set by any node that encounters an unrecoverable error."""

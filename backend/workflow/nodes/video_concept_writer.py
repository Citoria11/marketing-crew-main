"""video_concept_writer LangGraph node.

Two-stage video production:

Stage 1 — Script (always runs):
    An LLM writes a production-ready short-form video script for every
    proposal that has a ``video_concept`` field, turning the rough concept
    into a full director's treatment with shot-by-shot breakdown.

Stage 2 — Video generation (runs if GEMINI_API_KEY is set):
    Google Gemini Veo 2 generates a short video clip (8 seconds) from the
    script's visual description.  The result URL is stored alongside the
    script.  If the key is not set the node silently skips Stage 2 and only
    returns the written scripts — the frontend can display the concept while
    the user sets up their key.

Alternative providers (not implemented here):
    - Runway ML (runwayml.com) — Gen-3 Alpha is excellent for music videos
    - OpenAI Sora (coming via API)
    Both accept a text prompt and return a video URL with a similar pattern.

Requires:
    state["social_media_proposals"]  — each with a "video_concept" string
    state["music_brief"]             — context for the script LLM

Produces:
    state["video_scripts"]           — list of VideoScript dicts
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from agents.base import get_chat_model
from workflow.state import WorkflowState

logger = logging.getLogger(__name__)

SCRIPT_SYSTEM_PROMPT = """\
You are a short-form video director specialising in country music content for
Instagram Reels and TikTok. You receive a rough video concept and expand it
into a production-ready script with:

  opening_hook    — the first 3 seconds (text on screen or action) — must stop
                    the scroll immediately
  shot_list       — numbered sequence of visual shots (4-8 shots), each with:
                    duration, action/visual, audio cue
  music_sync      — specific moments in the track to sync to cuts (e.g. "cut at
                    the snare hit at 0:34")
  cta             — the final call-to-action (e.g. "Save for your next road trip")
  caption_hook    — the first line of the post caption (separate from the video)

Keep total runtime 15-30 seconds for TikTok, 30-60 seconds for Reels.
Write in present tense, as if giving direction on set.
"""


async def _write_script(concept: str, music_brief: str, platform: str) -> dict[str, Any]:
    """Use the LLM to expand a rough concept into a full director treatment."""
    model = get_chat_model(temperature=0.7)
    prompt = (
        f"Platform: {platform}\n\n"
        f"Music brief:\n{music_brief}\n\n"
        f"Rough video concept:\n{concept}\n\n"
        "Expand this into a production-ready short-form video script."
    )
    response = await model.ainvoke([
        {"role": "system", "content": SCRIPT_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ])
    return {
        "platform": platform,
        "concept": concept,
        "script": response.content,
        "video_url": None,
        "error": None,
    }


async def _generate_video_gemini(script: str) -> str | None:
    """
    Call Gemini Veo 2 to render an 8-second video clip.

    Requires: pip install google-generativeai>=0.8.0
              GEMINI_API_KEY environment variable

    Returns the video file URI from Google's file API, or None on failure.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None

    try:
        import google.generativeai as genai  # type: ignore[import]
        genai.configure(api_key=api_key)

        model = genai.GenerativeModel("models/veo-2.0-generate-001")
        operation = model.generate_video(
            prompt=script[:2000],  # Veo 2 accepts up to 2000 chars
            config={
                "duration_seconds": 8,
                "aspect_ratio": "9:16",  # vertical for mobile feeds
            },
        )
        # Wait for async generation (typically 30-90s)
        result = await asyncio.to_thread(operation.result)
        if result and result.generated_videos:
            return result.generated_videos[0].video.uri
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gemini Veo 2 generation failed: %s", exc)
    return None


async def run_video_concept_writer(state: WorkflowState) -> dict:
    """LangGraph node: writes video scripts and optionally generates clips."""
    proposals: list[dict[str, Any]] = state.get("social_media_proposals", [])
    music_brief: str = state.get("music_brief", "")
    logger.info(
        "video_concept_writer: %d proposals, Gemini=%s",
        len(proposals),
        bool(os.environ.get("GEMINI_API_KEY")),
    )

    # Gather proposals that have a non-empty video_concept
    to_process = [
        (idx, p)
        for idx, p in enumerate(proposals)
        if p.get("video_concept", "").strip()
    ]

    if not to_process:
        return {
            "video_scripts": [],
            "current_node": "video_concept_writer",
            "agents_completed": _add_completed(state, "video_concept_writer"),
        }

    # Stage 1 — write all scripts concurrently
    script_tasks = [
        _write_script(p["video_concept"], music_brief, p.get("platform", ""))
        for _, p in to_process
    ]
    scripts = await asyncio.gather(*script_tasks)

    # Stage 2 — generate videos with Gemini Veo 2 (if key is present)
    gemini_available = bool(os.environ.get("GEMINI_API_KEY"))
    if gemini_available:
        video_tasks = [_generate_video_gemini(s["script"]) for s in scripts]
        video_urls = await asyncio.gather(*video_tasks, return_exceptions=True)
        for script, url_result in zip(scripts, video_urls):
            if isinstance(url_result, str):
                script["video_url"] = url_result
            elif isinstance(url_result, Exception):
                script["error"] = str(url_result)

    # Attach proposal_idx metadata
    video_scripts = []
    for (idx, _), script in zip(to_process, scripts):
        video_scripts.append({"proposal_idx": idx, **script})

    return {
        "video_scripts": video_scripts,
        "current_node": "video_concept_writer",
        "agents_completed": _add_completed(state, "video_concept_writer"),
        "clarification_needed": "",
    }


def _add_completed(state: WorkflowState, node: str) -> list[str]:
    done = list(state.get("agents_completed", []))
    if node not in done:
        done.append(node)
    return done

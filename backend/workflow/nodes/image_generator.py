"""image_generator LangGraph node.

Calls the OpenAI Images API (DALL-E 3) for every proposal that has a
``visual_direction`` field set, and stores the resulting URLs in
``state["image_assets"]``.

Requires:
    state["social_media_proposals"]  — each with a "visual_direction" string

Produces:
    state["image_assets"]            — list of ImageAsset dicts

DALL-E 3 generates 1024×1024 by default.  Instagram/TikTok work best at
1024×1792 (portrait/9:16) or 1792×1024 (landscape).  Size is chosen by
platform automatically.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from openai import AsyncOpenAI

from workflow.state import WorkflowState

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Image generation requires a valid OpenAI API key."
            )
        _client = AsyncOpenAI(api_key=api_key)
    return _client


# Platforms that should get a portrait (9:16) image for mobile feeds
_PORTRAIT_PLATFORMS = {"Instagram", "TikTok", "instagram_post", "tiktok_post"}


async def _generate_image(prompt: str, size: str) -> str:
    """Call DALL-E 3 and return the image URL (valid for ~1 hour)."""
    response = await _get_client().images.generate(
        model="dall-e-3",
        prompt=prompt,
        size=size,         # type: ignore[arg-type]
        quality="standard",
        n=1,
    )
    return response.data[0].url or ""


async def run_image_generator(state: WorkflowState) -> dict:
    """LangGraph node: generate images for all proposals that have a visual_direction."""
    proposals: list[dict[str, Any]] = state.get("social_media_proposals", [])
    logger.info("image_generator: processing %d proposals", len(proposals))

    tasks = []
    meta: list[dict[str, Any]] = []

    for idx, proposal in enumerate(proposals):
        direction = proposal.get("visual_direction", "").strip()
        if not direction:
            continue

        platform = proposal.get("platform", "")
        size = "1024x1792" if platform in _PORTRAIT_PLATFORMS else "1024x1024"

        tasks.append(_generate_image(direction, size))
        meta.append({
            "proposal_idx": idx,
            "platform": platform,
            "prompt": direction,
            "size": size,
        })

    if not tasks:
        return {
            "image_assets": [],
            "current_node": "image_generator",
            "agents_completed": _add_completed(state, "image_generator"),
        }

    urls = await asyncio.gather(*tasks, return_exceptions=True)

    image_assets: list[dict[str, Any]] = []
    failed = 0
    for info, result in zip(meta, urls):
        if isinstance(result, Exception):
            logger.error(
                "DALL-E 3 failed for proposal %d (%s): %s",
                info["proposal_idx"],
                info["platform"],
                result,
            )
            image_assets.append({**info, "url": None, "error": str(result)})
            failed += 1
        else:
            image_assets.append({**info, "url": result, "error": None})
    logger.info(
        "image_generator: %d images generated, %d failed",
        len(image_assets) - failed,
        failed,
    )

    return {
        "image_assets": image_assets,
        "current_node": "image_generator",
        "agents_completed": _add_completed(state, "image_generator"),
        "clarification_needed": "",
    }


def _add_completed(state: WorkflowState, node: str) -> list[str]:
    done = list(state.get("agents_completed", []))
    if node not in done:
        done.append(node)
    return done

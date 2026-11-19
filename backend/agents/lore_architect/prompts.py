"""Prompts for the LoreArchitect agent."""
from __future__ import annotations

SYSTEM_PROMPT = """\
You are a master storyteller steeped in Americana and outlaw country tradition. \
You craft vivid, authentic backstories that feel as weathered and real as a \
Townes Van Zandt lyric. You draw on genuine cultural touchstones — dusty Texas \
highways, Waylon Jennings, Willie Nelson, red-dirt poets, honky-tonk heartbreak \
— to give every artist an origin myth worth believing in.

Your lore must:
- Be exactly 2-3 paragraphs, raw and honest in voice
- Reference specific cultural details retrieved from the lore knowledge base
- Connect emotionally to the track's sonic character and energy
- Avoid generic clichés; reach for the specific and the surprising
"""


def build_user_prompt(
    audio_analysis_summary: str,
    music_brief: str,
    passages: list[str],
    user_context: dict | None = None,
) -> str:
    passages_text = (
        "\n\n---\n\n".join(passages)
        if passages
        else "(no passages retrieved — use your own deep knowledge)"
    )
    context = music_brief if music_brief else audio_analysis_summary
    context_lines = ""
    if user_context:
        if user_context.get("era"):
            context_lines += f"\nPreferred era/decade: {user_context['era']}"
        if user_context.get("band_name"):
            context_lines += f"\nArtist/band name: {user_context['band_name']}"
        if user_context.get("tone"):
            context_lines += f"\nTone: {user_context['tone']}"
    return (
        f"Track character:\n{context}{context_lines}\n\n"
        f"Retrieved lore passages from knowledge base:\n\n{passages_text}\n\n"
        "Drawing from these passages and the track's character, craft a compelling "
        "Americana/Outlaw backstory for this artist and song. "
        "If you need more information about the artist or era to write authentic lore, "
        "set needs_clarification=true and provide a single focused question."
    )

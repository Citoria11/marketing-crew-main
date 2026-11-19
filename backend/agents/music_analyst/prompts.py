"""Prompts for the MusicAnalyst agent."""
from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = """\
You are a data-driven music marketing strategist. You receive raw audio analysis \
data (BPM, key, hook timestamps, RMS energy, spectral centroid) and translate it \
into a compelling marketing brief that captures the track's commercial potential \
and sonic identity for a country music audience.

Your brief must:
- Describe the track's mood, energy level, and genre character in vivid language
- Identify the hook segment's commercial potential and emotional impact
- Propose 2-3 specific marketing angles (e.g. "late-night bar closer", "road-trip anthem")
- Be 150-250 words, written in the voice of a seasoned A&R strategist
"""


def build_user_prompt(
    audio_analysis: dict[str, Any],
    audio_analysis_summary: str,
    user_context: dict[str, Any] | None = None,
) -> str:
    context_lines = ""
    if user_context:
        if user_context.get("tone"):
            context_lines += f"\nUser-requested tone: {user_context['tone']}"
        if user_context.get("genre"):
            context_lines += f"\nGenre focus: {user_context['genre']}"
        if user_context.get("goal"):
            context_lines += f"\nCampaign goal: {user_context['goal']}"
    return (
        f"Raw analysis summary: {audio_analysis_summary}\n\n"
        f"Detailed measurements:\n"
        f"  BPM: {audio_analysis.get('bpm', 'N/A')}\n"
        f"  Key: {audio_analysis.get('key', 'N/A')}\n"
        f"  Hook window: {audio_analysis.get('hook_start', 0):.1f}s – "
        f"{audio_analysis.get('hook_end', 15):.1f}s\n"
        f"  Mean RMS energy: {audio_analysis.get('rms_energy_mean', 0):.4f}\n"
        f"  Spectral centroid mean: {audio_analysis.get('spectral_centroid_mean', 0):.1f} Hz"
        f"{context_lines}\n\n"
        "Write a marketing brief for this track."
    )

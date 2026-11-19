"""analyze_audio LangGraph node — deterministic librosa analysis.

No LLM call. Runs librosa via asyncio.to_thread to avoid blocking the event loop.
Input:  state['audio_path']
Output: state['audio_analysis'], state['audio_analysis_summary']
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from workflow.state import WorkflowState

logger = logging.getLogger(__name__)

try:
    import librosa
    import numpy as np

    _LIBROSA_AVAILABLE = True
except ImportError:  # pragma: no cover
    _LIBROSA_AVAILABLE = False


def _run_librosa(audio_path: str) -> dict[str, Any]:
    """Synchronous librosa analysis — called via asyncio.to_thread."""
    if not _LIBROSA_AVAILABLE:
        return {
            "bpm": 120.0,
            "key": "G major",
            "hook_start": 30.0,
            "hook_end": 45.0,
            "spectral_centroid_mean": 2500.0,
            "rms_energy_mean": 0.05,
            "note": "librosa not installed – placeholder values.",
        }

    y, sr = librosa.load(audio_path, sr=None, mono=True)

    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(tempo)

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    pitch_classes = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    key = f"{pitch_classes[int(np.argmax(chroma.mean(axis=1)))]} major"

    rms = librosa.feature.rms(y=y)
    rms_mean = float(np.mean(rms))

    sc = librosa.feature.spectral_centroid(y=y, sr=sr)
    sc_mean = float(np.mean(sc))

    hop_length = 512
    hook_duration = 15.0
    frame_duration = hop_length / sr
    hook_frames = int(hook_duration / frame_duration)
    rms_flat = rms[0]

    if len(rms_flat) < hook_frames:
        hook_start = 0.0
    else:
        energy_windows = np.convolve(rms_flat, np.ones(hook_frames), mode="valid")
        hook_start = float(int(np.argmax(energy_windows)) * frame_duration)

    return {
        "bpm": bpm,
        "key": key,
        "hook_start": hook_start,
        "hook_end": hook_start + hook_duration,
        "spectral_centroid_mean": sc_mean,
        "rms_energy_mean": rms_mean,
    }


async def analyze_audio(state: WorkflowState) -> dict:
    """LangGraph node: runs librosa analysis on the uploaded audio file."""
    audio_path: str = state.get("audio_path", "")

    if not audio_path or not os.path.exists(audio_path):
        return {
            "current_node": "analyze_audio",
            "error": f"Audio file not found: {audio_path!r}",
            "audio_analysis": {},
            "audio_analysis_summary": "No audio file available.",
            "agents_completed": [],
            "iteration_count": 0,
        }

    logger.info("analyze_audio: starting librosa analysis on %s", audio_path)
    try:
        analysis = await asyncio.to_thread(_run_librosa, audio_path)
    except Exception as exc:  # noqa: BLE001
        logger.error("librosa analysis failed: %s", exc, exc_info=True)
        return {
            "current_node": "analyze_audio",
            "error": f"librosa analysis failed: {exc}",
            "audio_analysis": {},
            "audio_analysis_summary": "Audio analysis failed.",
            "agents_completed": [],
            "iteration_count": 0,
        }

    summary = (
        f"BPM: {analysis.get('bpm', 'N/A')}, "
        f"Key: {analysis.get('key', 'N/A')}, "
        f"Hook: {analysis.get('hook_start', 0):.1f}s – {analysis.get('hook_end', 15):.1f}s, "
        f"RMS energy: {analysis.get('rms_energy_mean', 0):.4f}"
    )
    logger.info("analyze_audio: %s", summary)

    existing_completed = list(state.get("agents_completed", []))
    if "analyze_audio" not in existing_completed:
        existing_completed.append("analyze_audio")

    return {
        "current_node": "analyze_audio",
        "audio_analysis": analysis,
        "audio_analysis_summary": summary,
        "agents_completed": existing_completed,
        "iteration_count": 0,
    }

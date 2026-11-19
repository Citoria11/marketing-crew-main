"""Shared LLM client factory for all agents."""
from __future__ import annotations

from langchain_openai import ChatOpenAI


def get_chat_model(model: str = "gpt-4o", temperature: float = 0) -> ChatOpenAI:
    """Return a configured ChatOpenAI instance.

    OPENAI_API_KEY must be set in the environment.
    Uses structured output via .with_structured_output() at the call site.
    """
    return ChatOpenAI(model=model, temperature=temperature)

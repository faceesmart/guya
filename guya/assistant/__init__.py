"""Guya's small, local desktop assistant.

The assistant deliberately understands a limited set of safe actions. It does
not send commands to an LLM and it never executes arbitrary shell text.
"""

from .service import AssistantService

__all__ = ["AssistantService"]

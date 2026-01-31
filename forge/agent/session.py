"""Forge session manager with conversation history and token tracking.

Maintains state across turns for natural conversation flow.
"""
import json
import time
import os
from dataclasses import dataclass, field
from typing import Any, Optional

try:
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
except ImportError:
    HumanMessage = AIMessage = SystemMessage = None


@dataclass
class Message:
    """A single message in the conversation."""
    role: str  # "user", "assistant", "system", "tool"
    content: str
    timestamp: float = field(default_factory=time.time)
    tokens: int = 0  # Estimated token count
    tool_calls: list = field(default_factory=list)
    tool_results: list = field(default_factory=list)


@dataclass
class SessionStats:
    """Token usage statistics for the session."""
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    max_context: int = os.getenv("MAX_CONTEXT", 32768)  # Default for most small models
    turn_count: int = 0
    start_time: float = field(default_factory=time.time)

    @property
    def context_pct(self) -> float:
        """Percentage of context window used."""
        return (self.total_tokens / self.max_context) * 100 if self.max_context > 0 else 0

    @property
    def elapsed_time(self) -> float:
        """Session duration in seconds."""
        return time.time() - self.start_time

    def to_status(self) -> str:
        """Format stats for status bar display."""
        pct = self.context_pct
        return f"T:{self.turn_count} | Tokens:{self.total_tokens}/{self.max_context} ({pct:.0f}%)"


class Session:
    """Manages conversation state for Forge interactive mode."""

    # Model context sizes (approximate)
    MODEL_CONTEXTS = {
        "gemma3:4b": 8192,
        "qwen3:1.7b": 32768,
        "qwen3-vl:8b": 32768,
        "qwen2.5vl:7b": 32768,
        "qwen2.5-coder:3b": 32768,
        "deepseek-r1:7b": 65536,
    }

    def __init__(
        self,
        model: str = "gemma3:4b",
        max_history: int = 10,
        system_prompt: Optional[str] = None,
    ):
        self.model = model
        self.max_history = max_history
        self.messages: list[Message] = []
        self.stats = SessionStats(
            max_context=self.MODEL_CONTEXTS.get(model, 8192)
        )
        self.system_prompt = system_prompt or self._default_system_prompt()

    def _default_system_prompt(self) -> str:
        return (
            "You are Forge, a local-first coding assistant. "
            "Execute tasks using tools. Be concise. "
            "When you need information, use tools to get it. "
            "When you complete a task, summarize what you did."
        )

    def add_user_message(self, content: str) -> None:
        """Add a user message to history."""
        tokens = self._estimate_tokens(content)
        self.messages.append(Message(
            role="user",
            content=content,
            tokens=tokens,
        ))
        self.stats.prompt_tokens += tokens
        self.stats.total_tokens += tokens
        self.stats.turn_count += 1
        self._trim_history()

    def add_assistant_message(
        self,
        content: str,
        tool_calls: Optional[list] = None,
        tool_results: Optional[list] = None,
    ) -> None:
        """Add an assistant message to history."""
        tokens = self._estimate_tokens(content)
        self.messages.append(Message(
            role="assistant",
            content=content,
            tokens=tokens,
            tool_calls=tool_calls or [],
            tool_results=tool_results or [],
        ))
        self.stats.completion_tokens += tokens
        self.stats.total_tokens += tokens
        self._trim_history()

    def get_context_messages(self) -> list:
        """Get messages formatted for LangChain."""
        if HumanMessage is None:
            raise RuntimeError("langchain_core not available")

        lc_messages = [SystemMessage(content=self.system_prompt)]

        for msg in self.messages[-self.max_history:]:
            if msg.role == "user":
                lc_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                lc_messages.append(AIMessage(content=msg.content))

        return lc_messages

    def get_history_summary(self, last_n: int = 5) -> str:
        """Get a text summary of recent history for context injection."""
        lines = []
        for msg in self.messages[-last_n:]:
            prefix = "User: " if msg.role == "user" else "Forge: "
            # Truncate long messages
            content = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
            lines.append(f"{prefix}{content}")
        return "\n".join(lines)

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (4 chars per token average)."""
        return len(text) // 4 + 1

    def _trim_history(self) -> None:
        """Trim oldest messages to stay within context window."""
        # Keep at least 50% of context for new content
        max_history_tokens = self.stats.max_context // 2

        while len(self.messages) > 2:  # Keep at least 2 messages
            total_history = sum(m.tokens for m in self.messages)
            if total_history <= max_history_tokens:
                break
            # Remove oldest message
            removed = self.messages.pop(0)
            self.stats.total_tokens -= removed.tokens

    def reset(self) -> None:
        """Clear history and reset stats."""
        self.messages.clear()
        self.stats = SessionStats(
            max_context=self.MODEL_CONTEXTS.get(self.model, 8192)
        )

    def to_dict(self) -> dict:
        """Serialize session for persistence."""
        return {
            "model": self.model,
            "max_history": self.max_history,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp,
                    "tokens": m.tokens,
                }
                for m in self.messages
            ],
            "stats": {
                "total_tokens": self.stats.total_tokens,
                "prompt_tokens": self.stats.prompt_tokens,
                "completion_tokens": self.stats.completion_tokens,
                "turn_count": self.stats.turn_count,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        """Deserialize session from dict."""
        session = cls(
            model=data.get("model", "gemma3:4b"),
            max_history=data.get("max_history", 10),
        )
        for m in data.get("messages", []):
            session.messages.append(Message(
                role=m["role"],
                content=m["content"],
                timestamp=m.get("timestamp", time.time()),
                tokens=m.get("tokens", 0),
            ))
        stats = data.get("stats", {})
        session.stats.total_tokens = stats.get("total_tokens", 0)
        session.stats.prompt_tokens = stats.get("prompt_tokens", 0)
        session.stats.completion_tokens = stats.get("completion_tokens", 0)
        session.stats.turn_count = stats.get("turn_count", 0)
        return session

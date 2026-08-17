"""Small data objects shared by the assistant parser and action layer."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class ParsedCommand:
    intent: str
    language: str
    slots: Dict[str, str] = field(default_factory=dict)
    original_text: str = ""
    steps: List["ParsedCommand"] = field(default_factory=list)


@dataclass
class AssistantResponse:
    status: str
    message: str
    command: Optional[ParsedCommand] = None
    path: Optional[Path] = None
    language: str = "en"
    options: List[Path] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.status == "success"


@dataclass
class ActionOutcome:
    success: bool
    message_en: str
    message_fa: str
    path: Optional[Path] = None

    def message_for(self, language: str) -> str:
        return self.message_fa if language == "fa" else self.message_en


@dataclass(frozen=True)
class SearchMatch:
    path: Path
    score: float
    exact: bool = False

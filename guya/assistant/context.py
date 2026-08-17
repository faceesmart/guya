"""Short-lived conversational context for references such as "rename it"."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .models import ParsedCommand


@dataclass
class AssistantContext:
    current_path: Optional[Path] = None
    recent_paths: List[Path] = field(default_factory=list)
    pending_command: Optional[ParsedCommand] = None
    pending_path: Optional[Path] = None
    pending_slot: Optional[str] = None
    pending_action: Optional[str] = None
    pending_options: List[Path] = field(default_factory=list)
    pending_option_action: Optional[str] = None

    def remember(self, path: Optional[Path]) -> None:
        if path is not None:
            remembered = Path(path)
            self.current_path = remembered
            self.recent_paths = [
                item for item in self.recent_paths if item != remembered
            ]
            self.recent_paths.insert(0, remembered)
            del self.recent_paths[5:]

    def request_confirmation(
        self,
        command: ParsedCommand,
        path: Path,
        action: str = "rename",
    ) -> None:
        self.pending_command = command
        self.pending_path = Path(path)
        self.pending_slot = None
        self.pending_action = action

    def request_slot(self, command: ParsedCommand, slot: str, path: Optional[Path] = None) -> None:
        self.pending_command = command
        self.pending_path = Path(path) if path is not None else None
        self.pending_slot = slot
        self.pending_action = None

    def request_selection(
        self,
        command: ParsedCommand,
        options: List[Path],
        action: str = "open",
    ) -> None:
        self.pending_command = command
        self.pending_path = None
        self.pending_slot = None
        self.pending_action = None
        self.pending_options = [Path(item) for item in options[:3]]
        self.pending_option_action = action

    def clear_pending(self) -> None:
        self.pending_command = None
        self.pending_path = None
        self.pending_slot = None
        self.pending_action = None
        self.pending_options = []
        self.pending_option_action = None

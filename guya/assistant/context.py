"""Short-lived conversational context for references such as "rename it"."""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .models import ParsedCommand

# A question the assistant asked ("Rename X to Y?", "Open it now?") is only
# valid for a short while. A "yes" spoken minutes later must not rename a
# file the user has forgotten about.
PENDING_TIMEOUT_SEC = 120.0


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
    pending_since: Optional[float] = None

    @property
    def has_pending(self) -> bool:
        return self.pending_command is not None or bool(self.pending_options)

    def pending_expired(self, now: Optional[float] = None) -> bool:
        if not self.has_pending or self.pending_since is None:
            return False
        return (now if now is not None else time.monotonic()) - self.pending_since > PENDING_TIMEOUT_SEC

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
        self.pending_since = time.monotonic()

    def request_slot(self, command: ParsedCommand, slot: str, path: Optional[Path] = None) -> None:
        self.pending_command = command
        self.pending_path = Path(path) if path is not None else None
        self.pending_slot = slot
        self.pending_action = None
        self.pending_since = time.monotonic()

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
        self.pending_since = time.monotonic()

    def clear_pending(self) -> None:
        self.pending_command = None
        self.pending_path = None
        self.pending_slot = None
        self.pending_action = None
        self.pending_options = []
        self.pending_option_action = None
        self.pending_since = None

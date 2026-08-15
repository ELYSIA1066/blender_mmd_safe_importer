"""Structured reporting for Safe MMD Importer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class Diagnostic:
    level: str
    message: str


@dataclass
class Diagnostics:
    events: list[Diagnostic] = field(default_factory=list)

    def info(self, message: str) -> None:
        self.events.append(Diagnostic("INFO", message))

    def warning(self, message: str) -> None:
        self.events.append(Diagnostic("WARNING", message))

    def error(self, message: str) -> None:
        self.events.append(Diagnostic("ERROR", message))

    @property
    def has_errors(self) -> bool:
        return any(event.level == "ERROR" for event in self.events)

    def extend(self, events: Iterable[Diagnostic]) -> None:
        self.events.extend(events)

    def text(self) -> str:
        if not self.events:
            return "No diagnostics recorded."
        return "\n".join(f"[{event.level}] {event.message}" for event in self.events)


def publish(scene, diagnostics: Diagnostics) -> None:
    """Store a compact, namespaced report in the active scene."""
    scene.mmd_safe_import_report = diagnostics.text()

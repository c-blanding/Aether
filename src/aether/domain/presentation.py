from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, Field


class PresentationStyle(BaseModel):
    """
    Host-controlled presentation knobs for narrative and dialogue renderers.

    Defaults preserve current literary third-person behavior.
    """

    tone: str = Field(
        default="literary",
        description=(
            "Presentation tone hint, e.g. literary, terse, lyrical, neutral, noir."
        ),
    )

    length: Literal["terse", "default", "expansive"] = Field(
        default="default",
        description="How long narrative/dialogue beats should run.",
    )

    pov: Literal["third", "second"] = Field(
        default="third",
        description="Narrative point of view.",
    )

    sfw: bool = Field(
        default=True,
        description="When True, keep presentation suitable for general audiences.",
    )

    rails: str = Field(
        default="",
        description="Optional host-enforced rails / style notes (plain text).",
    )


class InteractOptions(BaseModel):
    """Optional knobs for ``Aether.interact``."""

    style: PresentationStyle = Field(
        default_factory=PresentationStyle,
        description="Presentation style for narrative/dialogue renderers.",
    )

    max_steps: int = Field(
        default=6,
        ge=1,
        description="Maximum decide/execute loops for the player planner.",
    )

    max_npc_actions: int = Field(
        default=2,
        ge=0,
        le=3,
        description="Maximum reactive NPC actions after the player beat (0–3).",
    )


class SceneSummary(BaseModel):
    """
    Rolling continuity packet for the current scene.

    Persisted on the session so later interacts stay grounded without restating
    every prior fact in the host message.
    """

    text: str = Field(
        default="",
        description="Short rolling summary of the current scene.",
    )

    location_id: Optional[str] = Field(
        default=None,
        description="Primary location ID for the current scene, if known.",
    )

    character_ids: list[str] = Field(
        default_factory=list,
        description="Character IDs present or recently involved in the scene.",
    )

    tension: str = Field(
        default="",
        description="Short note on current tension or emotional weather.",
    )

    open_threads: list[str] = Field(
        default_factory=list,
        description="Open questions / unresolved beats still in play.",
    )


@dataclass
class PresentationCallbacks:
    """
    Optional host hooks fired during interact.

    Narrative deltas and dialogue lines are emitted only after the beat's
    events have already been committed.
    """

    on_narrative_delta: Optional[Callable[[str], None]] = None
    on_dialogue_line: Optional[Callable[[Any], None]] = None
    on_event: Optional[Callable[[Any], None]] = None


@dataclass
class PresentationChunk:
    """One item yielded by ``Aether.interact_stream``."""

    kind: Literal["event", "narrative_delta", "dialogue_line", "result"]
    text: Optional[str] = None
    event: Any = None
    dialogue: Any = None
    result: Any = None

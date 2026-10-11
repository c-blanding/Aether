from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from aether.domain.presentation import SceneSummary
from aether.modules.dialogue import SPEAKING_EVENT_TYPES


class SceneSummaryDraft(BaseModel):
    """Structured LLM output for refreshing scene continuity."""

    text: str = Field(
        ...,
        description="2–4 sentence rolling summary of the current scene.",
    )
    tension: str = Field(
        default="",
        description="Short tension / emotional weather note.",
    )
    open_threads: list[str] = Field(
        default_factory=list,
        description="Up to 4 open threads still unresolved.",
    )


def _event_type(event: Any) -> Optional[str]:
    if hasattr(event, "type"):
        return event.type
    if isinstance(event, dict):
        return (event.get("data") or {}).get("type") or event.get("type")
    return None


def _event_attrs(event: Any) -> dict[str, Any]:
    if hasattr(event, "data"):
        return dict(getattr(event.data, "attributes", None) or {})
    if isinstance(event, dict):
        return dict((event.get("data") or {}).get("attributes") or {})
    return {}


def heuristic_scene_summary(
    world: Any,
    session: Any,
    *,
    actor_id: str,
    events: list[Any],
    narrative: Optional[str] = None,
) -> SceneSummary:
    """
    Build / refresh a scene summary without an LLM call.

    Used as the default updater and as a fallback when model refresh fails.
    """
    previous = getattr(session, "scene_summary", None) or SceneSummary()
    actor = world.characters.get(actor_id)
    location_id = actor.state.location_id if actor is not None else previous.location_id
    location = world.locations.get(location_id) if location_id else None

    present_ids = [
        character.id
        for character in world.characters.values()
        if character.state.location_id == location_id
    ]
    names = [
        world.describe_character(character_id) for character_id in present_ids[:6]
    ]

    open_threads = list(previous.open_threads)
    for event in events:
        event_type = _event_type(event)
        attrs = _event_attrs(event)
        topic = str(attrs.get("topic") or "").strip()
        if event_type == "question_asked" and topic:
            thread = f"Unanswered question about {topic}"
            if thread not in open_threads:
                open_threads.append(thread)
        if event_type == "question_answered" and topic:
            thread = f"Unanswered question about {topic}"
            open_threads = [item for item in open_threads if item != thread]

    open_threads = open_threads[-4:]

    event_types = [t for t in (_event_type(e) for e in events) if t]
    tension = previous.tension
    if any(t == "evidence_presented" for t in event_types):
        tension = "confrontation over evidence"
    elif any(t in SPEAKING_EVENT_TYPES for t in event_types):
        tension = tension or "active conversation"
    elif event_types:
        tension = tension or "scene in motion"
    elif not tension:
        tension = "calm"

    bits = []
    if location is not None:
        bits.append(f"In the {location.name}")
    if names:
        bits.append("with " + ", ".join(names))
    if narrative:
        bits.append(narrative.strip()[:220])
    elif event_types:
        bits.append("Recent beats: " + ", ".join(event_types[-5:]))
    elif previous.text:
        bits.append(previous.text)

    text = ". ".join(part.rstrip(".") for part in bits if part).strip()
    if text and not text.endswith("."):
        text += "."
    if previous.text and narrative:
        # Keep a short bridge from prior continuity.
        bridge = previous.text[:160].rstrip(".")
        text = f"{bridge}. Now: {text}" if bridge else text
        if len(text) > 480:
            text = text[-480:]

    return SceneSummary(
        text=text or previous.text,
        location_id=location_id,
        character_ids=present_ids or list(previous.character_ids),
        tension=tension,
        open_threads=open_threads,
    )


def refresh_scene_summary(
    *,
    world: Any,
    session: Any,
    actor_id: str,
    events: list[Any],
    narrative: Optional[str] = None,
    model: Any = None,
) -> SceneSummary:
    """
    Update session.scene_summary after a successful interact.

    Prefers a short structured LLM refresh when a model is available;
    otherwise uses the heuristic updater.
    """
    draft = heuristic_scene_summary(
        world,
        session,
        actor_id=actor_id,
        events=events,
        narrative=narrative,
    )

    if model is None:
        session.scene_summary = draft
        return draft

    try:
        prompt = (
            "Update the rolling scene summary for an interactive world SDK.\n"
            "Keep 2–4 sentences. Preserve who/where/tension/open threads.\n"
            "Do not invent new plot facts beyond the committed events and narrative.\n\n"
            f"Previous summary JSON:\n{session.scene_summary.model_dump_json(indent=2)}\n\n"
            f"Heuristic draft JSON:\n{draft.model_dump_json(indent=2)}\n\n"
            f"Committed event types: {[ _event_type(e) for e in events ]}\n"
            f"Narrative:\n{narrative or '(none)'}\n"
        )
        structured = model.with_structured_output(
            SceneSummaryDraft,
            method="function_calling",
        )
        generated: SceneSummaryDraft = structured.invoke(
            [
                {
                    "role": "system",
                    "content": (
                        "You maintain short scene continuity summaries for hosts. "
                        "Stay factual and compact."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
        )
        draft = SceneSummary(
            text=(generated.text or draft.text).strip(),
            location_id=draft.location_id,
            character_ids=draft.character_ids,
            tension=(generated.tension or draft.tension).strip(),
            open_threads=list(generated.open_threads or draft.open_threads)[:4],
        )
    except Exception:  # noqa: BLE001 — continuity must not fail the turn
        pass

    session.scene_summary = draft
    return draft

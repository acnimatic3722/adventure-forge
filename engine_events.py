#!/usr/bin/env python3
"""
AdventureForge — Event System

A project can own an ``events`` list. Each event pairs a *trigger* with a
list of *actions*::

    "events": [
      {
        "id": "ev_intro",
        "name": "Arrival in the lobby",
        "enabled": true,
        "once": true,
        "priority": 0,
        "trigger": {"type": "on_enter_room", "target": "lobby"},
        "actions": [
          {"type": "play_cutscene", "value": "intro"},
          {"type": "set_flag", "value": "met_the_manager"}
        ]
      }
    ]

Trigger types
-------------
``on_game_start``    once, when the runtime boots
``on_enter_room``    when the player walks into a room (``target`` = room id)
``on_flag_set``      when a story flag is raised (``target`` = flag name)
``on_item_pickup``   when an item is collected (``target`` = item id)
``on_hotspot_use``   when a hotspot is interacted with (``target`` = hotspot id)
``on_dialog_end``    when a conversation finishes (``target`` = dialog id)

Action types
------------
``set_flag``      raise a story flag
``clear_flag``    drop a story flag
``play_cutscene`` start a cutscene
``start_dialog``  open a dialog tree
``give_item``     add an item to the inventory
``unlock_door``   unlock a hotspot (clears ``locked``)
``show_text``     say a line of dialogue
``play_sound``    play a sound effect

Everything here is pure. The engine owns the dispatch and the action queue.
"""
from __future__ import annotations

from typing import Any

TRIGGER_TYPES = (
    "on_game_start",
    "on_enter_room",
    "on_flag_set",
    "on_item_pickup",
    "on_hotspot_use",
    "on_dialog_end",
)

# Triggers whose ``target`` must match exactly for the event to fire.
TARGETED_TRIGGERS = ("on_enter_room", "on_item_pickup", "on_hotspot_use", "on_dialog_end")

ACTION_TYPES = (
    "set_flag",
    "clear_flag",
    "play_cutscene",
    "start_dialog",
    "give_item",
    "unlock_door",
    "show_text",
    "play_sound",
)

# Trigger types that were previously expressed as fields on a cutscene.
LEGACY_CUTSCENE_TRIGGERS = ("on_enter_room", "on_flag_set")


def _as_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    if value is None:
        return fallback
    return bool(value)


def _as_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def normalize_action(raw: Any) -> dict[str, Any]:
    """Normalise one event action."""
    if isinstance(raw, str):
        raw = {"type": raw, "value": raw}
    if not isinstance(raw, dict):
        return {"type": "", "value": ""}

    atype = str(raw.get("type") or raw.get("action") or "").strip().lower()
    value = raw.get("value", raw.get("target", raw.get("id", "")))
    if value is None:
        value = ""

    action: dict[str, Any] = {"type": atype, "value": value}

    # Optional per-action extras.
    for extra in ("speaker", "color", "room_id", "hotspot_id", "item_id", "flag"):
        if extra in raw and raw[extra] not in (None, ""):
            action[extra] = raw[extra]

    return action


def normalize_event(event_id: str, raw: Any) -> dict[str, Any]:
    """Normalise one event definition."""
    raw = raw if isinstance(raw, dict) else {}

    raw_trigger = raw.get("trigger")
    if isinstance(raw_trigger, str):
        raw_trigger = {"type": raw_trigger}
    if not isinstance(raw_trigger, dict):
        raw_trigger = {}

    trigger_type = str(
        raw_trigger.get("type") or raw.get("trigger_type") or ""
    ).strip().lower()
    if trigger_type not in TRIGGER_TYPES:
        trigger_type = ""

    target = str(
        raw_trigger.get("target")
        or raw_trigger.get("flag")
        or raw.get("trigger_target")
        or ""
    ).strip()

    raw_actions = raw.get("actions")
    if not isinstance(raw_actions, list):
        raw_actions = []

    return {
        "id": str(event_id or raw.get("id") or "").strip(),
        "name": str(raw.get("name") or raw.get("title") or "").strip(),
        "enabled": _as_bool(raw.get("enabled"), True),
        "once": _as_bool(raw.get("once"), True),
        "priority": _as_int(raw.get("priority"), 0),
        "requires_flag": str(raw.get("requires_flag") or "").strip(),
        "trigger": {
            "type": trigger_type,
            "target": target,
        },
        "actions": [normalize_action(a) for a in raw_actions],
    }


def normalize_events(raw_events: Any) -> list[dict[str, Any]]:
    """Normalise the whole event list, dropping entries without an id."""
    if isinstance(raw_events, dict):
        raw_events = [
            {**value, "id": key} if isinstance(value, dict) else {"id": key}
            for key, value in raw_events.items()
        ]
    if not isinstance(raw_events, list):
        return []

    out: list[dict[str, Any]] = []
    for raw in raw_events:
        event = normalize_event("", raw)
        if event["id"]:
            out.append(event)
    return out


def event_matches(
    event: dict[str, Any],
    trigger_type: str,
    target: str = "",
    flags: set[str] | None = None,
) -> bool:
    """True when an event should fire for the given trigger."""
    if not event.get("enabled", True):
        return False

    trigger = event.get("trigger") or {}
    if trigger.get("type") != trigger_type:
        return False

    wanted = str(trigger.get("target") or "").strip()
    if wanted and trigger_type in TARGETED_TRIGGERS:
        if wanted != target:
            return False
    elif wanted and trigger_type == "on_flag_set":
        if wanted != target:
            return False

    requires = str(event.get("requires_flag") or "").strip()
    if requires and flags is not None and requires not in flags:
        return False

    return True


def sort_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort events by priority (highest first), then by name for stability."""
    return sorted(
        events,
        key=lambda e: (-_as_int(e.get("priority"), 0), str(e.get("name") or e.get("id") or "")),
    )


def migrate_cutscene_triggers(cutscenes: Any) -> list[dict[str, Any]]:
    """Convert legacy cutscene trigger fields into event definitions.

    Older projects expressed triggers as ``trigger_type`` / ``trigger_target``
    fields on a cutscene. Those are turned into ordinary events so there is
    only one mechanism left to reason about.
    """
    if not isinstance(cutscenes, list):
        return []

    events: list[dict[str, Any]] = []
    for cs in cutscenes:
        if not isinstance(cs, dict):
            continue
        cs_id = str(cs.get("id") or "").strip()
        if not cs_id:
            continue

        trigger_type = str(cs.get("trigger_type") or "").strip().lower()
        if trigger_type not in LEGACY_CUTSCENE_TRIGGERS:
            continue

        target = str(cs.get("trigger_target") or "").strip()
        if trigger_type == "on_flag_set" and not target:
            continue

        event = normalize_event(
            f"legacy_{cs_id}",
            {
                "id": f"legacy_{cs_id}",
                "name": f"(migrated) {cs.get('name') or cs_id}",
                "enabled": True,
                "once": _as_bool(cs.get("once"), True),
                "priority": -100,
                "requires_flag": str(cs.get("requires_flag") or ""),
                "trigger": {"type": trigger_type, "target": target},
                "actions": [{"type": "play_cutscene", "value": cs_id}],
            },
        )
        event["legacy"] = True
        events.append(event)

    return events

"""
AdventureForge — Event MCP Tools

Events replace the ad-hoc trigger fields that used to live on cutscenes,
hotspots, puzzles and dialog options. An event pairs a *trigger* with a list
of *actions*, and the runtime dispatches them through one mechanism.

Trigger types
-------------
``on_game_start``    once, when the runtime boots
``on_enter_room``    when the player walks into a room (target = room id)
``on_flag_set``      when a story flag is raised (target = flag name)
``on_item_pickup``   when an item is collected (target = item id)
``on_hotspot_use``   when a hotspot is interacted with (target = hotspot id)
``on_dialog_end``    when a conversation finishes (target = dialog id)

Action types
------------
``set_flag`` ``clear_flag`` ``play_cutscene`` ``start_dialog`` ``give_item``
``unlock_door`` ``show_text`` ``play_sound``
"""
import json
from typing import Any

from engine_events import (
    ACTION_TYPES,
    TRIGGER_TYPES,
    migrate_cutscene_triggers,
    normalize_action,
    normalize_event,
)

from ._core import (
    _load_proj,
    _save_proj,
)


def _clean_id(raw: str, fallback: str = "event") -> str:
    return "".join(ch for ch in str(raw or "").lower() if ch.isalnum() or ch == "_") or fallback


def list_events() -> dict[str, Any]:
    """List every event with its trigger, actions, and whether it has already fired."""
    proj = _load_proj()
    events = proj.get("events")
    if not isinstance(events, list):
        events = []

    out = []
    for idx, raw in enumerate(events):
        event = normalize_event(str(raw.get("id") or f"event_{idx + 1}") if isinstance(raw, dict) else f"event_{idx + 1}", raw)
        out.append({
            "id": event["id"],
            "name": event["name"],
            "enabled": event["enabled"],
            "once": event["once"],
            "priority": event["priority"],
            "requires_flag": event["requires_flag"],
            "trigger": event["trigger"],
            "action_count": len(event["actions"]),
            "actions": event["actions"],
        })
    return {
        "count": len(out),
        "events": out,
        "trigger_types": list(TRIGGER_TYPES),
        "action_types": list(ACTION_TYPES),
    }


def get_event(event_id: str) -> dict[str, Any]:
    """Get one event's full definition."""
    proj = _load_proj()
    for raw in proj.get("events", []) or []:
        if isinstance(raw, dict) and raw.get("id") == event_id:
            return {"event": normalize_event(event_id, raw)}
    return {"error": f"Event '{event_id}' not found."}


def create_or_update_event(
    event_id: str,
    name: str = "",
    trigger_type: str = "on_enter_room",
    trigger_target: str = "",
    once: bool = True,
    priority: int = 0,
    enabled: bool = True,
    requires_flag: str = "",
) -> dict[str, Any]:
    """Create an event, or update the trigger and settings of an existing one.

    trigger_type is one of on_game_start, on_enter_room, on_flag_set,
    on_item_pickup, on_hotspot_use, on_dialog_end. trigger_target is the id
    the trigger matches (a room id, flag name, item id, hotspot id or dialog
    id). Leave it empty to match any target.
    """
    proj = _load_proj()
    clean = _clean_id(event_id)
    events = proj.get("events")
    if not isinstance(events, list):
        events = []
        proj["events"] = events

    existing = next((e for e in events if isinstance(e, dict) and e.get("id") == clean), None)
    if existing is None:
        existing = {"id": clean, "actions": []}
        events.append(existing)

    if name:
        existing["name"] = name
    existing["enabled"] = bool(enabled)
    existing["once"] = bool(once)
    existing["priority"] = int(priority)
    existing["requires_flag"] = requires_flag
    existing["trigger"] = {
        "type": str(trigger_type or "").strip().lower(),
        "target": str(trigger_target or "").strip(),
    }

    _save_proj(proj)
    return {"status": "ok", "event": normalize_event(clean, existing)}


def delete_event(event_id: str) -> dict[str, Any]:
    """Delete an event."""
    proj = _load_proj()
    events = proj.get("events") or []
    before = len(events)
    proj["events"] = [e for e in events if not (isinstance(e, dict) and e.get("id") == event_id)]
    _save_proj(proj)
    return {"status": "ok", "deleted": before - len(proj["events"])}


def add_event_action(
    event_id: str,
    action_type: str,
    value: str = "",
    speaker: str = "",
) -> dict[str, Any]:
    """Append an action to an event.

    action_type is one of set_flag, clear_flag, play_cutscene, start_dialog,
    give_item, unlock_door, show_text, play_sound. value is the flag name,
    id, path or text the action operates on.
    """
    proj = _load_proj()
    events = proj.get("events") or []
    event = next((e for e in events if isinstance(e, dict) and e.get("id") == event_id), None)
    if not event:
        return {"error": f"Event '{event_id}' not found."}

    atype = str(action_type or "").strip().lower()
    if atype not in ACTION_TYPES:
        return {"error": f"Unknown action type '{action_type}'. Valid: {', '.join(ACTION_TYPES)}"}

    action = normalize_action({"type": atype, "value": value})
    if speaker:
        action["speaker"] = speaker

    actions = event.get("actions")
    if not isinstance(actions, list):
        actions = []
    actions.append(action)
    event["actions"] = actions

    _save_proj(proj)
    return {"status": "ok", "event_id": event_id, "action": action, "action_count": len(actions)}


def remove_event_action(event_id: str, action_index: int) -> dict[str, Any]:
    """Remove one action from an event by its index."""
    proj = _load_proj()
    events = proj.get("events") or []
    event = next((e for e in events if isinstance(e, dict) and e.get("id") == event_id), None)
    if not event:
        return {"error": f"Event '{event_id}' not found."}

    actions = event.get("actions") or []
    if action_index < 0 or action_index >= len(actions):
        return {"error": f"Action index {action_index} out of range (event has {len(actions)} actions)."}

    removed = actions.pop(action_index)
    event["actions"] = actions
    _save_proj(proj)
    return {"status": "ok", "event_id": event_id, "removed": removed, "action_count": len(actions)}


def set_event_actions(event_id: str, actions_json: str) -> dict[str, Any]:
    """Replace every action on an event.

    actions_json is a JSON array of objects like
    [{"type":"set_flag","value":"door_open"},{"type":"play_cutscene","value":"intro"}].
    """
    proj = _load_proj()
    events = proj.get("events") or []
    event = next((e for e in events if isinstance(e, dict) and e.get("id") == event_id), None)
    if not event:
        return {"error": f"Event '{event_id}' not found."}

    try:
        raw = json.loads(actions_json)
    except Exception as e:
        return {"error": f"Invalid actions_json: {e}"}
    if not isinstance(raw, list):
        return {"error": "actions_json must be a JSON array of action objects."}

    out = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            return {"error": f"Action #{idx + 1} is not an object."}
        atype = str(item.get("type") or "").strip().lower()
        if atype not in ACTION_TYPES:
            return {"error": f"Action #{idx + 1}: unknown type '{atype}'. Valid: {', '.join(ACTION_TYPES)}"}
        out.append(normalize_action(item))

    event["actions"] = out
    _save_proj(proj)
    return {"status": "ok", "event_id": event_id, "actions": out, "action_count": len(out)}


def migrate_legacy_triggers() -> dict[str, Any]:
    """Convert old cutscene trigger fields into real events.

    Older projects expressed triggers as trigger_type / trigger_target on a
    cutscene. This rewrites them as events so there is only one mechanism
    left to reason about. The cutscenes themselves are left intact.
    """
    proj = _load_proj()
    legacy = migrate_cutscene_triggers(proj.get("cutscenes"))
    if not legacy:
        return {"status": "ok", "migrated": 0, "message": "No legacy cutscene triggers found."}

    events = proj.get("events")
    if not isinstance(events, list):
        events = []
        proj["events"] = events

    existing = {e.get("id") for e in events if isinstance(e, dict)}
    added = []
    for event in legacy:
        if event["id"] in existing:
            continue
        clean = dict(event)
        clean.pop("legacy", None)
        events.append(clean)
        added.append(clean["id"])

    _save_proj(proj)
    return {
        "status": "ok",
        "migrated": len(added),
        "event_ids": added,
        "message": f"Created {len(added)} event(s) from legacy cutscene triggers.",
    }

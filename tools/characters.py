"""
AdventureForge — Character MCP Tools

The generic, multi-character model. AdventureForge used to hard-code exactly
two actors (``player_sprite`` and ``partner_sprite`` plus one global
``partner_dialog_id``), which made every game a Sam & Max game.

A project now owns a ``characters`` map and names one of them as the player.
Characters have a role:

* ``player``    — the character the player controls
* ``companion`` — follows the player around
* ``npc``       — lives in a room, talked to through a hotspot

Every function here works on the same normalised shape the runtime uses, so
the editor and the engine can never disagree about what a character is.
"""
from typing import Any

from engine_characters import (
    build_character_registry,
    companion_character_ids,
    normalize_character,
    resolve_player_character_id,
)

from ._core import (
    _load_proj,
    _save_proj,
)


def _clean_id(raw: str, fallback: str = "character") -> str:
    return "".join(ch for ch in str(raw or "").lower() if ch.isalnum() or ch == "_") or fallback


def _ensure_character_map(proj: dict[str, Any]) -> dict[str, Any]:
    """Return the project's character map, creating it from legacy data if needed."""
    existing = proj.get("characters")
    if isinstance(existing, dict) and existing:
        return existing

    # Seed the map from the legacy sprite slots so nothing is lost.
    seeded: dict[str, Any] = {}
    player_sprite = str(proj.get("player_sprite") or "").strip()
    if player_sprite:
        seeded[_clean_id(f"player_{player_sprite}", "player")] = {
            "name": "",
            "sprite": player_sprite,
            "role": "player",
        }
    partner_sprite = str(proj.get("partner_sprite") or "").strip()
    if partner_sprite:
        seeded[_clean_id(f"companion_{partner_sprite}", "companion")] = {
            "name": "",
            "sprite": partner_sprite,
            "role": "companion",
            "dialog_id": str(proj.get("partner_dialog_id") or ""),
            "follow": True,
        }
    proj["characters"] = seeded
    return seeded


def list_characters() -> dict[str, Any]:
    """List every character in the project with its sprite, role, and follow settings."""
    proj = _load_proj()
    registry = build_character_registry(proj)
    player_id = resolve_player_character_id(proj)
    companions = companion_character_ids(registry)

    characters = []
    for cid, char in registry.items():
        characters.append({
            "id": cid,
            "name": char["name"],
            "sprite": char["sprite"],
            "role": char["role"],
            "color": char["color"],
            "scale": char["scale"],
            "dialog_id": char["dialog_id"],
            "follow": char["follow"],
            "follow_distance": char["follow_distance"],
            "follow_speed": char["follow_speed"],
            "is_player": cid == player_id,
            "is_companion": cid in companions,
        })

    return {
        "count": len(characters),
        "characters": characters,
        "player_character": player_id,
        "companions": companions,
    }


def get_character(character_id: str) -> dict[str, Any]:
    """Get one character's full definition."""
    proj = _load_proj()
    registry = build_character_registry(proj)
    char = registry.get(character_id)
    if not char:
        return {"error": f"Character '{character_id}' not found."}
    char = dict(char)
    char["is_player"] = character_id == resolve_player_character_id(proj)
    return {"character": char}


def create_or_update_character(
    character_id: str,
    name: str = "",
    sprite: str = "",
    role: str = "npc",
    color: str = "",
    scale: float = 0.0,
    dialog_id: str = "",
    follow: bool | None = None,
    follow_distance: float = 130.0,
    follow_speed: float = 245.0,
    set_as_player: bool = False,
) -> dict[str, Any]:
    """Create a character, or update an existing one.

    role is 'player', 'companion' or 'npc'. A companion follows the player
    around; set follow=False to keep it near the player but stationary.
    color accepts 'r,g,b' or '#rrggbb'. Leave scale at 0 to use the sprite's
    own scale.

    Leave follow unset to keep the current value — a new companion follows the
    player by default, anything else does not.
    """
    proj = _load_proj()
    clean = _clean_id(character_id)
    characters = _ensure_character_map(proj)
    sprites = proj.get("sprites") if isinstance(proj.get("sprites"), dict) else {}

    raw = dict(characters.get(clean) or {})
    if name:
        raw["name"] = name
    if sprite:
        raw["sprite"] = sprite
    if role:
        raw["role"] = role
    if color:
        raw["color"] = color
    if scale and scale > 0:
        raw["scale"] = scale
    if dialog_id:
        raw["dialog_id"] = dialog_id
    if follow is not None:
        raw["follow"] = bool(follow)
    elif "follow" not in raw:
        # New characters follow the player when they are a companion.
        raw["follow"] = role == "companion"
    if follow_distance:
        raw["follow_distance"] = follow_distance
    if follow_speed:
        raw["follow_speed"] = follow_speed

    char = normalize_character(clean, raw, sprites)
    characters[clean] = char

    # Keep the legacy top-level keys in sync so older builds still run.
    if char["role"] == "player" or set_as_player:
        proj["player_character"] = clean
        if char["sprite"]:
            proj["player_sprite"] = char["sprite"]
    if char["role"] == "companion":
        if char["sprite"]:
            proj["partner_sprite"] = char["sprite"]
        if char["dialog_id"]:
            proj["partner_dialog_id"] = char["dialog_id"]

    _save_proj(proj)
    return {"status": "ok", "character": char, "player_character": resolve_player_character_id(proj)}


def delete_character(character_id: str) -> dict[str, Any]:
    """Delete a character and detach it from any hotspot that referenced it."""
    proj = _load_proj()
    characters = proj.get("characters")
    if not isinstance(characters, dict) or character_id not in characters:
        return {"error": f"Character '{character_id}' not found."}

    del characters[character_id]

    if proj.get("player_character") == character_id:
        remaining = [cid for cid in characters if characters[cid].get("role") == "player"]
        proj["player_character"] = remaining[0] if remaining else ""

    detached = 0
    for room in proj.get("rooms", []):
        for hs in room.get("hotspots", []):
            if hs.get("character_id") == character_id:
                hs.pop("character_id", None)
                detached += 1

    _save_proj(proj)
    return {"status": "ok", "deleted": character_id, "detached_hotspots": detached}


def set_player_character(character_id: str) -> dict[str, Any]:
    """Choose which character the player controls."""
    proj = _load_proj()
    registry = build_character_registry(proj)
    if character_id not in registry:
        return {"error": f"Character '{character_id}' not found."}

    proj["player_character"] = character_id
    char = registry[character_id]
    if char.get("sprite"):
        proj["player_sprite"] = char["sprite"]

    _save_proj(proj)
    return {"status": "ok", "player_character": character_id, "name": char.get("name", character_id)}


def assign_character_to_hotspot(
    room_id: str,
    hotspot_id: str,
    character_id: str = "",
) -> dict[str, Any]:
    """Bind a character to an NPC hotspot so it shows the right sprite and dialogue.

    Pass an empty character_id to unbind.
    """
    proj = _load_proj()
    room = next((r for r in proj.get("rooms", []) if r.get("id") == room_id), None)
    if not room:
        return {"error": f"Room '{room_id}' not found."}
    hs = next((h for h in room.get("hotspots", []) if h.get("id") == hotspot_id), None)
    if not hs:
        return {"error": f"Hotspot '{hotspot_id}' not found in room '{room_id}'."}

    if not character_id:
        hs.pop("character_id", None)
        _save_proj(proj)
        return {"status": "ok", "room_id": room_id, "hotspot_id": hotspot_id, "character_id": ""}

    registry = build_character_registry(proj)
    char = registry.get(character_id)
    if not char:
        return {"error": f"Character '{character_id}' not found."}

    hs["character_id"] = character_id
    # Mirror onto the legacy fields so older builds still show the NPC.
    if char.get("sprite"):
        hs["sprite_id"] = char["sprite"]
    if char.get("dialog_id"):
        hs["dialog_id"] = char["dialog_id"]

    _save_proj(proj)
    return {"status": "ok", "room_id": room_id, "hotspot_id": hotspot_id, "character_id": character_id}

#!/usr/bin/env python3
"""
AdventureForge — Character Registry

The generic, multi-character model. AdventureForge used to hard-code exactly
two actors: ``player_sprite`` and ``partner_sprite``, plus a single global
``partner_dialog_id``. That made every game a Sam & Max game.

Now a project owns a ``characters`` map::

    "characters": {
      "detective": {
        "id": "detective",
        "name": "Detective Vex",
        "sprite": "vex",
        "color": [240, 200, 80],
        "scale": 3.0,
        "role": "player",
        "dialog_id": "",
        "follow": false,
        "follow_distance": 130,
        "follow_speed": 245
      }
    },
    "player_character": "detective"

``role`` is one of:

* ``player``    — the character the player controls (exactly one)
* ``companion`` — follows the player around
* ``npc``       — stands in a room, talked to through a hotspot

Every function here is pure: no Pygame, no file access. The engine turns the
registry into live animation state; the MCP tools use the same helpers so
the editor and the runtime can never disagree about what a character is.
"""
from __future__ import annotations

from typing import Any

VALID_ROLES = ("player", "companion", "npc")

DEFAULT_COLORS = {
    "player": (240, 200, 80),
    "companion": (192, 132, 252),
    "npc": (199, 125, 255),
}


def _as_color(value: Any, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    """Coerce a colour from JSON into an ``(r, g, b)`` tuple.

    Accepts a list/tuple of three numbers, a ``#rrggbb`` hex string, or a
    comma-separated ``"r,g,b"`` string (which is what the MCP tool takes).
    """
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return (
                max(0, min(255, int(value[0]))),
                max(0, min(255, int(value[1]))),
                max(0, min(255, int(value[2]))),
            )
        except (TypeError, ValueError):
            return fallback
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if text.startswith("#"):
            text = text[1:]
        if "," in text:
            parts = [p.strip() for p in text.split(",")]
            if len(parts) >= 3:
                try:
                    return (
                        max(0, min(255, int(parts[0]))),
                        max(0, min(255, int(parts[1]))),
                        max(0, min(255, int(parts[2]))),
                    )
                except ValueError:
                    return fallback
            return fallback
        if len(text) == 6:
            try:
                return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
            except ValueError:
                return fallback
    return fallback


def _as_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _as_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    if value is None:
        return fallback
    return bool(value)


def normalize_character(
    character_id: str,
    raw: dict[str, Any] | None = None,
    sprites: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalise one character entry into the canonical shape.

    ``sprites`` is the project's sprite map, used to pull a sensible default
    display name out of the sprite metadata when the character has none.
    """
    raw = raw if isinstance(raw, dict) else {}
    sprites = sprites if isinstance(sprites, dict) else {}

    cid = str(character_id or raw.get("id") or "").strip()
    role = str(raw.get("role") or "npc").strip().lower()
    if role not in VALID_ROLES:
        role = "npc"

    sprite_id = str(raw.get("sprite") or raw.get("sprite_id") or "").strip()

    name = str(raw.get("name") or "").strip()
    if not name and sprite_id:
        sprite_meta = sprites.get(sprite_id)
        if isinstance(sprite_meta, dict):
            name = str(sprite_meta.get("name") or "").split("(")[0].strip()
    if not name:
        name = cid.replace("_", " ").title() or "Character"

    scale = _as_float(raw.get("scale"), 0.0)
    if scale <= 0:
        scale = 0.0  # 0 means "use the sprite's own scale"

    follow = _as_bool(raw.get("follow"), role == "companion")

    return {
        "id": cid,
        "name": name,
        "sprite": sprite_id,
        "color": list(_as_color(raw.get("color"), DEFAULT_COLORS.get(role, (200, 200, 200)))),
        "scale": scale,
        "role": role,
        "dialog_id": str(raw.get("dialog_id") or "").strip(),
        "follow": follow,
        "follow_distance": max(20.0, _as_float(raw.get("follow_distance"), 130.0)),
        "follow_speed": max(40.0, _as_float(raw.get("follow_speed"), 245.0)),
        "visible": _as_bool(raw.get("visible"), True),
    }


def _legacy_character_id(prefix: str, sprite_id: str) -> str:
    """Build a stable character id from a legacy sprite reference."""
    clean = "".join(ch for ch in sprite_id.lower() if ch.isalnum() or ch == "_")
    return f"{prefix}_{clean}" if clean else prefix


def build_character_registry(project: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Build the normalised character registry for a project.

    Falls back to the legacy ``player_sprite`` / ``partner_sprite`` keys when
    a project has no ``characters`` map yet, so every existing game keeps
    working untouched.
    """
    project = project if isinstance(project, dict) else {}
    sprites = project.get("sprites") if isinstance(project.get("sprites"), dict) else {}

    raw_characters = project.get("characters")
    registry: dict[str, dict[str, Any]] = {}

    if isinstance(raw_characters, dict) and raw_characters:
        for cid, raw in raw_characters.items():
            if not isinstance(raw, dict):
                continue
            char = normalize_character(str(cid), raw, sprites)
            if not char["id"]:
                continue
            registry[char["id"]] = char
    elif isinstance(raw_characters, list):
        # Tolerate the list form some hand-written manifests use.
        for raw in raw_characters:
            if not isinstance(raw, dict):
                continue
            char = normalize_character(str(raw.get("id") or ""), raw, sprites)
            if char["id"]:
                registry[char["id"]] = char

    if not registry:
        # Legacy fallback: derive characters from the old sprite slots.
        player_sprite = str(project.get("player_sprite") or "").strip()
        if player_sprite:
            cid = _legacy_character_id("player", player_sprite)
            registry[cid] = normalize_character(
                cid,
                {
                    "name": "",
                    "sprite": player_sprite,
                    "role": "player",
                    "color": list(DEFAULT_COLORS["player"]),
                },
                sprites,
            )

        partner_sprite = str(project.get("partner_sprite") or "").strip()
        if partner_sprite:
            cid = _legacy_character_id("companion", partner_sprite)
            registry[cid] = normalize_character(
                cid,
                {
                    "name": "",
                    "sprite": partner_sprite,
                    "role": "companion",
                    "dialog_id": str(project.get("partner_dialog_id") or ""),
                    "follow": True,
                    "color": list(DEFAULT_COLORS["companion"]),
                },
                sprites,
            )

    return registry


def resolve_player_character_id(project: dict[str, Any] | None) -> str:
    """Determine which character the player controls.

    Order: explicit ``player_character`` -> the character whose role is
    ``player`` -> the first companion -> the first character -> "".
    """
    project = project if isinstance(project, dict) else {}
    registry = build_character_registry(project)

    explicit = str(project.get("player_character") or "").strip()
    if explicit and explicit in registry:
        return explicit

    for cid, char in registry.items():
        if char["role"] == "player":
            return cid

    for cid, char in registry.items():
        if char["role"] == "companion":
            return cid

    return next(iter(registry), "")


def companion_character_ids(registry: dict[str, dict[str, Any]]) -> list[str]:
    """Ids of characters that follow the player, in registry order."""
    return [
        cid
        for cid, char in registry.items()
        if char["role"] == "companion" and char.get("follow", True)
    ]


def npc_character_ids(registry: dict[str, dict[str, Any]]) -> list[str]:
    """Ids of characters that live in rooms as NPCs."""
    return [cid for cid, char in registry.items() if char["role"] == "npc"]


def character_color(char: dict[str, Any] | None) -> tuple[int, int, int]:
    """RGB tuple for a character's fallback circle colour."""
    if not isinstance(char, dict):
        return DEFAULT_COLORS["npc"]
    role = char.get("role", "npc")
    return _as_color(char.get("color"), DEFAULT_COLORS.get(role, (200, 200, 200)))

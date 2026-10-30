"""
AdventureForge — Project & Engine MCP Tools
"""
from typing import Any
from config import config
from engine_characters import build_character_registry
from . import _core
from ._core import (
    _load_proj,
    _save_proj,
)
import sys
import os
import subprocess


def get_project_summary() -> dict[str, Any]:
    """Get a complete summary of the AdventureForge project: title, rooms, hotspots, items, puzzles, characters, sprites, dialogs, cutscenes and events."""
    proj = _load_proj()
    rooms_summary = []
    for r in proj.get("rooms", []):
        rooms_summary.append({
            "id": r.get("id"),
            "name": r.get("name"),
            "map_x": r.get("map_x", 100),
            "map_y": r.get("map_y", 100),
            "background": r.get("background"),
            "player_start": r.get("player_start"),
            "collider_count": len(r.get("colliders") or []),
            "hotspots": [
                {
                    "id": h.get("id"),
                    "name": h.get("name"),
                    "type": h.get("type"),
                    "rect": h.get("rect"),
                    "item_id": h.get("item_id", ""),
                    "target_room": h.get("target_room", ""),
                    "locked": h.get("locked", False),
                    "required_flag": h.get("required_flag", ""),
                    "dialog_id": h.get("dialog_id", ""),
                    "character_id": h.get("character_id", ""),
                    "cutscene_id": h.get("cutscene_id", ""),
                    "look_text": h.get("look_text", "")
                }
                for h in r.get("hotspots", [])
            ]
        })
    return {
        "title": proj.get("title"),
        "start_room": proj.get("start_room"),
        "player_character": proj.get("player_character", ""),
        "player_sprite": proj.get("player_sprite"),
        "partner_sprite": proj.get("partner_sprite"),
        "partner_dialog_id": proj.get("partner_dialog_id", ""),
        "characters": build_character_registry(proj),
        "rooms": rooms_summary,
        "items": proj.get("items", []),
        "puzzles": proj.get("puzzles", []),
        "sprites": list(proj.get("sprites", {}).keys()),
        "dialogs": [{"id": d.get("id"), "name": d.get("name"), "npc_name": d.get("npc_name"), "node_count": len(d.get("nodes", []))} for d in proj.get("dialogs", [])],
        "cutscenes": [{"id": c.get("id"), "name": c.get("name"), "trigger_type": c.get("trigger_type"), "trigger_target": c.get("trigger_target"), "step_count": len(c.get("steps", []))} for c in proj.get("cutscenes", [])],
        "events": [
            {
                "id": e.get("id"),
                "name": e.get("name", ""),
                "trigger": (e.get("trigger") or {}).get("type", ""),
                "target": (e.get("trigger") or {}).get("target", ""),
                "action_count": len(e.get("actions") or []),
            }
            for e in (proj.get("events") or [])
            if isinstance(e, dict)
        ]
    }


def get_full_project() -> dict[str, Any]:
    """Retrieve the entire raw AdventureForge project JSON structure."""
    return _load_proj()


def set_project_title(title: str) -> dict[str, Any]:
    """Set the game's display title."""
    proj = _load_proj()
    proj["title"] = title
    _save_proj(proj)
    return {"status": "ok", "title": title}


def set_character_roles(player_sprite: str = "", partner_sprite: str = "") -> dict[str, Any]:
    """Assign which loaded sprite is the Player character and which is the Partner follower.

    Legacy shortcut for the character system: it updates the matching entries
    in ``project.characters`` as well as the old top-level sprite keys. Use
    ``create_or_update_character`` for anything beyond a player and a partner.
    """
    proj = _load_proj()
    if player_sprite:
        proj["player_sprite"] = player_sprite
    if partner_sprite == "__none__":
        proj["partner_sprite"] = ""
    elif partner_sprite:
        proj["partner_sprite"] = partner_sprite

    # Mirror the change into the character registry so both models agree.
    characters = proj.get("characters")
    if not isinstance(characters, dict):
        characters = {}

    if player_sprite:
        player_id = proj.get("player_character") or ""
        if not player_id or player_id not in characters:
            player_id = next(
                (cid for cid, c in characters.items() if c.get("role") == "player"),
                "",
            )
        if not player_id:
            player_id = f"player_{player_sprite}"
            characters[player_id] = {"name": "", "sprite": player_sprite, "role": "player"}
        else:
            characters[player_id]["sprite"] = player_sprite
        characters[player_id]["role"] = "player"
        proj["player_character"] = player_id

    if partner_sprite:
        partner_id = proj.get("partner_character") or ""
        if not partner_id or partner_id not in characters:
            partner_id = next(
                (cid for cid, c in characters.items() if c.get("role") == "companion"),
                "",
            )
        if not partner_id:
            partner_id = f"companion_{partner_sprite}"
            characters[partner_id] = {
                "name": "", "sprite": partner_sprite, "role": "companion", "follow": True,
            }
        else:
            characters[partner_id]["sprite"] = partner_sprite
        characters[partner_id]["role"] = "companion"
        characters[partner_id]["follow"] = True
        proj["partner_character"] = partner_id
    elif partner_sprite == "__none__":
        for cid, c in characters.items():
            if c.get("role") == "companion":
                c["follow"] = False

    if characters:
        proj["characters"] = characters

    _save_proj(proj)
    return {
        "status": "ok",
        "player_sprite": proj.get("player_sprite"),
        "partner_sprite": proj.get("partner_sprite"),
        "player_character": proj.get("player_character", ""),
    }


def launch_pygame_game(room_id: str = "", cutscene_id: str = "", dialog_id: str = "") -> dict[str, Any]:
    """Launch the Pygame engine runtime to playtest the game (optionally starting at a specific room, cutscene, or dialog)."""
    if _core.PYGAME_PROC and _core.PYGAME_PROC.poll() is None:
        _core.PYGAME_PROC.terminate()
        try:
            _core.PYGAME_PROC.wait(timeout=2)
        except Exception:
            _core.PYGAME_PROC.kill()

    cmd = [sys.executable, str(config.BASE_DIR / "engine_pygame.py")]
    if room_id:
        cmd.extend(["--room", str(room_id)])
    if cutscene_id:
        cmd.extend(["--cutscene", str(cutscene_id)])
    if dialog_id:
        cmd.extend(["--dialog", str(dialog_id)])

    env = os.environ.copy()
    if "DISPLAY" not in env:
        env["DISPLAY"] = config.DISPLAY
    if "XAUTHORITY" not in env and config.XAUTHORITY:
        env["XAUTHORITY"] = config.XAUTHORITY

    _core.PYGAME_PROC = subprocess.Popen(cmd, cwd=str(config.BASE_DIR), env=env)
    return {"status": "launched", "pid": _core.PYGAME_PROC.pid, "command": cmd}


def stop_pygame_game() -> dict[str, Any]:
    """Terminate any currently running Pygame test play instance."""
    if _core.PYGAME_PROC and _core.PYGAME_PROC.poll() is None:
        pid = _core.PYGAME_PROC.pid
        _core.PYGAME_PROC.terminate()
        try:
            _core.PYGAME_PROC.wait(timeout=2)
        except Exception:
            _core.PYGAME_PROC.kill()
        _core.PYGAME_PROC = None
        return {"status": "stopped", "pid": pid}
    return {"status": "not_running"}
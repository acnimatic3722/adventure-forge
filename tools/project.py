"""
AdventureForge — Project & Engine MCP Tools
"""
from typing import Any
from config import config
from agent_tools import (
    _load_proj,
    _save_proj,
    PYGAME_PROC,
)
import sys
import os
import subprocess


def get_project_summary() -> dict[str, Any]:
    """Get a complete summary of the AdventureForge project: title, rooms, hotspots, items, puzzles, sprites, dialogs, and cutscenes."""
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
                    "cutscene_id": h.get("cutscene_id", ""),
                    "look_text": h.get("look_text", "")
                }
                for h in r.get("hotspots", [])
            ]
        })
    return {
        "title": proj.get("title"),
        "start_room": proj.get("start_room"),
        "player_sprite": proj.get("player_sprite"),
        "partner_sprite": proj.get("partner_sprite"),
        "partner_dialog_id": proj.get("partner_dialog_id", ""),
        "rooms": rooms_summary,
        "items": proj.get("items", []),
        "puzzles": proj.get("puzzles", []),
        "sprites": list(proj.get("sprites", {}).keys()),
        "dialogs": [{"id": d.get("id"), "name": d.get("name"), "npc_name": d.get("npc_name"), "node_count": len(d.get("nodes", []))} for d in proj.get("dialogs", [])],
        "cutscenes": [{"id": c.get("id"), "name": c.get("name"), "trigger_type": c.get("trigger_type"), "trigger_target": c.get("trigger_target"), "step_count": len(c.get("steps", []))} for c in proj.get("cutscenes", [])]
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
    """Assign which loaded sprite is the Player character and which is the Partner follower."""
    proj = _load_proj()
    if player_sprite:
        proj["player_sprite"] = player_sprite
    if partner_sprite == "__none__":
        proj["partner_sprite"] = ""
    elif partner_sprite:
        proj["partner_sprite"] = partner_sprite
    _save_proj(proj)
    return {
        "status": "ok",
        "player_sprite": proj.get("player_sprite"),
        "partner_sprite": proj.get("partner_sprite")
    }


def launch_pygame_game(room_id: str = "", cutscene_id: str = "", dialog_id: str = "") -> dict[str, Any]:
    """Launch the Pygame engine runtime to playtest the game (optionally starting at a specific room, cutscene, or dialog)."""
    global PYGAME_PROC
    if PYGAME_PROC and PYGAME_PROC.poll() is None:
        PYGAME_PROC.terminate()
        try:
            PYGAME_PROC.wait(timeout=2)
        except Exception:
            PYGAME_PROC.kill()

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

    PYGAME_PROC = subprocess.Popen(cmd, cwd=str(config.BASE_DIR), env=env)
    return {"status": "launched", "pid": PYGAME_PROC.pid, "command": cmd}


def stop_pygame_game() -> dict[str, Any]:
    """Terminate any currently running Pygame test play instance."""
    global PYGAME_PROC
    if PYGAME_PROC and PYGAME_PROC.poll() is None:
        pid = PYGAME_PROC.pid
        PYGAME_PROC.terminate()
        try:
            PYGAME_PROC.wait(timeout=2)
        except Exception:
            PYGAME_PROC.kill()
        PYGAME_PROC = None
        return {"status": "stopped", "pid": pid}
    return {"status": "not_running"}
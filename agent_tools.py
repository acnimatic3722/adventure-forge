#!/usr/bin/env python3
"""
AdventureForge — Comprehensive MCP Toolset & LLM/VLM Agent Engine
Exposes all game editor, world map, room hotspot, inventory, puzzle, dialog,
cutscene, sprite studio, asset management, and Pygame runtime functions
over the Model Context Protocol (MCP) and Gemini Agent loop.
"""

import io
import json
import inspect
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw
from google import genai
from google.genai import types

# Import config first
from config import config

sys.path.insert(0, str(config.SPRITE_SLICER_PATH))
from slice_sprites import load_env

BASE_DIR = config.BASE_DIR
DATA_DIR = config.DATA_DIR
ASSETS_DIR = config.ASSETS_DIR
PROJECT_FILE = config.PROJECT_FILE
SPRITES_DIR = config.SPRITES_DIR

PYGAME_PROC: subprocess.Popen | None = None


# ============================================================================
# PROJECT & ASSET HELPERS
# ============================================================================

def _load_proj() -> dict[str, Any]:
    if not PROJECT_FILE.exists():
        return {
            "title": "New Adventure",
            "start_room": "",
            "rooms": [],
            "items": [],
            "puzzles": [],
            "dialogs": [],
            "cutscenes": [],
            "sprites": {}
        }
    data = json.loads(PROJECT_FILE.read_text())
    for k in ("rooms", "items", "puzzles", "dialogs", "cutscenes"):
        if k not in data or not isinstance(data[k], list):
            data[k] = []
    if "sprites" not in data or not isinstance(data["sprites"], dict):
        data["sprites"] = {}
    return data


def _save_proj(data: dict[str, Any]) -> None:
    PROJECT_FILE.write_text(json.dumps(data, indent=2))


def _resolve_asset(web_url: str) -> Path:
    clean = web_url.split("?")[0].lstrip("/")
    if not clean.startswith("assets/"):
        clean = "assets/" + clean
    target = (DATA_DIR / clean).resolve()
    if not str(target).startswith(str(ASSETS_DIR.resolve())):
        raise ValueError("Forbidden asset path")
    return target


def _normalize_vlm_meta(meta: dict[str, Any], fallback_name: str) -> dict[str, Any]:
    vlm = meta.get("vlm")
    if isinstance(vlm, list):
        merged_anims = []
        char_names = []
        for item in vlm:
            if isinstance(item, dict):
                cname = item.get("character_name", "")
                if cname:
                    char_names.append(str(cname))
                for anim in item.get("animations", []):
                    if isinstance(anim, dict):
                        merged_anims.append(anim)
        meta["vlm"] = {
            "character_name": " & ".join(char_names[:3]) if char_names else fallback_name,
            "animations": merged_anims
        }
    elif not isinstance(vlm, dict):
        meta["vlm"] = {"character_name": fallback_name, "animations": []}
    return meta


# ============================================================================
# 1. PROJECT & ENGINE MCP TOOLS
# ============================================================================

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

    cmd = [sys.executable, str(BASE_DIR / "engine_pygame.py")]
    if room_id:
        cmd.extend(["--room", str(room_id)])
    if cutscene_id:
        cmd.extend(["--cutscene", str(cutscene_id)])
    if dialog_id:
        cmd.extend(["--dialog", str(dialog_id)])

    env = os.environ.copy()
    if "DISPLAY" not in env:
        env["DISPLAY"] = ":1.0"
    if "XAUTHORITY" not in env and os.path.exists(os.path.expanduser("~/.Xauthority")):
        env["XAUTHORITY"] = os.path.expanduser("~/.Xauthority")

    PYGAME_PROC = subprocess.Popen(cmd, cwd=str(BASE_DIR), env=env)
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


# ============================================================================
# 2. ROOMS & WORLD MAP MCP TOOLS
# ============================================================================

def list_rooms() -> dict[str, Any]:
    """List all room screens with their IDs, names, map coordinates, and door counts."""
    proj = _load_proj()
    rooms = []
    for r in proj.get("rooms", []):
        door_count = len([h for h in r.get("hotspots", []) if h.get("type") == "exit"])
        rooms.append({
            "id": r.get("id"),
            "name": r.get("name"),
            "map_x": r.get("map_x", 100),
            "map_y": r.get("map_y", 100),
            "background": r.get("background", ""),
            "is_start": (r.get("id") == proj.get("start_room")),
            "doors": door_count,
            "hotspot_count": len(r.get("hotspots", []))
        })
    return {"count": len(rooms), "rooms": rooms}


def get_room(room_id: str) -> dict[str, Any]:
    """Get full details of a specific room screen including walkable polygon, player spawn, and all hotspots."""
    proj = _load_proj()
    room = next((r for r in proj.get("rooms", []) if r.get("id") == room_id), None)
    if not room:
        return {"error": f"Room '{room_id}' not found."}
    return {"room": room}


def create_or_update_room(
    room_id: str,
    name: str = "",
    background: str = "",
    player_start_x: int = 400,
    player_start_y: int = 560,
    set_as_start: bool = False
) -> dict[str, Any]:
    """Create a new room screen or update an existing room's name, background URL, or player spawn coordinates."""
    proj = _load_proj()
    clean_id = "".join(c for c in room_id if c.isalnum() or c == "_").lower() or "room_new"
    room = next((r for r in proj["rooms"] if r["id"] == clean_id), None)
    if room is None:
        room = {
            "id": clean_id,
            "name": name or clean_id,
            "map_x": 180 + (len(proj["rooms"]) * 180) % 600,
            "map_y": 140 + (len(proj["rooms"]) * 90) % 400,
            "background": background,
            "player_start": {"x": int(player_start_x), "y": int(player_start_y)},
            "walkable_polygon": [
                {"x": 60, "y": 470},
                {"x": 1220, "y": 470},
                {"x": 1240, "y": 700},
                {"x": 40, "y": 700}
            ],
            "hotspots": []
        }
        proj["rooms"].append(room)
        action = "created"
    else:
        if name:
            room["name"] = name
        if background:
            room["background"] = background
        if player_start_x and player_start_y:
            room["player_start"] = {"x": int(player_start_x), "y": int(player_start_y)}
        action = "updated"

    if set_as_start or not proj.get("start_room"):
        proj["start_room"] = clean_id

    _save_proj(proj)
    return {"status": "ok", "action": action, "room": room}


def delete_room(room_id: str) -> dict[str, Any]:
    """Delete a room screen by ID."""
    proj = _load_proj()
    before = len(proj["rooms"])
    proj["rooms"] = [r for r in proj["rooms"] if r.get("id") != room_id]
    if proj.get("start_room") == room_id:
        proj["start_room"] = proj["rooms"][0]["id"] if proj["rooms"] else ""
    _save_proj(proj)
    return {"status": "ok", "deleted": before - len(proj["rooms"])}


def update_room_map_position(room_id: str, map_x: int, map_y: int) -> dict[str, Any]:
    """Set the (map_x, map_y) coordinate of a room node on the World Map canvas."""
    proj = _load_proj()
    room = next((r for r in proj["rooms"] if r["id"] == room_id), None)
    if not room:
        return {"error": f"Room '{room_id}' not found."}
    room["map_x"] = int(map_x)
    room["map_y"] = int(map_y)
    _save_proj(proj)
    return {"status": "ok", "room_id": room_id, "map_x": room["map_x"], "map_y": room["map_y"]}


def set_room_walkable_polygon(room_id: str, points_json: str) -> dict[str, Any]:
    """Set the walkable floor polygon for a room. points_json should be a JSON array of coordinates, e.g. '[{"x": 60, "y": 450}, {"x": 1200, "y": 450}, ...]'."""
    proj = _load_proj()
    room = next((r for r in proj["rooms"] if r["id"] == room_id), None)
    if not room:
        return {"error": f"Room '{room_id}' not found."}
    try:
        pts = json.loads(points_json)
        if not isinstance(pts, list):
            return {"error": "points_json must be a JSON array of points."}
        room["walkable_polygon"] = [{"x": int(p.get("x", 0)), "y": int(p.get("y", 0))} for p in pts]
    except Exception as e:
        return {"error": f"Invalid polygon JSON: {e}"}
    _save_proj(proj)
    return {"status": "ok", "room_id": room_id, "point_count": len(room["walkable_polygon"])}


def set_start_room(room_id: str) -> dict[str, Any]:
    """Designate which room the player spawns into when a new game starts."""
    proj = _load_proj()
    room = next((r for r in proj["rooms"] if r["id"] == room_id), None)
    if not room:
        return {"error": f"Room '{room_id}' not found."}
    proj["start_room"] = room_id
    _save_proj(proj)
    return {"status": "ok", "start_room": room_id}


# ============================================================================
# 3. ROOM HOTSPOTS, PROPS, NPCS & DOORS MCP TOOLS
# ============================================================================

def list_hotspots(room_id: str) -> dict[str, Any]:
    """List all hotspots (props, pickups, NPCs, doors) in a room."""
    proj = _load_proj()
    room = next((r for r in proj["rooms"] if r["id"] == room_id), None)
    if not room:
        return {"error": f"Room '{room_id}' not found."}
    return {"room_id": room_id, "count": len(room.get("hotspots", [])), "hotspots": room.get("hotspots", [])}


def get_hotspot(room_id: str, hotspot_id: str) -> dict[str, Any]:
    """Get full properties of a specific hotspot in a room."""
    proj = _load_proj()
    room = next((r for r in proj["rooms"] if r["id"] == room_id), None)
    if not room:
        return {"error": f"Room '{room_id}' not found."}
    hs = next((h for h in room.get("hotspots", []) if h.get("id") == hotspot_id), None)
    if not hs:
        return {"error": f"Hotspot '{hotspot_id}' not found in room '{room_id}'."}
    return {"room_id": room_id, "hotspot": hs}


def create_or_update_hotspot(
    room_id: str,
    hotspot_id: str,
    name: str = "",
    hs_type: str = "prop",
    x: int = 400,
    y: int = 350,
    w: int = 100,
    h: int = 100,
    look_text: str = "",
    use_text: str = "",
    talk_text: str = "",
    icon: str = "",
    item_id: str = "",
    pickup_text: str = "",
    target_room: str = "",
    locked: bool = False,
    required_flag: str = "",
    locked_text: str = "",
    sprite_id: str = "",
    npc_anim: str = "idle_down",
    dialog_id: str = "",
    cutscene_id: str = ""
) -> dict[str, Any]:
    """Place a new hotspot or update an existing hotspot in a room. hs_type must be 'prop', 'pickup', 'npc', or 'exit' (door)."""
    proj = _load_proj()
    room = next((r for r in proj["rooms"] if r["id"] == room_id), None)
    if not room:
        return {"error": f"Room '{room_id}' not found."}

    if "hotspots" not in room or not isinstance(room["hotspots"], list):
        room["hotspots"] = []

    try:
        x, y, w, h = int(x), int(y), int(w), int(h)
    except (ValueError, TypeError):
        x, y, w, h = 400, 350, 100, 100

    clean_id = "".join(c for c in hotspot_id if c.isalnum() or c == "_").lower() or "hs_new"
    hs = next((item for item in room["hotspots"] if item["id"] == clean_id), None)
    rect = {"x": x, "y": y, "w": max(16, w), "h": max(16, h)}
    walk_to = {"x": x + w // 2, "y": min(690, y + h + 25)}

    if hs is None:
        hs = {
            "id": clean_id,
            "name": name or clean_id,
            "type": hs_type,
            "rect": rect,
            "walk_to": walk_to,
            "look_text": look_text or f"It's {name or clean_id}.",
            "use_text": use_text,
            "talk_text": talk_text,
            "icon": icon,
            "item_id": item_id,
            "pickup_text": pickup_text,
            "sprite_id": sprite_id,
            "npc_anim": npc_anim,
            "target_room": target_room,
            "locked": bool(locked),
            "required_flag": required_flag,
            "locked_text": locked_text,
            "dialog_id": dialog_id,
            "cutscene_id": cutscene_id
        }
        room["hotspots"].append(hs)
        action = "created"
    else:
        if name:
            hs["name"] = name
        if hs_type:
            hs["type"] = hs_type
        hs["rect"] = rect
        hs["walk_to"] = walk_to
        if look_text:
            hs["look_text"] = look_text
        if use_text:
            hs["use_text"] = use_text
        if talk_text:
            hs["talk_text"] = talk_text
        if icon:
            hs["icon"] = icon
        if item_id:
            hs["item_id"] = item_id
        if pickup_text:
            hs["pickup_text"] = pickup_text
        if target_room:
            hs["target_room"] = target_room
        hs["locked"] = bool(locked)
        if required_flag:
            hs["required_flag"] = required_flag
        if locked_text:
            hs["locked_text"] = locked_text
        if sprite_id:
            hs["sprite_id"] = sprite_id
        if npc_anim:
            hs["npc_anim"] = npc_anim
        if dialog_id:
            hs["dialog_id"] = dialog_id
        if cutscene_id:
            hs["cutscene_id"] = cutscene_id
        action = "updated"

    _save_proj(proj)
    return {"status": "ok", "action": action, "room_id": room_id, "hotspot": hs}


def delete_hotspot(room_id: str, hotspot_id: str) -> dict[str, Any]:
    """Delete a hotspot from a room."""
    proj = _load_proj()
    room = next((r for r in proj["rooms"] if r["id"] == room_id), None)
    if not room:
        return {"error": f"Room '{room_id}' not found."}
    before = len(room.get("hotspots", []))
    room["hotspots"] = [h for h in room.get("hotspots", []) if h.get("id") != hotspot_id]
    _save_proj(proj)
    return {"status": "ok", "deleted": before - len(room["hotspots"])}


def link_door(
    source_room_id: str,
    hotspot_id: str,
    target_room_id: str,
    door_name: str = "",
    locked: bool = False,
    required_flag: str = "",
    create_return_door: bool = False
) -> dict[str, Any]:
    """Connect an exit door in source_room_id to lead to target_room_id, with optional lock flag and optional automatic return door creation."""
    proj = _load_proj()
    src_room = next((r for r in proj["rooms"] if r["id"] == source_room_id), None)
    if not src_room:
        return {"error": f"Source room '{source_room_id}' not found."}
    dest_room = next((r for r in proj["rooms"] if r["id"] == target_room_id), None)
    if not dest_room:
        return {"error": f"Target room '{target_room_id}' not found."}

    hs = next((h for h in src_room.get("hotspots", []) if h.get("id") == hotspot_id), None)
    if not hs:
        hs = {
            "id": hotspot_id,
            "name": door_name or f"Door to {dest_room.get('name', target_room_id)}",
            "type": "exit",
            "rect": {"x": 100, "y": 240, "w": 120, "h": 260},
            "walk_to": {"x": 160, "y": 525},
            "target_room": target_room_id,
            "locked": bool(locked),
            "required_flag": required_flag,
            "locked_text": "It's locked.",
            "look_text": f"A doorway leading to {dest_room.get('name', target_room_id)}."
        }
        src_room.setdefault("hotspots", []).append(hs)
    else:
        hs["type"] = "exit"
        hs["target_room"] = target_room_id
        if door_name:
            hs["name"] = door_name
        hs["locked"] = bool(locked)
        if required_flag:
            hs["required_flag"] = required_flag

    return_hs = None
    if create_return_door:
        ret_id = f"return_to_{source_room_id}"
        existing_ret = next((h for h in dest_room.get("hotspots", []) if h.get("target_room") == source_room_id), None)
        if not existing_ret:
            return_hs = {
                "id": ret_id,
                "name": f"Door to {src_room.get('name', source_room_id)}",
                "type": "exit",
                "rect": {"x": 80, "y": 240, "w": 120, "h": 260},
                "walk_to": {"x": 140, "y": 525},
                "target_room": source_room_id,
                "locked": False,
                "look_text": f"Leads back to {src_room.get('name', source_room_id)}."
            }
            dest_room.setdefault("hotspots", []).append(return_hs)
        else:
            return_hs = existing_ret

    _save_proj(proj)
    return {
        "status": "ok",
        "door": hs,
        "return_door": return_hs
    }


def set_hotspot_lock(
    room_id: str,
    hotspot_id: str,
    locked: bool,
    required_flag: str = "",
    locked_text: str = ""
) -> dict[str, Any]:
    """Lock or unlock a door or prop hotspot, and optionally set the required flag or dialogue response."""
    proj = _load_proj()
    room = next((r for r in proj["rooms"] if r["id"] == room_id), None)
    if not room:
        return {"error": f"Room '{room_id}' not found."}
    hs = next((h for h in room.get("hotspots", []) if h.get("id") == hotspot_id), None)
    if not hs:
        return {"error": f"Hotspot '{hotspot_id}' not found in room '{room_id}'."}
    hs["locked"] = bool(locked)
    if required_flag:
        hs["required_flag"] = required_flag
    if locked_text:
        hs["locked_text"] = locked_text
    _save_proj(proj)
    return {"status": "ok", "hotspot": hs}


# ============================================================================
# 4. ITEMS & INVENTORY MCP TOOLS
# ============================================================================

def list_items() -> dict[str, Any]:
    """List all inventory items in the adventure game."""
    proj = _load_proj()
    return {"count": len(proj.get("items", [])), "items": proj.get("items", [])}


def get_item(item_id: str) -> dict[str, Any]:
    """Get full details of a specific inventory item by ID."""
    proj = _load_proj()
    item = next((i for i in proj.get("items", []) if i.get("id") == item_id), None)
    if not item:
        return {"error": f"Item '{item_id}' not found."}
    return {"item": item}


def create_or_update_item(
    item_id: str,
    name: str = "",
    description: str = "",
    icon: str = "",
    place_in_room: str = "",
    x: int = 520,
    y: int = 580,
    w: int = 56,
    h: int = 56
) -> dict[str, Any]:
    """Create or update an inventory item. If place_in_room is provided (e.g. 'reception'), also places a pickup hotspot for it on the floor."""
    proj = _load_proj()
    clean_id = "".join(c for c in item_id if c.isalnum() or c == "_").lower() or "item_new"
    item = next((i for i in proj["items"] if i["id"] == clean_id), None)
    if item is None:
        item = {
            "id": clean_id,
            "name": name or clean_id,
            "icon": icon,
            "description": description or f"It's {name or clean_id}."
        }
        proj["items"].append(item)
    else:
        if name:
            item["name"] = name
        if description:
            item["description"] = description
        if icon:
            item["icon"] = icon

    try:
        x, y, w, h = int(x), int(y), int(w), int(h)
    except (ValueError, TypeError):
        x, y, w, h = 520, 580, 56, 56

    placed_hs = None
    if place_in_room:
        room = next((r for r in proj["rooms"] if r["id"] == place_in_room), None)
        if room:
            hs_id = f"pickup_{clean_id}"
            existing_hs = next((h for h in room.get("hotspots", []) if h.get("item_id") == clean_id or h.get("id") == hs_id), None)
            if existing_hs is None:
                placed_hs = {
                    "id": hs_id,
                    "name": item["name"],
                    "type": "pickup",
                    "item_id": clean_id,
                    "icon": item.get("icon", ""),
                    "rect": {"x": x, "y": y, "w": w, "h": h},
                    "walk_to": {"x": x + w // 2, "y": min(685, y + h + 20)},
                    "look_text": item["description"],
                    "pickup_text": f"Picked up {item['name']}!"
                }
                room.setdefault("hotspots", []).append(placed_hs)
            else:
                existing_hs["item_id"] = clean_id
                existing_hs["name"] = item["name"]
                if item.get("icon"):
                    existing_hs["icon"] = item["icon"]
                placed_hs = existing_hs

    _save_proj(proj)
    return {"status": "ok", "item": item, "placed_hotspot": placed_hs}


def delete_item(item_id: str) -> dict[str, Any]:
    """Delete an inventory item by ID."""
    proj = _load_proj()
    before = len(proj["items"])
    proj["items"] = [i for i in proj["items"] if i.get("id") != item_id]
    _save_proj(proj)
    return {"status": "ok", "deleted": before - len(proj["items"])}


def link_item_usage(
    item_id: str,
    target_id: str,
    purpose: str = "unlock_door",
    sets_flag: str = "",
    success_text: str = "",
    consume_item: bool = True,
    gives_item: str = "",
    cutscene_id: str = ""
) -> dict[str, Any]:
    """Define where an item is used and what puzzle rule it triggers (e.g. unlocking a door, using an item on a prop/NPC, or combining items).
    purpose can be 'unlock_door', 'use_on_prop', 'give_to_npc', or 'combine_item'."""
    proj = _load_proj()
    item = next((i for i in proj["items"] if i["id"] == item_id), None)
    item_name = item["name"] if item else item_id

    target_hs = None
    for r in proj.get("rooms", []):
        for h in r.get("hotspots", []):
            if h.get("id") == target_id:
                target_hs = h
                break

    target_name = target_hs["name"] if target_hs else target_id
    flag = sets_flag or (f"{target_id}_unlocked" if purpose == "unlock_door" else f"{target_id}_solved")
    trigger = "combine_items" if purpose == "combine_item" else "use_item_on_hotspot"
    text = success_text or (f"*Click!* {item_name} unlocked {target_name}!" if purpose == "unlock_door" else f"Used {item_name} on {target_name}!")

    puz = next((p for p in proj["puzzles"] if p.get("item_id") == item_id and p.get("target_id") == target_id), None)
    if puz is None:
        puz = {
            "id": f"use_{item_id}_on_{target_id}",
            "name": f"Use {item_name} on {target_name}",
            "trigger": trigger,
            "item_id": item_id,
            "target_id": target_id,
            "requires_flag": "",
            "sets_flag": flag,
            "gives_item": gives_item,
            "cutscene_id": cutscene_id,
            "consume_item": bool(consume_item),
            "success_text": text
        }
        proj["puzzles"].append(puz)
    else:
        puz.update({
            "name": f"Use {item_name} on {target_name}",
            "trigger": trigger,
            "sets_flag": flag,
            "gives_item": gives_item,
            "cutscene_id": cutscene_id,
            "consume_item": bool(consume_item),
            "success_text": text
        })

    if target_hs and (target_hs.get("type") == "exit" or purpose == "unlock_door"):
        target_hs["locked"] = True
        target_hs["required_flag"] = flag
        if not target_hs.get("locked_text"):
            target_hs["locked_text"] = f"It's locked. I need {item_name}."

    _save_proj(proj)
    return {"status": "ok", "puzzle": puz, "door_updated": bool(target_hs and target_hs.get("type") == "exit")}


# ============================================================================
# 5. PUZZLES & RULES MCP TOOLS
# ============================================================================

def list_puzzles() -> dict[str, Any]:
    """List all puzzle rules and item interaction conditions."""
    proj = _load_proj()
    return {"count": len(proj.get("puzzles", [])), "puzzles": proj.get("puzzles", [])}


def get_puzzle(puzzle_id: str) -> dict[str, Any]:
    """Get full details of a specific puzzle rule by ID."""
    proj = _load_proj()
    puz = next((p for p in proj.get("puzzles", []) if p.get("id") == puzzle_id), None)
    if not puz:
        return {"error": f"Puzzle '{puzzle_id}' not found."}
    return {"puzzle": puz}


def create_or_update_puzzle(
    puzzle_id: str,
    name: str = "",
    trigger: str = "use_item_on_hotspot",
    item_id: str = "",
    target_id: str = "",
    requires_flag: str = "",
    sets_flag: str = "",
    gives_item: str = "",
    cutscene_id: str = "",
    consume_item: bool = True,
    success_text: str = ""
) -> dict[str, Any]:
    """Create or update a puzzle rule. trigger is 'use_item_on_hotspot' or 'combine_items'."""
    proj = _load_proj()
    clean_id = "".join(c for c in puzzle_id if c.isalnum() or c == "_").lower() or "puzzle_new"
    puz = next((p for p in proj["puzzles"] if p["id"] == clean_id), None)
    data_dict = {
        "id": clean_id,
        "name": name or clean_id,
        "trigger": trigger or "use_item_on_hotspot",
        "item_id": item_id,
        "target_id": target_id,
        "requires_flag": requires_flag,
        "sets_flag": sets_flag,
        "gives_item": gives_item,
        "cutscene_id": cutscene_id,
        "consume_item": bool(consume_item),
        "success_text": success_text or "That worked!"
    }
    if puz is None:
        proj["puzzles"].append(data_dict)
        action = "created"
    else:
        puz.update(data_dict)
        action = "updated"
    _save_proj(proj)
    return {"status": "ok", "action": action, "puzzle": data_dict}


def delete_puzzle(puzzle_id: str) -> dict[str, Any]:
    """Delete a puzzle rule by ID."""
    proj = _load_proj()
    before = len(proj["puzzles"])
    proj["puzzles"] = [p for p in proj["puzzles"] if p.get("id") != puzzle_id]
    _save_proj(proj)
    return {"status": "ok", "deleted": before - len(proj["puzzles"])}


# ============================================================================
# 6. BRANCHING DIALOG TREES MCP TOOLS
# ============================================================================

def list_dialog_trees() -> dict[str, Any]:
    """List all branching dialog trees."""
    proj = _load_proj()
    dlgs = []
    for d in proj.get("dialogs", []):
        dlgs.append({
            "id": d.get("id"),
            "name": d.get("name"),
            "npc_name": d.get("npc_name"),
            "root_node": d.get("root_node", "root"),
            "is_partner_dialog": (d.get("id") == proj.get("partner_dialog_id")),
            "node_count": len(d.get("nodes", []))
        })
    return {"count": len(dlgs), "dialogs": dlgs}


def get_dialog_tree(dialog_id: str) -> dict[str, Any]:
    """Get complete branching nodes, dialogue lines, and player choices for a dialog tree."""
    proj = _load_proj()
    dlg = next((d for d in proj.get("dialogs", []) if d.get("id") == dialog_id), None)
    if not dlg:
        return {"error": f"Dialog tree '{dialog_id}' not found."}
    return {"dialog": dlg}


def create_or_update_dialog_tree(
    dialog_id: str,
    name: str = "",
    npc_name: str = "",
    root_node: str = "root",
    set_as_partner: bool = False
) -> dict[str, Any]:
    """Create or update a dialog tree's metadata (id, title, NPC name, starting root node)."""
    proj = _load_proj()
    clean_id = "".join(c for c in dialog_id if c.isalnum() or c == "_").lower() or "dialog_new"
    dlg = next((d for d in proj["dialogs"] if d["id"] == clean_id), None)
    if dlg is None:
        dlg = {
            "id": clean_id,
            "name": name or f"Conversation with {npc_name or clean_id}",
            "npc_name": npc_name or "Speaker",
            "root_node": root_node or "root",
            "nodes": [
                {
                    "id": "root",
                    "speaker": "npc",
                    "npc_text": "Hello there! What's on your mind?",
                    "options": [
                        {
                            "text": "Nevermind, talk to you later.",
                            "reply_text": "See you around!",
                            "next_node": "__exit__",
                            "requires_flag": "",
                            "sets_flag": "",
                            "gives_item": "",
                            "triggers_cutscene": "",
                            "once": False
                        }
                    ]
                }
            ]
        }
        proj["dialogs"].append(dlg)
        action = "created"
    else:
        if name:
            dlg["name"] = name
        if npc_name:
            dlg["npc_name"] = npc_name
        if root_node:
            dlg["root_node"] = root_node
        action = "updated"

    if set_as_partner:
        proj["partner_dialog_id"] = clean_id

    _save_proj(proj)
    return {"status": "ok", "action": action, "dialog": dlg}


def delete_dialog_tree(dialog_id: str) -> dict[str, Any]:
    """Delete a dialog tree by ID."""
    proj = _load_proj()
    before = len(proj["dialogs"])
    proj["dialogs"] = [d for d in proj["dialogs"] if d.get("id") != dialog_id]
    if proj.get("partner_dialog_id") == dialog_id:
        proj["partner_dialog_id"] = ""
    _save_proj(proj)
    return {"status": "ok", "deleted": before - len(proj["dialogs"])}


def add_or_update_dialog_node(
    dialog_id: str,
    node_id: str,
    speaker: str = "npc",
    npc_text: str = ""
) -> dict[str, Any]:
    """Add or edit a conversation node within a dialog tree. speaker can be 'npc', 'partner', or 'player'."""
    proj = _load_proj()
    dlg = next((d for d in proj["dialogs"] if d["id"] == dialog_id), None)
    if not dlg:
        return {"error": f"Dialog tree '{dialog_id}' not found."}
    node = next((n for n in dlg.get("nodes", []) if n.get("id") == node_id), None)
    if node is None:
        node = {
            "id": node_id,
            "speaker": speaker,
            "npc_text": npc_text or "What else can I do for you?",
            "options": []
        }
        dlg.setdefault("nodes", []).append(node)
        action = "created"
    else:
        node["speaker"] = speaker
        if npc_text:
            node["npc_text"] = npc_text
        action = "updated"
    _save_proj(proj)
    return {"status": "ok", "action": action, "node": node}


def delete_dialog_node(dialog_id: str, node_id: str) -> dict[str, Any]:
    """Delete a node from a dialog tree."""
    proj = _load_proj()
    dlg = next((d for d in proj["dialogs"] if d["id"] == dialog_id), None)
    if not dlg:
        return {"error": f"Dialog tree '{dialog_id}' not found."}
    before = len(dlg.get("nodes", []))
    dlg["nodes"] = [n for n in dlg.get("nodes", []) if n.get("id") != node_id]
    if dlg.get("root_node") == node_id and dlg["nodes"]:
        dlg["root_node"] = dlg["nodes"][0]["id"]
    _save_proj(proj)
    return {"status": "ok", "deleted": before - len(dlg["nodes"])}


def add_dialog_player_choice(
    dialog_id: str,
    node_id: str,
    text: str,
    reply_text: str = "",
    next_node: str = "__stay__",
    requires_flag: str = "",
    sets_flag: str = "",
    gives_item: str = "",
    triggers_cutscene: str = "",
    once: bool = False
) -> dict[str, Any]:
    """Add a player response choice to a dialog node. next_node can be a node ID, '__stay__', or '__exit__'."""
    proj = _load_proj()
    dlg = next((d for d in proj["dialogs"] if d["id"] == dialog_id), None)
    if not dlg:
        return {"error": f"Dialog tree '{dialog_id}' not found."}
    node = next((n for n in dlg.get("nodes", []) if n.get("id") == node_id), None)
    if not node:
        return {"error": f"Node '{node_id}' not found in dialog '{dialog_id}'."}
    opt = {
        "text": text,
        "reply_text": reply_text,
        "next_node": next_node,
        "requires_flag": requires_flag,
        "sets_flag": sets_flag,
        "gives_item": gives_item,
        "triggers_cutscene": triggers_cutscene,
        "once": bool(once)
    }
    node.setdefault("options", []).append(opt)
    _save_proj(proj)
    return {"status": "ok", "choice_index": len(node["options"]) - 1, "choice": opt}


def delete_dialog_player_choice(dialog_id: str, node_id: str, choice_index: int) -> dict[str, Any]:
    """Delete a player choice by index from a dialog node."""
    proj = _load_proj()
    dlg = next((d for d in proj["dialogs"] if d["id"] == dialog_id), None)
    if not dlg:
        return {"error": f"Dialog tree '{dialog_id}' not found."}
    node = next((n for n in dlg.get("nodes", []) if n.get("id") == node_id), None)
    if not node or not node.get("options") or choice_index < 0 or choice_index >= len(node["options"]):
        return {"error": "Invalid choice index or node."}
    removed = node["options"].pop(choice_index)
    _save_proj(proj)
    return {"status": "ok", "removed": removed}


def ai_generate_dialog_tree(
    dialog_id: str,
    npc_name: str,
    topic_prompt: str,
    attach_to_hotspot: str = "",
    set_as_partner_dialog: bool = False
) -> dict[str, Any]:
    """Use Gemini LLM to write a multi-node branching LucasArts Dialog Tree, save it to the project, and optionally attach it to a room hotspot or Partner."""
    load_env()
    client = genai.Client()
    proj = _load_proj()
    clean_id = "".join(c for c in dialog_id if c.isalnum() or c == "_").lower() or "dialog_ai"
    room_names = [r.get("name", r.get("id", "")) for r in proj.get("rooms", [])]
    item_names = [f"{i.get('name')} ({i.get('id')})" for i in proj.get("items", [])]

    prompt = f"""You are a LucasArts adventure writer (Sam & Max, Monkey Island).
Create a branching Dialog Tree (id: "{clean_id}") for speaking with "{npc_name}".
Topic / Instructions: {topic_prompt}
Rooms in game: {", ".join(room_names)}
Items in game: {", ".join(item_names)}

Return ONLY valid JSON matching:
{{
  "name": "Conversation Title",
  "npc_name": "{npc_name}",
  "root_node": "root",
  "nodes": [
    {{
      "id": "root",
      "speaker": "npc",
      "npc_text": "Opening line",
      "options": [
        {{
          "text": "Player choice line",
          "reply_text": "Witty speaker reply",
          "next_node": "__exit__",
          "requires_flag": "",
          "sets_flag": "",
          "gives_item": "",
          "triggers_cutscene": "",
          "once": false
        }}
      ]
    }}
  ]
}}"""
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[prompt],
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    data = json.loads(response.text)
    if isinstance(data, list) and data:
        data = data[0]

    new_dlg = {
        "id": clean_id,
        "name": data.get("name", f"Talk with {npc_name}"),
        "npc_name": data.get("npc_name", npc_name),
        "root_node": data.get("root_node", "root"),
        "nodes": data.get("nodes", [])
    }
    proj["dialogs"] = [d for d in proj.get("dialogs", []) if d.get("id") != clean_id]
    proj["dialogs"].append(new_dlg)

    if set_as_partner_dialog:
        proj["partner_dialog_id"] = clean_id
    if attach_to_hotspot:
        for r in proj.get("rooms", []):
            for h in r.get("hotspots", []):
                if h.get("id") == attach_to_hotspot:
                    h["dialog_id"] = clean_id

    _save_proj(proj)
    return {"status": "ok", "dialog": new_dlg}


# ============================================================================
# 7. CUTSCENES & CINEMATICS TIMELINE MCP TOOLS
# ============================================================================

def list_cutscenes() -> dict[str, Any]:
    """List all cutscenes in the game."""
    proj = _load_proj()
    cs_list = []
    for c in proj.get("cutscenes", []):
        cs_list.append({
            "id": c.get("id"),
            "name": c.get("name"),
            "trigger_type": c.get("trigger_type"),
            "trigger_target": c.get("trigger_target"),
            "once": c.get("once", True),
            "step_count": len(c.get("steps", []))
        })
    return {"count": len(cs_list), "cutscenes": cs_list}


def get_cutscene(cutscene_id: str) -> dict[str, Any]:
    """Get full step sequence and trigger settings of a cutscene."""
    proj = _load_proj()
    cs = next((c for c in proj.get("cutscenes", []) if c.get("id") == cutscene_id), None)
    if not cs:
        return {"error": f"Cutscene '{cutscene_id}' not found."}
    return {"cutscene": cs}


def create_or_update_cutscene(
    cutscene_id: str,
    name: str = "",
    trigger_type: str = "manual",
    trigger_target: str = "",
    requires_flag: str = "",
    sets_flag: str = "",
    once: bool = True
) -> dict[str, Any]:
    """Create or update a cutscene's metadata. trigger_type can be 'manual', 'on_enter_room', or 'on_flag_set'."""
    proj = _load_proj()
    clean_id = "".join(c for c in cutscene_id if c.isalnum() or c == "_").lower() or "cutscene_new"
    cs = next((c for c in proj["cutscenes"] if c["id"] == clean_id), None)
    if cs is None:
        cs = {
            "id": clean_id,
            "name": name or clean_id,
            "trigger_type": trigger_type or "manual",
            "trigger_target": trigger_target,
            "requires_flag": requires_flag,
            "sets_flag": sets_flag,
            "once": bool(once),
            "steps": [
                {"type": "fade", "effect": "fade_in", "duration": 0.8},
                {"type": "say", "actor": "player", "text": "Let's inspect this scene.", "duration": 2.5}
            ]
        }
        proj["cutscenes"].append(cs)
        action = "created"
    else:
        if name:
            cs["name"] = name
        if trigger_type:
            cs["trigger_type"] = trigger_type
        if trigger_target:
            cs["trigger_target"] = trigger_target
        if requires_flag:
            cs["requires_flag"] = requires_flag
        if sets_flag:
            cs["sets_flag"] = sets_flag
        cs["once"] = bool(once)
        action = "updated"

    _save_proj(proj)
    return {"status": "ok", "action": action, "cutscene": cs}


def delete_cutscene(cutscene_id: str) -> dict[str, Any]:
    """Delete a cutscene by ID."""
    proj = _load_proj()
    before = len(proj["cutscenes"])
    proj["cutscenes"] = [c for c in proj["cutscenes"] if c.get("id") != cutscene_id]
    _save_proj(proj)
    return {"status": "ok", "deleted": before - len(proj["cutscenes"])}


def add_cutscene_step(
    cutscene_id: str,
    step_type: str,
    actor: str = "player",
    text: str = "",
    x: int = 500,
    y: int = 560,
    duration: float = 2.0,
    target_room_id: str = "",
    flag_name: str = "",
    item_id: str = "",
    dialog_id: str = "",
    anim_name: str = "",
    effect: str = "fade_in"
) -> dict[str, Any]:
    """Append a timeline action step to a cutscene. step_type can be 'say', 'walk', 'wait', 'fade', 'play_anim', 'change_room', 'give_item', 'set_flag', or 'start_dialog'."""
    proj = _load_proj()
    cs = next((c for c in proj["cutscenes"] if c["id"] == cutscene_id), None)
    if not cs:
        return {"error": f"Cutscene '{cutscene_id}' not found."}

    step: dict[str, Any] = {"type": step_type}
    if step_type == "say":
        step["actor"] = actor
        step["text"] = text or "..."
        step["duration"] = float(duration)
    elif step_type == "walk":
        step["actor"] = actor
        step["x"] = int(x)
        step["y"] = int(y)
    elif step_type == "wait":
        step["duration"] = float(duration)
    elif step_type == "fade":
        step["effect"] = effect or "fade_in"
        step["duration"] = float(duration)
    elif step_type == "play_anim":
        step["actor"] = actor
        step["anim"] = anim_name or "walk_down"
        step["duration"] = float(duration)
    elif step_type == "change_room":
        step["room_id"] = target_room_id or proj.get("start_room", "reception")
        step["x"] = int(x)
        step["y"] = int(y)
    elif step_type == "give_item":
        step["item_id"] = item_id
    elif step_type == "set_flag":
        step["flag"] = flag_name
    elif step_type == "start_dialog":
        step["dialog_id"] = dialog_id

    cs.setdefault("steps", []).append(step)
    _save_proj(proj)
    return {"status": "ok", "step_index": len(cs["steps"]) - 1, "step": step}


def delete_cutscene_step(cutscene_id: str, step_index: int) -> dict[str, Any]:
    """Delete a specific action step by index from a cutscene's timeline."""
    proj = _load_proj()
    cs = next((c for c in proj["cutscenes"] if c["id"] == cutscene_id), None)
    if not cs or not cs.get("steps") or step_index < 0 or step_index >= len(cs["steps"]):
        return {"error": "Invalid cutscene or step index."}
    removed = cs["steps"].pop(step_index)
    _save_proj(proj)
    return {"status": "ok", "removed_step": removed}


def ai_generate_cutscene(
    cutscene_id: str,
    room_id: str,
    scene_prompt: str,
    trigger_type: str = "manual",
    trigger_target: str = ""
) -> dict[str, Any]:
    """Use Gemini LLM to choreograph a multi-step LucasArts cutscene and save it to the project."""
    load_env()
    client = genai.Client()
    proj = _load_proj()
    clean_id = "".join(c for c in cutscene_id if c.isalnum() or c == "_").lower() or "cutscene_ai"

    prompt = f"""You are a LucasArts cutscene director. Create a cutscene in room "{room_id}".
Scene description: {scene_prompt}

Allowed step objects:
- {{"type": "fade", "effect": "fade_in" | "fade_out" | "flash_white" | "shake", "duration": 0.8}}
- {{"type": "walk", "actor": "player" | "partner", "x": 300..950, "y": 500..640}}
- {{"type": "say", "actor": "player" | "partner" | "narrator", "text": "Dialogue line", "duration": 3.2}}
- {{"type": "wait", "duration": 1.0}}
- {{"type": "change_room", "room_id": "{room_id}", "x": 500, "y": 560}}
- {{"type": "set_flag", "flag": "flag_name"}}

Return ONLY valid JSON:
{{
  "name": "Cutscene Name",
  "steps": [ ... ]
}}"""
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[prompt],
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    data = json.loads(response.text)
    if isinstance(data, list) and data:
        data = data[0]

    new_cs = {
        "id": clean_id,
        "name": data.get("name", clean_id),
        "trigger_type": trigger_type,
        "trigger_target": trigger_target or (room_id if trigger_type == "on_enter_room" else ""),
        "requires_flag": "",
        "sets_flag": "",
        "once": True,
        "steps": data.get("steps", [])
    }
    proj["cutscenes"] = [c for c in proj.get("cutscenes", []) if c.get("id") != clean_id]
    proj["cutscenes"].append(new_cs)
    _save_proj(proj)
    return {"status": "ok", "cutscene": new_cs}


# ============================================================================
# 8. SPRITES & ANIMATION STUDIO MCP TOOLS
# ============================================================================

def list_sprites() -> dict[str, Any]:
    """List all character sprites registered in AdventureForge with their scales and role assignments."""
    proj = _load_proj()
    sprites_dict = proj.get("sprites", {})
    results = []
    for sid, sdata in sprites_dict.items():
        results.append({
            "id": sid,
            "name": sdata.get("name", sid),
            "scale": sdata.get("scale", 3.0),
            "sheet": sdata.get("sheet", ""),
            "anim_roles": sdata.get("anim_roles", {}),
            "is_player": (sid == proj.get("player_sprite")),
            "is_partner": (sid == proj.get("partner_sprite"))
        })
    return {"count": len(results), "sprites": results}


def get_sprite(sprite_id: str) -> dict[str, Any]:
    """Get full details of a sprite including all sliced frames and animation sequences."""
    proj = _load_proj()
    sp = proj.get("sprites", {}).get(sprite_id)
    if not sp:
        return {"error": f"Sprite '{sprite_id}' not found."}
    meta_rel = sp.get("metadata_file", f"/assets/sprites/{sprite_id}_slicer.json").lstrip("/")
    meta_path = DATA_DIR / meta_rel
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    _normalize_vlm_meta(meta, fallback_name=sprite_id)
    return {"sprite": sp, "metadata": meta}


def add_or_update_sprite_animation(
    sprite_id: str,
    anim_name: str,
    fps: float = 8.0,
    loop: bool = True,
    frame_indices: str = "0,1,2"
) -> dict[str, Any]:
    """Create or update an animation sequence for a character sprite. frame_indices is a comma-separated list of frame indices e.g. '0,1,2,3'."""
    proj = _load_proj()
    sp = proj.get("sprites", {}).get(sprite_id)
    if not sp:
        return {"error": f"Sprite '{sprite_id}' not found."}

    meta_rel = sp.get("metadata_file", f"/assets/sprites/{sprite_id}_slicer.json").lstrip("/")
    meta_path = DATA_DIR / meta_rel
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {"vlm": {"animations": []}}
    _normalize_vlm_meta(meta, fallback_name=sprite_id)

    indices = [int(s.strip()) for s in frame_indices.split(",") if s.strip().isdigit()]
    anims = meta["vlm"].get("animations", [])
    cur = next((a for a in anims if a.get("name") == anim_name), None)
    if cur is None:
        cur = {"name": anim_name, "fps": float(fps), "loop": bool(loop), "indices": indices}
        anims.append(cur)
    else:
        cur["fps"] = float(fps)
        cur["loop"] = bool(loop)
        cur["indices"] = indices

    meta["vlm"]["animations"] = anims
    meta_path.write_text(json.dumps(meta, indent=2))
    return {"status": "ok", "animation": cur, "total_animations": len(anims)}


def delete_sprite_animation(sprite_id: str, anim_name: str) -> dict[str, Any]:
    """Delete an animation sequence from a sprite."""
    proj = _load_proj()
    sp = proj.get("sprites", {}).get(sprite_id)
    if not sp:
        return {"error": f"Sprite '{sprite_id}' not found."}
    meta_rel = sp.get("metadata_file", f"/assets/sprites/{sprite_id}_slicer.json").lstrip("/")
    meta_path = DATA_DIR / meta_rel
    if not meta_path.exists():
        return {"error": f"Metadata file for '{sprite_id}' not found."}
    meta = json.loads(meta_path.read_text())
    _normalize_vlm_meta(meta, fallback_name=sprite_id)
    anims = meta["vlm"].get("animations", [])
    before = len(anims)
    meta["vlm"]["animations"] = [a for a in anims if a.get("name") != anim_name]
    meta_path.write_text(json.dumps(meta, indent=2))
    return {"status": "ok", "deleted": before - len(meta["vlm"]["animations"])}


def assign_sprite_direction_role(sprite_id: str, role: str, anim_name: str) -> dict[str, Any]:
    """Assign an animation to a movement role ('walk', 'up', 'down', or 'idle')."""
    proj = _load_proj()
    sp = proj.get("sprites", {}).get(sprite_id)
    if not sp:
        return {"error": f"Sprite '{sprite_id}' not found."}
    roles = sp.setdefault("anim_roles", {})
    roles[role] = anim_name

    meta_rel = sp.get("metadata_file", f"/assets/sprites/{sprite_id}_slicer.json").lstrip("/")
    meta_path = DATA_DIR / meta_rel
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        meta["anim_roles"] = roles
        meta_path.write_text(json.dumps(meta, indent=2))

    _save_proj(proj)
    return {"status": "ok", "sprite_id": sprite_id, "role": role, "animation": anim_name}


def set_sprite_scale(sprite_id: str, scale: float = 3.0) -> dict[str, Any]:
    """Change the visual rendering scale multiplier for a character sprite (e.g. 2.5 or 3.2)."""
    proj = _load_proj()
    sp = proj.get("sprites", {}).get(sprite_id)
    if not sp:
        return {"error": f"Sprite '{sprite_id}' not found."}
    sp["scale"] = max(0.5, min(10.0, float(scale)))
    _save_proj(proj)
    return {"status": "ok", "sprite_id": sprite_id, "scale": sp["scale"]}


# ============================================================================
# 9. ASSET LIBRARY & BACKGROUND REMOVER MCP TOOLS
# ============================================================================

def list_assets(category: str = "all") -> dict[str, Any]:
    """List uploaded image assets on disk. category can be 'all', 'items', 'backgrounds', 'sprites', or 'frames'."""
    assets = []
    if ASSETS_DIR.exists():
        for path in sorted(ASSETS_DIR.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp") or ".orig." in path.name:
                continue
            rel = "/" + str(path.relative_to(DATA_DIR)).replace("\\", "/")
            parts = path.relative_to(ASSETS_DIR).parts
            top_cat = parts[0] if parts else "other"
            cat = "frames" if (top_cat == "sprites" and len(parts) > 1 and parts[1].endswith("_frames")) else top_cat
            if category != "all" and cat != category:
                continue
            assets.append({"url": rel, "name": path.name, "category": cat})
    return {"count": len(assets), "assets": assets}


def remove_asset_background(
    asset_url: str,
    mode: str = "corners",
    tolerance: int = 30,
    trim: bool = False
) -> dict[str, Any]:
    """Remove the background from an uploaded image asset (e.g. '/assets/items/pizzaslice.png'), saving a .orig backup and updating it retroactively everywhere."""
    target = _resolve_asset(asset_url)
    if not target.exists():
        return {"error": f"Asset not found: {asset_url}"}

    orig_backup = target.with_name(f"{target.stem}.orig{target.suffix}")
    if not orig_backup.exists():
        shutil.copy2(target, orig_backup)

    img = Image.open(target).convert("RGBA")
    arr = np.array(img)
    h, w, _ = arr.shape
    tol = max(1, int(tolerance)) * 3

    corners = [arr[0, 0, :3], arr[0, w - 1, :3], arr[h - 1, 0, :3], arr[h - 1, w - 1, :3]]

    if mode == "global":
        bg_rgb = corners[0].astype(int)
        diff = np.sum(np.abs(arr[:, :, :3].astype(int) - bg_rgb), axis=2)
        arr[diff <= tol, 3] = 0
    else:
        visited = np.zeros((h, w), dtype=bool)
        stack = [(0, 0, corners[0].astype(int)), (w - 1, 0, corners[1].astype(int)), (0, h - 1, corners[2].astype(int)), (w - 1, h - 1, corners[3].astype(int))]
        for sx, sy, c_rgb in stack:
            q = [(sx, sy)]
            while q:
                cx, cy = q.pop()
                if cx < 0 or cx >= w or cy < 0 or cy >= h or visited[cy, cx]:
                    continue
                visited[cy, cx] = True
                px_rgb = arr[cy, cx, :3].astype(int)
                if int(np.sum(np.abs(px_rgb - c_rgb))) <= tol:
                    arr[cy, cx, 3] = 0
                    q.extend([(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)])

    out_img = Image.fromarray(arr, "RGBA")
    if trim:
        bbox = out_img.getbbox()
        if bbox:
            out_img = out_img.crop(bbox)
    out_img.save(target, format="PNG")

    return {
        "status": "ok",
        "asset_url": asset_url,
        "width": out_img.width,
        "height": out_img.height,
        "backup_created": True
    }


def restore_asset_original(asset_url: str) -> dict[str, Any]:
    """Revert an edited asset image back to its original pre-modified disk backup."""
    target = _resolve_asset(asset_url)
    orig_candidates = [
        target.with_name(f"{target.stem}.orig{target.suffix}"),
        target.with_name(f"{target.stem}.orig.png"),
        target.with_name(f"{target.stem}.orig.jpg"),
        target.with_name(f"{target.stem}.orig.jpeg"),
    ]
    orig_file = next((f for f in orig_candidates if f.exists()), None)
    if not orig_file:
        return {"error": f"No original backup found for {asset_url}"}
    shutil.copy2(orig_file, target)
    return {"status": "ok", "restored": asset_url, "source_backup": orig_file.name}


def delete_asset_file(asset_url: str) -> dict[str, Any]:
    """Delete an image asset and its backup from the project's data/assets directory."""
    target = _resolve_asset(asset_url)
    if not target.exists():
        return {"error": f"Asset file not found: {asset_url}"}
    target.unlink()
    for orig in target.parent.glob(f"{target.stem}.orig.*"):
        try:
            orig.unlink()
        except Exception:
            pass
    return {"status": "ok", "deleted": asset_url}


def pixelize_asset(
    asset_url: str,
    pixel_size: int = 32,
    num_colors: int = 16,
    auto_remove_bg: bool = False
) -> dict[str, Any]:
    """Convert any image asset into authentic 16-bit/32-bit pixel art by downsampling, palette-quantizing, and upscaling with nearest-neighbor interpolation."""
    target = _resolve_asset(asset_url)
    if not target.exists():
        return {"error": f"Asset not found: {asset_url}"}

    orig_backup = target.with_name(f"{target.stem}.orig{target.suffix}")
    if not orig_backup.exists():
        shutil.copy2(target, orig_backup)

    try:
        pixel_size = int(pixel_size)
    except (ValueError, TypeError):
        pixel_size = 32

    try:
        img = Image.open(target).convert("RGBA")
        w, h = img.size
        aspect = w / h

        # If it's a full background or high-res scene (w >= 384) and pixel_size wasn't explicitly set large,
        # use authentic SCUMM VGA resolution (320px wide) rather than 32px item thumbnail resolution!
        is_background = ("background" in asset_url.lower()) or (w >= 384 and pixel_size <= 64)
        if is_background:
            target_res = 320
            dw = target_res
            dh = max(160, int(target_res / aspect))
            colors = max(32, min(256, int(num_colors) if num_colors > 16 else 128))
        else:
            dw = max(16, min(128, pixel_size))
            dh = max(8, int(dw / aspect)) if aspect >= 1.0 else max(8, int(dw * aspect))
            colors = max(4, min(64, int(num_colors)))

        # Use NEAREST resampling to preserve razor-sharp pixel edges (no bilinear blur!)
        small = img.resize((dw, dh), Image.Resampling.NEAREST)
        r, g, b, a = small.split()
        rgb = Image.merge("RGB", (r, g, b))
        quantized = rgb.quantize(colors=colors, dither=Image.Dither.FLOYDSTEINBERG).convert("RGB")
        qr, qg, qb = quantized.split()
        a_crisp = a.point(lambda p: 255 if p > 64 else 0)
        pixel_art = Image.merge("RGBA", (qr, qg, qb, a_crisp))

        # Scale back up to original display size with NEAREST for chunky pixels
        final_img = pixel_art.resize((w, h), Image.Resampling.NEAREST)
        final_img.save(target, format="PNG")

        if auto_remove_bg:
            try:
                remove_asset_background(asset_url, mode="corners", tolerance=35, trim=True)
            except Exception:
                pass

        return {
            "status": "ok",
            "asset_url": asset_url,
            "pixel_size": pixel_size,
            "num_colors": num_colors,
            "display_size": [w, h],
            "backed_up_to": orig_backup.name
        }
    except Exception as e:
        return {"error": f"Failed to pixelize image: {e}"}


# ============================================================================
# 10. MEDIA GENERATION, SEARCH & SOUND EFFECTS MCP TOOLS (.env Powered)
# ============================================================================

def _get_api_keys() -> dict[str, str]:
    """Retrieve API keys from .env with fallback paths."""
    load_env()
    for env_path in [
        BASE_DIR / ".env",
        BASE_DIR.parent / ".env",
        Path("/home/x/Desktop/IDEAS/.env")
    ]:
        if env_path.exists():
            load_env(str(env_path))
    return {
        "gemini": os.getenv("GEMINI_API_KEY", "").strip(),
        "serp": os.getenv("SERP_API_KEY", "").strip(),
        "freesound": os.getenv("FREESOUND_API_KEY", "").strip(),
        "hf": os.getenv("HF_TOKEN", "").strip(),
        "nvidia": os.getenv("NVIDIA_API_KEY", "").strip(),
        "prime": os.getenv("PRIME_API_KEY", "").strip(),
        "spritefusion": os.getenv("SPRITE_FUSION_API_KEY", "").strip() or os.getenv("SPRITEFUSION_API_KEY", "").strip(),
    }


def list_available_media_apis() -> dict[str, Any]:
    """Check configuration and availability of media generation and search API keys in .env (Freesound, SerpAPI Google Images, Gemini, Sprite Fusion MCP, Hugging Face, Local Jetson Iris 3B Diffusion)."""
    keys = _get_api_keys()
    iris_path = config.get_iris_model_path()
    return {
        "freesound_audio": bool(keys.get("freesound")),
        "serp_google_images": bool(keys.get("serp")),
        "gemini_image_gen": bool(keys.get("gemini")),
        "spritefusion_mcp": bool(keys.get("spritefusion")),
        "huggingface": bool(keys.get("hf")),
        "nvidia": bool(keys.get("nvidia")),
        "prime": bool(keys.get("prime")),
        "jetson_local_iris_diffusion": iris_path.exists(),
        "jetson_local_model_path": str(iris_path) if iris_path.exists() else "",
        "jetson_text_encoder_path": str(config.get_iris_te_path()) if config.get_iris_te_path().exists() else "",
        "jetson_cuda_accelerated": True,
    }


def search_and_download_sound_effects(
    query: str,
    category: str = "sounds",
    filename: str = "",
    min_duration: float = 0.2,
    max_duration: float = 20.0,
    link_to_room_id: str = "",
    link_to_puzzle_id: str = ""
) -> dict[str, Any]:
    """Search Freesound.org using FREESOUND_API_KEY from .env, download high-quality sound effect or music preview directly into /assets/sounds or /assets/music, and optionally link to a room or puzzle."""
    keys = _get_api_keys()
    fs_key = keys.get("freesound")
    if not fs_key:
        return {"error": "FREESOUND_API_KEY not found in .env"}
    if not query.strip():
        return {"error": "Search query cannot be empty"}

    cat_name = "music" if category.lower() in ("music", "bgm", "ambient") else "sounds"
    cat_dir = ASSETS_DIR / cat_name
    cat_dir.mkdir(parents=True, exist_ok=True)

    params = urllib.parse.urlencode({
        "query": query.strip(),
        "token": fs_key,
        "fields": "id,name,duration,previews,tags",
        "filter": f"duration:[{max(0.1, float(min_duration))} TO {min(180.0, float(max_duration))}]",
        "page_size": 10
    })
    url = f"https://freesound.org/apiv2/search/text/?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "AdventureForge/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        return {"error": f"Freesound API request failed: {e}"}

    results = data.get("results") or []
    if not results:
        return {"error": f"No sound effects found for query: '{query}'"}

    cand = next((r for r in results if r.get("previews", {}).get("preview-hq-mp3")), results[0])
    preview_url = cand.get("previews", {}).get("preview-hq-mp3") or cand.get("previews", {}).get("preview-lq-mp3")
    if not preview_url:
        return {"error": "Sound result has no downloadable audio preview"}

    if not filename:
        clean_name = re.sub(r"[^\w\-_\.]", "_", cand.get("name", "sound")).lower()
        if not clean_name.endswith((".mp3", ".wav", ".ogg")):
            clean_name += ".mp3"
        filename = f"{clean_name}"
    else:
        if not filename.endswith((".mp3", ".wav", ".ogg")):
            filename += ".mp3"
        filename = re.sub(r"[^\w\-_\.]", "_", filename).lower()

    dest_path = cat_dir / filename
    dl_req = urllib.request.Request(preview_url, headers={"User-Agent": "AdventureForge/1.0"})
    try:
        with urllib.request.urlopen(dl_req, timeout=15) as dl_resp, open(dest_path, "wb") as f:
            f.write(dl_resp.read())
    except Exception as e:
        return {"error": f"Failed to download audio preview: {e}"}

    rel_url = f"/assets/{cat_name}/{filename}"

    proj = _load_proj()
    linked = []
    if link_to_room_id:
        room = next((r for r in proj.get("rooms", []) if r.get("id") == link_to_room_id), None)
        if room:
            room["music"] = rel_url
            linked.append(f"Room '{room.get('name', link_to_room_id)}' (music/ambient)")

    if link_to_puzzle_id:
        puz = next((p for p in proj.get("puzzles", []) if p.get("id") == link_to_puzzle_id), None)
        if puz:
            puz["sound_effect"] = rel_url
            linked.append(f"Puzzle '{puz.get('name', link_to_puzzle_id)}' (solve sound)")

    if linked:
        _save_proj(proj)

    return {
        "status": "ok",
        "sound_name": cand.get("name"),
        "duration": cand.get("duration"),
        "freesound_id": cand.get("id"),
        "file_url": rel_url,
        "file_path": str(dest_path),
        "size_bytes": dest_path.stat().st_size,
        "linked_to": linked
    }


def search_and_download_images(
    query: str,
    category: str = "items",
    filename: str = "",
    transparent_only: bool = False,
    auto_remove_bg: bool = True,
    link_to_room_id: str = "",
    link_to_item_id: str = "",
    link_to_hotspot_id: str = ""
) -> dict[str, Any]:
    """Search Google Images using SERP_API_KEY from .env, download high-res images directly into /assets/items, /assets/backgrounds, or /assets/sprites, optionally remove background to make it transparent, and link to room, item, or prop."""
    keys = _get_api_keys()
    serp_key = keys.get("serp")
    if not serp_key:
        return {"error": "SERP_API_KEY not found in .env"}
    if not query.strip():
        return {"error": "Search query cannot be empty"}

    valid_cats = {"items", "backgrounds", "sprites"}
    target_cat = category if category in valid_cats else "items"
    cat_dir = ASSETS_DIR / target_cat
    cat_dir.mkdir(parents=True, exist_ok=True)

    search_q = query.strip()
    if transparent_only and "transparent" not in search_q.lower():
        search_q += " transparent png"
    if target_cat == "items" and "pixel art" not in search_q.lower() and "icon" not in search_q.lower():
        search_q += " pixel art icon"
    elif target_cat == "backgrounds" and "background" not in search_q.lower() and "room" not in search_q.lower():
        search_q += " adventure game background"

    params = urllib.parse.urlencode({
        "engine": "google_images",
        "q": search_q,
        "api_key": serp_key,
        "num": 10
    })
    url = f"https://serpapi.com/search.json?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        return {"error": f"SerpApi search failed: {e}"}

    imgs = data.get("images_results") or []
    if not imgs:
        return {"error": f"No Google Images results for query: '{query}'"}

    if not filename:
        clean_name = re.sub(r"[^\w\-_\.]", "_", query.strip().split()[0]).lower()
        filename = f"{clean_name}_{int(time.time()) % 10000}.png"
    else:
        if not filename.endswith((".png", ".jpg", ".jpeg", ".webp")):
            filename += ".png"
        filename = re.sub(r"[^\w\-_\.]", "_", filename).lower()

    dest_path = cat_dir / filename

    downloaded = False
    chosen_meta = {}
    for im in imgs[:6]:
        cand_url = im.get("original") or im.get("thumbnail")
        if not cand_url:
            continue
        try:
            ireq = urllib.request.Request(cand_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            with urllib.request.urlopen(ireq, timeout=8) as iresp:
                raw_bytes = iresp.read()
                pil_img = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
                pil_img.save(dest_path, format="PNG")
                downloaded = True
                chosen_meta = im
                break
        except Exception:
            continue

    if not downloaded:
        thumb_url = imgs[0].get("thumbnail")
        if thumb_url:
            try:
                ireq = urllib.request.Request(thumb_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(ireq, timeout=8) as iresp:
                    pil_img = Image.open(io.BytesIO(iresp.read())).convert("RGBA")
                    pil_img.save(dest_path, format="PNG")
                    downloaded = True
                    chosen_meta = imgs[0]
            except Exception as e:
                return {"error": f"Failed downloading image candidates: {e}"}

    if not downloaded:
        return {"error": "Failed to download image from search results"}

    rel_url = f"/assets/{target_cat}/{filename}"

    bg_removed = False
    if auto_remove_bg and target_cat in ("items", "sprites"):
        try:
            res_bg = remove_asset_background(rel_url, mode="corners", tolerance=35, trim=True)
            bg_removed = "error" not in res_bg
        except Exception:
            pass

    proj = _load_proj()
    linked = []
    if link_to_room_id:
        room = next((r for r in proj.get("rooms", []) if r.get("id") == link_to_room_id), None)
        if room:
            room["background"] = rel_url
            linked.append(f"Room '{room.get('name', link_to_room_id)}' (background)")

    if link_to_item_id:
        item = next((i for i in proj.get("items", []) if i.get("id") == link_to_item_id), None)
        if item:
            item["icon"] = rel_url
            linked.append(f"Item '{item.get('name', link_to_item_id)}' (icon)")

    if link_to_hotspot_id:
        for r in proj.get("rooms", []):
            hs = next((h for h in r.get("hotspots", []) if h.get("id") == link_to_hotspot_id), None)
            if hs:
                hs["icon"] = rel_url
                linked.append(f"Hotspot '{hs.get('name', link_to_hotspot_id)}' (icon)")
                break

    if linked:
        _save_proj(proj)

    return {
        "status": "ok",
        "file_url": rel_url,
        "title": chosen_meta.get("title", filename),
        "source": chosen_meta.get("link", ""),
        "background_removed": bg_removed,
        "linked_to": linked
    }


def _call_spritefusion_mcp(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Helper to communicate with Sprite Fusion MCP endpoint (https://www.spritefusion.com/mcp) over SSE stream."""
    keys = _get_api_keys()
    sf_key = keys.get("spritefusion")
    if not sf_key:
        return {"error": "SPRITE_FUSION_API_KEY not found in .env."}

    req_data = json.dumps({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        },
        "id": int(time.time() * 1000)
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://www.spritefusion.com/mcp",
        data=req_data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {sf_key}",
            "User-Agent": "AdventureForge/1.0"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=55) as resp:
            resp_text = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return {"error": f"Failed connecting to Sprite Fusion MCP: {e}"}

    parsed = None
    for line in resp_text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload_str = line[len("data:"):].strip()
            try:
                msg = json.loads(payload_str)
                if "result" in msg or "error" in msg:
                    parsed = msg
                    break
            except Exception:
                pass
    if not parsed:
        try:
            parsed = json.loads(resp_text)
        except Exception:
            return {"error": f"Invalid response from Sprite Fusion: {resp_text[:300]}"}

    if "error" in parsed:
        err = parsed["error"]
        msg = err.get("message") if isinstance(err, dict) else str(err)
        return {"error": f"Sprite Fusion MCP Error: {msg}"}

    return parsed.get("result", {})


def spritefusion_get_credits() -> dict[str, Any]:
    """Get the current Sprite Fusion account credit balance via MCP server."""
    res = _call_spritefusion_mcp("get_credits", {})
    if "error" in res:
        return res
    if "structuredContent" in res and "credits" in res["structuredContent"]:
        return {"credits": res["structuredContent"]["credits"]}
    for c in res.get("content", []):
        try:
            val = json.loads(c.get("text", "{}"))
            if "credits" in val:
                return {"credits": val["credits"]}
        except Exception:
            pass
    return {"credits": 0, "raw": res}


def spritefusion_list_saved_assets() -> dict[str, Any]:
    """List all previously generated pixel art assets saved in the user's Sprite Fusion cloud library."""
    res = _call_spritefusion_mcp("list_assets", {})
    if "error" in res:
        return res
    for c in res.get("content", []):
        try:
            val = json.loads(c.get("text", "{}"))
            if "assets" in val:
                return {"count": len(val["assets"]), "assets": val["assets"]}
        except Exception:
            pass
    return {"count": 0, "assets": []}


def spritefusion_generate_pixel_art(
    prompt: str,
    size: int = 32,
    category: str = "items",
    filename: str = "",
    auto_remove_bg: bool = False,
    link_to_room_id: str = "",
    link_to_item_id: str = "",
    link_to_hotspot_id: str = ""
) -> dict[str, Any]:
    """Generate authentic pixel art using Sprite Fusion MCP Server (https://www.spritefusion.com/mcp) via SPRITE_FUSION_API_KEY from .env, saving sprites directly into /assets/*. If credits are depleted, automatically searches and reuses matching assets from the user's Sprite Fusion cloud library."""
    keys = _get_api_keys()
    sf_key = keys.get("spritefusion")
    if not sf_key:
        return {
            "error": "SPRITE_FUSION_API_KEY not found in .env.",
            "mcp_server_url": "https://www.spritefusion.com/mcp",
            "setup_guide": "Sign up at https://www.spritefusion.com/account/api-keys to get your API key, then add SPRITE_FUSION_API_KEY=sf_live_... to your .env file."
        }
    if not prompt.strip():
        return {"error": "Prompt cannot be empty"}

    try:
        size = int(size)
    except (ValueError, TypeError):
        size = 32
    if size not in (16, 32, 64):
        size = 32

    valid_cats = {"items", "backgrounds", "sprites"}
    target_cat = category if category in valid_cats else "items"
    cat_dir = ASSETS_DIR / target_cat
    cat_dir.mkdir(parents=True, exist_ok=True)

    if not filename:
        clean_name = re.sub(r"[^\w\-_\.]", "_", prompt.strip().split()[0]).lower()
        filename = f"{clean_name}_{int(time.time()) % 10000}.png"
    else:
        if not filename.endswith((".png", ".jpg", ".jpeg", ".webp")):
            filename += ".png"
        filename = re.sub(r"[^\w\-_\.]", "_", filename).lower()

    dest_path = cat_dir / filename
    rel_url = f"/assets/{target_cat}/{filename}"

    download_url = ""
    reused_from_library = False

    # Attempt generation via Sprite Fusion MCP
    res = _call_spritefusion_mcp("generate_sprites", {"prompt": prompt, "size": size})

    if "error" in res or res.get("isError"):
        err_msg = ""
        if "error" in res:
            err_msg = str(res["error"])
        elif res.get("isError"):
            for c in res.get("content", []):
                if c.get("text"):
                    err_msg = c["text"]
                    break
        # If out of credits or generation failed, check if we can reuse a matching saved asset from library
        saved_assets_res = spritefusion_list_saved_assets()
        saved_list = saved_assets_res.get("assets", [])
        prompt_words = [w.lower() for w in re.findall(r"\w+", prompt) if len(w) > 2]

        best_match = None
        best_score = 0
        for item in saved_list:
            item_prompt = item.get("prompt", "").lower()
            score = sum(1 for w in prompt_words if w in item_prompt)
            if score > best_score:
                best_score = score
                best_match = item

        if best_match and best_match.get("assetUrl"):
            download_url = best_match["assetUrl"]
            reused_from_library = True
        else:
            return {
                "error": f"Sprite Fusion generation unavailable: {err_msg}",
                "suggestion": "Sprite Fusion credits are depleted (15 credits needed per generation). You can top up at https://www.spritefusion.com/pricing, or use generate_image_ai / search_and_download_images for instant graphic generation."
            }
    else:
        # Extract download URL from successful generation result
        for c in res.get("content", []):
            text_val = c.get("text", "")
            try:
                json_match = re.search(r'(\{.*"outputs"\s*:\s*\[.*\}\])', text_val, re.DOTALL)
                if json_match:
                    embedded = json.loads(json_match.group(1))
                    outputs = embedded.get("outputs", [])
                    if outputs and outputs[0].get("assetUrl"):
                        download_url = outputs[0]["assetUrl"]
                        break
            except Exception:
                pass
            if not download_url:
                urls = re.findall(r'https?://[^\s"\'<>)]+\.png(?:\?[^\s"\'<>)]*)?', text_val)
                if urls:
                    download_url = urls[0]
                    break

    if not download_url:
        return {"error": f"No download URL returned from Sprite Fusion: {res}"}

    try:
        dl_req = urllib.request.Request(download_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(dl_req, timeout=25) as dl_resp, open(dest_path, "wb") as f:
            f.write(dl_resp.read())
    except Exception as dl_err:
        return {"error": f"Failed downloading Sprite Fusion asset from {download_url}: {dl_err}"}

    bg_removed = False
    if auto_remove_bg:
        try:
            res_bg = remove_asset_background(rel_url, mode="corners", tolerance=35, trim=True)
            bg_removed = "error" not in res_bg
        except Exception:
            pass

    proj = _load_proj()
    linked = []
    if link_to_room_id:
        room = next((r for r in proj.get("rooms", []) if r.get("id") == link_to_room_id), None)
        if room:
            room["background"] = rel_url
            linked.append(f"Room '{room.get('name', link_to_room_id)}' (background)")

    if link_to_item_id:
        item = next((i for i in proj.get("items", []) if i.get("id") == link_to_item_id), None)
        if item:
            item["icon"] = rel_url
            linked.append(f"Item '{item.get('name', link_to_item_id)}' (icon)")

    if link_to_hotspot_id:
        for r in proj.get("rooms", []):
            hs = next((h for h in r.get("hotspots", []) if h.get("id") == link_to_hotspot_id), None)
            if hs:
                hs["icon"] = rel_url
                linked.append(f"Hotspot '{hs.get('name', link_to_hotspot_id)}' (icon)")
                break

    if linked:
        _save_proj(proj)

    return {
        "status": "ok",
        "file_url": rel_url,
        "filename": filename,
        "prompt": prompt,
        "size": size,
        "generator_method": "Sprite Fusion Cloud Library (reused asset)" if reused_from_library else "Sprite Fusion Pixel Art MCP",
        "background_removed": bg_removed,
        "linked_to": linked
    }


# Model paths using config
LOCAL_SD15_GGUF = config.get_sd15_model_path("q8")
LOCAL_SD15_GGUF_Q4 = config.get_sd15_model_path("q4")
LOCAL_REDMOND_LORA = config.get_lora_path(config.REDMOND_LORA)
LOCAL_LUCASARTS_LORA = config.get_lora_path(config.LUCASARTS_LORA)
LOCAL_IRIS_GGUF = config.get_iris_model_path()
LOCAL_IRIS_TE = config.get_iris_te_path()


def jetson_generate_image(
    prompt: str,
    category: str = "items",
    filename: str = "",
    width: int = 512,
    height: int = 512,
    steps: int = 20,
    cfg_scale: float = 7.0,
    sampling_method: str = "euler_a",
    model_engine: str = "sd15",
    base_model_file: str = "",
    active_loras: dict[str, float] | None = None,
    negative_prompt: str = "",
    seed: int = -1,
    lucasarts_weight: float = 0.0,
    redmond_weight: float = 0.0,
    pixel_art: bool = False,
    pixel_size: int = 32,
    num_colors: int = 16,
    auto_remove_bg: bool = False,
    link_to_room_id: str = "",
    link_to_item_id: str = "",
    link_to_hotspot_id: str = ""
) -> dict[str, Any]:
    """Generate image locally and offline on the NVIDIA Jetson GPU.
    Supports raw SD 1.5, Sakura-Iris-3B, or user-selected LoRAs with explicit weights."""
    if not LOCAL_SD15_GGUF.exists() and not LOCAL_IRIS_GGUF.exists():
        return {"error": f"No local diffusion models found in {config.JETSON_MODELS_DIR}."}
    if not prompt.strip():
        return {"error": "Prompt cannot be empty"}

    try:
        width = int(width)
        height = int(height)
        steps = int(steps)
        cfg_scale = float(cfg_scale)
        pixel_size = int(pixel_size)
        num_colors = int(num_colors)
        seed = int(seed)
    except (ValueError, TypeError):
        width, height, steps, cfg_scale, pixel_size, num_colors, seed = 512, 512, 20, 7.0, 32, 16, -1

    width = max(256, min(1024, (width // 64) * 64))
    height = max(256, min(1024, (height // 64) * 64))
    steps = max(10, min(50, steps))
    cfg_scale = max(1.0, min(15.0, cfg_scale))

    valid_cats = {"items", "backgrounds", "sprites"}
    target_cat = category if category in valid_cats else "items"
    cat_dir = ASSETS_DIR / target_cat
    cat_dir.mkdir(parents=True, exist_ok=True)

    if not filename:
        clean_name = re.sub(r"[^\w\-_\.]", "_", prompt.strip().split()[0]).lower()
        filename = f"{clean_name}_{int(time.time()) % 10000}.png"
    else:
        if not filename.endswith((".png", ".jpg", ".jpeg", ".webp")):
            filename += ".png"
        filename = re.sub(r"[^\w\-_\.]", "_", filename).lower()

    dest_path = cat_dir / filename
    rel_url = f"/assets/{target_cat}/{filename}"
    out_rel = f"out_{int(time.time() * 1000)}.png"

    sd_bin = config.get_sd_cli_binary()
    if not sd_bin.exists():
        return {"error": f"stable-diffusion.cpp binary not found at {sd_bin}. Please verify build."}

    bin_path = f"/data/stable-diffusion.cpp/build/bin/{sd_bin.name}"

    # Only apply LoRAs if explicitly requested by user (weight > 0.0)
    lora_tags = []
    loras_dir = config.JETSON_LORAS_DIR

    if active_loras and isinstance(active_loras, dict):
        for lname, lweight in active_loras.items():
            try:
                w = float(lweight)
                if w > 0.01:
                    cname = Path(lname).stem
                    lora_tags.append(f"<lora:{cname}:{w:.2f}>")
            except (ValueError, TypeError):
                pass
    else:
        try:
            lw = float(lucasarts_weight or 0.0)
            if lw > 0.01 and LOCAL_LUCASARTS_LORA.exists():
                lora_tags.append(f"<lora:lucasarts_retro_style:{lw:.2f}>")
        except (ValueError, TypeError):
            pass

        try:
            rw = float(redmond_weight or 0.0)
            if rw > 0.01 and LOCAL_REDMOND_LORA.exists():
                lora_tags.append(f"<lora:PixelArtRedmond:{rw:.2f}>")
        except (ValueError, TypeError):
            pass

    model_prompt = prompt.strip()
    if lora_tags:
        model_prompt += ", " + ", ".join(lora_tags)

    neg = (negative_prompt or "").strip() or "blurry, photograph, 3d render, realistic, smooth gradient, vector"

    target_base_name = LOCAL_SD15_GGUF.name
    if base_model_file:
        cand = config.JETSON_SD15_DIR / Path(base_model_file).name
        if cand.exists():
            target_base_name = cand.name

    data_volume = f"{config.JETSON_MODELS_DIR.parent}:/data"

    if model_engine == "iris" and LOCAL_IRIS_GGUF.exists():
        # Sakura-Iris-3B DiT + Qwen3-VL
        if not sampling_method or sampling_method == "euler_a":
            sampling_method = "dpm++2m"
        if cfg_scale > 4.5:
            cfg_scale = 3.0

        cmd = [
            "docker", "run", "--runtime", "nvidia", "--rm",
            "-u", f"{os.getuid()}:{os.getgid()}",
            "-v", data_volume,
            "-w", "/data",
            config.JETSON_DOCKER_IMAGE,
            bin_path,
            "--diffusion-model", f"/data/models/iris-3b/{LOCAL_IRIS_GGUF.name}",
            "--llm", f"/data/models/iris-3b/{LOCAL_IRIS_TE.name}",
            "--backend", "te=cpu,diffusion=CUDA0",
            "--params-backend", "diffusion=disk,te=disk",
            "--max-vram", "2.0",
            "--sampling-method", sampling_method,
            "--cfg-scale", str(cfg_scale),
            "-p", model_prompt,
            "-n", neg,
            "-W", str(width),
            "-H", str(height),
            "--steps", str(steps),
            "-o", f"/data/{out_rel}"
        ]
        if seed >= 0:
            cmd.extend(["-s", str(seed)])
        method_label = "Jetson GPU (Sakura-Iris-3B DiT)"
    else:
        # Standard SD 1.5 GGUF on CUDA0
        if not sampling_method:
            sampling_method = "euler_a"

        cmd = [
            "docker", "run", "--runtime", "nvidia", "--rm",
            "-u", f"{os.getuid()}:{os.getgid()}",
            "-v", data_volume,
            "-w", "/data",
            config.JETSON_DOCKER_IMAGE,
            bin_path,
            "-m", f"/data/models/sd15/{target_base_name}",
            "--lora-model-dir", "/data/models/loras",
            "--backend", "cuda0",
            "--sampling-method", sampling_method,
            "--cfg-scale", str(cfg_scale),
            "-p", model_prompt,
            "-n", neg,
            "-W", str(width),
            "-H", str(height),
            "--steps", str(steps),
            "-o", f"/data/{out_rel}"
        ]
        if seed >= 0:
            cmd.extend(["-s", str(seed)])

        applied_desc = []
        if lora_tags:
            applied_desc.append(" + ".join(lora_tags))
        method_label = f"Jetson GPU ({target_base_name}{' + ' + ', '.join(applied_desc) if applied_desc else ' Raw Base'})"

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        out_file = Path(f"{config.JETSON_MODELS_DIR.parent}/{out_rel}")
        if not out_file.exists():
            return {
                "error": f"Generation failed: {proc.stderr or proc.stdout[:300]}",
                "returncode": proc.returncode
            }
        shutil.move(str(out_file), str(dest_path))
    except Exception as e:
        return {"error": f"Failed running local diffusion model: {e}"}

    bg_removed = False
    # Automatically pixelize to crisp retro game standard
    if pixel_art:
        try:
            res_pix = pixelize_asset(rel_url, pixel_size=pixel_size, num_colors=num_colors, auto_remove_bg=auto_remove_bg)
            bg_removed = auto_remove_bg and ("error" not in res_pix)
        except Exception:
            pass
    elif auto_remove_bg and target_cat in ("items", "sprites"):
        try:
            res_bg = remove_asset_background(rel_url, mode="corners", tolerance=35, trim=True)
            bg_removed = "error" not in res_bg
        except Exception:
            pass

    proj = _load_proj()
    linked = []
    if link_to_room_id:
        room = next((r for r in proj.get("rooms", []) if r.get("id") == link_to_room_id), None)
        if room:
            room["background"] = rel_url
            linked.append(f"Room '{room.get('name', link_to_room_id)}' (background)")

    if link_to_item_id:
        item = next((i for i in proj.get("items", []) if i.get("id") == link_to_item_id), None)
        if item:
            item["icon"] = rel_url
            linked.append(f"Item '{item.get('name', link_to_item_id)}' (icon)")

    if link_to_hotspot_id:
        for r in proj.get("rooms", []):
            hs = next((h for h in r.get("hotspots", []) if h.get("id") == link_to_hotspot_id), None)
            if hs:
                hs["icon"] = rel_url
                linked.append(f"Hotspot '{hs.get('name', link_to_hotspot_id)}' (icon)")
                break

    if linked:
        _save_proj(proj)

    return {
        "status": "ok",
        "file_url": rel_url,
        "filename": filename,
        "prompt": prompt,
        "generator_method": method_label,
        "background_removed": bg_removed,
        "linked_to": linked
    }


def generate_image_ai(
    prompt: str,
    category: str = "items",
    filename: str = "",
    aspect_ratio: str = "1:1",
    auto_remove_bg: bool = True,
    link_to_room_id: str = "",
    link_to_item_id: str = "",
    link_to_hotspot_id: str = ""
) -> dict[str, Any]:
    """Generate image using Gemini/HF API key from .env (with intelligent SerpApi & procedural fallback), saves to /assets/*, optionally strips background, and wires directly into game entities."""
    keys = _get_api_keys()
    valid_cats = {"items", "backgrounds", "sprites"}
    target_cat = category if category in valid_cats else "items"
    cat_dir = ASSETS_DIR / target_cat
    cat_dir.mkdir(parents=True, exist_ok=True)

    if not filename:
        clean_name = re.sub(r"[^\w\-_\.]", "_", prompt.strip().split()[0]).lower()
        filename = f"{clean_name}_{int(time.time()) % 10000}.png"
    else:
        if not filename.endswith((".png", ".jpg", ".jpeg", ".webp")):
            filename += ".png"
        filename = re.sub(r"[^\w\-_\.]", "_", filename).lower()

    dest_path = cat_dir / filename
    rel_url = f"/assets/{target_cat}/{filename}"
    method_used = ""

    # Strategy 0: Sprite Fusion Pixel Art MCP if configured in .env
    if keys.get("spritefusion"):
        res_sf = spritefusion_generate_pixel_art(
            prompt=prompt,
            category=target_cat,
            filename=filename,
            auto_remove_bg=auto_remove_bg,
            link_to_room_id=link_to_room_id,
            link_to_item_id=link_to_item_id,
            link_to_hotspot_id=link_to_hotspot_id
        )
        if "error" not in res_sf:
            return res_sf

    # Strategy 1: Try Gemini API if available
    if keys.get("gemini"):
        try:
            client = genai.Client()
            resp = client.models.generate_content(
                model="gemini-2.5-flash-image",
                contents=f"Generate visual asset for adventure game: {prompt}. High quality graphic, solid plain background.",
            )
            cand = resp.candidates[0] if resp.candidates else None
            if cand and cand.content:
                for part in cand.content.parts or []:
                    if getattr(part, "inline_data", None) and part.inline_data.data:
                        pil_img = Image.open(io.BytesIO(part.inline_data.data)).convert("RGBA")
                        pil_img.save(dest_path, format="PNG")
                        method_used = "Gemini Native Image Model"
                        break
        except Exception:
            pass

    # Strategy 2: If image generation model quota reached, use SerpApi image search engine
    if not method_used and keys.get("serp"):
        res_serp = search_and_download_images(
            query=f"pixel art {prompt} transparent",
            category=target_cat,
            filename=filename,
            auto_remove_bg=auto_remove_bg,
            link_to_room_id=link_to_room_id,
            link_to_item_id=link_to_item_id,
            link_to_hotspot_id=link_to_hotspot_id
        )
        if "error" not in res_serp:
            res_serp["generator_method"] = "SerpApi Google High-Res Asset Search"
            return res_serp

    # Strategy 3: Local offline Jetson CUDA Iris model fallback if available
    if not dest_path.exists() and LOCAL_IRIS_GGUF.exists():
        res_local = jetson_generate_image(
            prompt=prompt,
            category=target_cat,
            filename=filename,
            auto_remove_bg=auto_remove_bg,
            link_to_room_id=link_to_room_id,
            link_to_item_id=link_to_item_id,
            link_to_hotspot_id=link_to_hotspot_id
        )
        if "error" not in res_local:
            return res_local

    if not dest_path.exists():
        return {"error": "Image generation and search providers both unavailable. Please verify API keys in .env or wait for local model compilation."}

    bg_removed = False
    if auto_remove_bg and target_cat in ("items", "sprites"):
        try:
            res_bg = remove_asset_background(rel_url, mode="corners", tolerance=35, trim=True)
            bg_removed = "error" not in res_bg
        except Exception:
            pass

    proj = _load_proj()
    linked = []
    if link_to_room_id:
        room = next((r for r in proj.get("rooms", []) if r.get("id") == link_to_room_id), None)
        if room:
            room["background"] = rel_url
            linked.append(f"Room '{room.get('name', link_to_room_id)}' (background)")

    if link_to_item_id:
        item = next((i for i in proj.get("items", []) if i.get("id") == link_to_item_id), None)
        if item:
            item["icon"] = rel_url
            linked.append(f"Item '{item.get('name', link_to_item_id)}' (icon)")

    if link_to_hotspot_id:
        for r in proj.get("rooms", []):
            hs = next((h for h in r.get("hotspots", []) if h.get("id") == link_to_hotspot_id), None)
            if hs:
                hs["icon"] = rel_url
                linked.append(f"Hotspot '{hs.get('name', link_to_hotspot_id)}' (icon)")
                break

    if linked:
        _save_proj(proj)

    return {
        "status": "ok",
        "file_url": rel_url,
        "method": method_used,
        "background_removed": bg_removed,
        "linked_to": linked
    }


def download_asset_from_url(
    url: str,
    category: str = "items",
    filename: str = "",
    auto_remove_bg: bool = False
) -> dict[str, Any]:
    """Directly download any image or sound asset from a URL into the game project and register it in the asset library."""
    if not url.strip():
        return {"error": "URL cannot be empty"}
    target_cat = category if category in ("items", "backgrounds", "sprites", "sounds", "music") else "items"
    cat_dir = ASSETS_DIR / target_cat
    cat_dir.mkdir(parents=True, exist_ok=True)

    if not filename:
        parsed_name = Path(urllib.parse.urlparse(url).path).name
        filename = parsed_name or f"download_{int(time.time())}"
        if "." not in filename:
            filename += ".mp3" if target_cat in ("sounds", "music") else ".png"

    dest_path = cat_dir / filename
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp, open(dest_path, "wb") as f:
            f.write(resp.read())
    except Exception as e:
        return {"error": f"Download failed: {e}"}

    rel_url = f"/assets/{target_cat}/{filename}"
    if auto_remove_bg and target_cat in ("items", "sprites"):
        try:
            remove_asset_background(rel_url, mode="corners", tolerance=35, trim=True)
        except Exception:
            pass

    return {
        "status": "ok",
        "file_url": rel_url,
        "file_path": str(dest_path),
        "size_bytes": dest_path.stat().st_size
    }


# ============================================================================
# 11. GEMINI VLM VISION INTELLIGENCE MCP TOOLS
# ============================================================================

def create_coordinate_grid_overlay(image: Image.Image, step_x: int = 64, step_y: int = 48) -> Image.Image:
    """Stamp a crisp coordinate grid overlay on an image so a VLM can accurately read pixel coordinates."""
    overlay = image.copy().convert("RGB")
    draw = ImageDraw.Draw(overlay, "RGBA")
    w, h = overlay.size

    for col, x in enumerate(range(0, w, step_x)):
        draw.line([(x, 0), (x, h)], fill=(255, 255, 255, 45), width=1)
        col_label = chr(65 + col) if col < 26 else f"A{col-26}"
        draw.text((x + 4, 4), f"{col_label}({x})", fill=(255, 230, 80, 230))

    for row, y in enumerate(range(0, h, step_y)):
        draw.line([(0, y), (w, y)], fill=(255, 255, 255, 45), width=1)
        draw.text((4, y + 4), f"R{row+1}({y})", fill=(255, 230, 80, 230))

    for x in range(step_x * 2, w, step_x * 2):
        for y in range(step_y * 2, h, step_y * 2):
            draw.text((x + 2, y + 2), f"{x},{y}", fill=(100, 240, 255, 140))

    return overlay


def vlm_auto_detect_and_place_props(room_id: str, count: int = 3, hint: str = "") -> dict[str, Any]:
    """Use Gemini VLM with a coordinate grid overlay to visually inspect a room's background image, detect background objects/props with pixel coordinates, write witty Look At & Use lines, and add them to the room."""
    proj = _load_proj()
    room = next((r for r in proj["rooms"] if r["id"] == room_id), None)
    if not room:
        return {"error": f"Room '{room_id}' not found."}
    bg_url = room.get("background", "")
    if not bg_url:
        return {"error": f"Room '{room_id}' has no background image."}

    bg_path = _resolve_asset(bg_url)
    if not bg_path.exists():
        return {"error": f"Background file not found: {bg_url}"}

    load_env()
    client = genai.Client()
    bg_img = Image.open(bg_path).convert("RGB").resize((1280, 720))
    gridded_img = create_coordinate_grid_overlay(bg_img, step_x=64, step_y=48)

    existing_names = [h.get("name", "") for h in room.get("hotspots", [])]
    prompt = f"""You are a LucasArts adventure game designer and vision model inspecting the 1280x720 background image for room "{room.get('name', room_id)}".
An explicit coordinate grid is stamped across the image with pixel X and Y coordinates. Use these grid lines and coordinate numbers to locate props with high pixel precision.
Existing hotspots already in the room: {", ".join(existing_names) or "none"}.
{f"Designer hint: {hint}" if hint else ""}

Visually identify {max(1, min(6, int(count)))} distinct, interesting props/objects visible in the room background image.
For each object, return its pixel bounding box in 1280x720 coordinates (x, y, w, h) and witty Sam & Max style "look_text" and "use_text".

Return ONLY valid JSON matching:
{{
  "props": [
    {{
      "id": "snake_case_id",
      "name": "Short Display Name",
      "x": 200,
      "y": 300,
      "w": 110,
      "h": 120,
      "look_text": "Witty 1-2 sentence LucasArts observation.",
      "use_text": "Witty 1 sentence response when used."
    }}
  ]
}}"""

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=[gridded_img, prompt],
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    res_data = json.loads(response.text)
    props_list = res_data.get("props", []) if isinstance(res_data, dict) else []

    added = []
    for p in props_list:
        hid = "".join(c for c in p.get("id", "prop") if c.isalnum() or c == "_").lower() or "prop_vlm"
        if any(h.get("id") == hid for h in room.get("hotspots", [])):
            hid = f"{hid}_{len(room.get('hotspots', [])) + 1}"
        x = max(0, min(1200, int(p.get("x", 300))))
        y = max(0, min(650, int(p.get("y", 300))))
        w = max(32, min(400, int(p.get("w", 90))))
        h = max(32, min(400, int(p.get("h", 90))))
        new_hs = {
            "id": hid,
            "name": p.get("name", hid),
            "type": "prop",
            "rect": {"x": x, "y": y, "w": w, "h": h},
            "walk_to": {"x": int(x + w // 2), "y": min(685, int(y + h + 25))},
            "look_text": p.get("look_text", "It looks interesting."),
            "use_text": p.get("use_text", ""),
            "talk_text": ""
        }
        room.setdefault("hotspots", []).append(new_hs)
        added.append(new_hs)

    _save_proj(proj)
    return {"status": "ok", "added_count": len(added), "props": added}


def vlm_generate_and_place_items(
    room_id: str,
    count: int = 3,
    generate_sprites: bool = True,
    hint: str = ""
) -> dict[str, Any]:
    """Use Gemini VLM with a coordinate grid overlay to inspect a room's physical surfaces (desks, shelves, floors), propose context-appropriate adventure game items with pixel-accurate positions, generate their pixel art sprites, and register them as inventory items and room pickup hotspots."""
    proj = _load_proj()
    room = next((r for r in proj["rooms"] if r["id"] == room_id), None)
    if not room:
        return {"error": f"Room '{room_id}' not found."}
    bg_url = room.get("background", "")
    if not bg_url:
        return {"error": f"Room '{room_id}' has no background image."}

    bg_path = _resolve_asset(bg_url)
    if not bg_path.exists():
        return {"error": f"Background file not found: {bg_url}"}

    load_env()
    client = genai.Client()
    bg_img = Image.open(bg_path).convert("RGB").resize((1280, 720))
    gridded_img = create_coordinate_grid_overlay(bg_img, step_x=64, step_y=48)

    existing_names = [h.get("name", "") for h in room.get("hotspots", [])]
    existing_items = [it.get("name", "") for it in proj.get("items", [])]

    prompt = f"""You are a master LucasArts point-and-click adventure game designer (Sam & Max / Day of the Tentacle style).
Inspect this 1280x720 background image with an explicit coordinate grid overlay for room "{room.get('name', room_id)}".

Notice the coordinate numbers stamped across the grid:
- Horizontal columns with pixel X values (e.g. 64, 128, 192, 256, 320, 384, ...)
- Vertical rows with pixel Y values (e.g. 48, 96, 144, 192, 240, 288, ...)

Existing hotspots already in the room: {", ".join(existing_names) or "none"}.
Existing inventory items: {", ".join(existing_items) or "none"}.
{f"Designer hint: {hint}" if hint else ""}

Identify {max(1, min(6, int(count)))} distinct, physical surfaces (such as a desk, a table, a shelf, the floor, the mantelpiece, or a counter) where interactive pickup items should be placed.
For each item:
1. 'name': Concise display name (e.g. 'Stale Donut', 'Rusty Skeleton Key', 'Magnifying Glass')
2. 'surface_description': What real surface in the image you are placing it on
3. 'rect': Exact pixel bounding box {{x, y, w, h}} where the item should sit based on the grid labels
4. 'walk_to': Natural pixel coordinates {{x, y}} for the character to walk up and interact with it
5. 'look_text': Witty 1-2 sentence LucasArts observation
6. 'pickup_text': Witty reaction when picked up
7. 'sprite_prompt': Visual description to generate a 16-bit pixel art sprite for this item

Return ONLY valid JSON matching:
{{
  "items": [
    {{
      "name": "Short Name",
      "surface_description": "On the wooden desk next to the lamp",
      "rect": {{"x": 200, "y": 300, "w": 48, "h": 48}},
      "walk_to": {{"x": 240, "y": 420}},
      "look_text": "Witty observation.",
      "pickup_text": "Picked up!",
      "sprite_prompt": "16-bit pixel art brass skeleton key, isolated on white background, retro adventure game sprite"
    }}
  ]
}}"""

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=[gridded_img, prompt],
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    res_data = json.loads(response.text)
    items_list = res_data.get("items", []) if isinstance(res_data, dict) else []

    items_dir = ASSETS_DIR / "items"
    items_dir.mkdir(parents=True, exist_ok=True)

    created_items = []
    for raw_item in items_list:
        name = raw_item.get("name", "Mystery Item")
        clean_id = re.sub(r"[^a-zA-Z0-9_]", "", name.lower().replace(" ", "_")) or "item_vlm"
        base_id = clean_id
        suffix = 1
        while any(it.get("id") == clean_id for it in proj.get("items", [])):
            clean_id = f"{base_id}_{suffix}"
            suffix += 1

        r = raw_item.get("rect", {})
        x = max(0, min(1200, int(r.get("x", 200))))
        y = max(0, min(650, int(r.get("y", 200))))
        w = max(24, min(256, int(r.get("w", 48))))
        h = max(24, min(256, int(r.get("h", 48))))

        wto = raw_item.get("walk_to", {})
        walk_x = max(0, min(1279, int(wto.get("x", x + w // 2))))
        walk_y = max(0, min(719, int(wto.get("y", min(685, y + h + 25)))))

        icon_rel_path = f"/assets/items/{clean_id}.png"
        icon_file_path = items_dir / f"{clean_id}.png"

        if generate_sprites:
            sprite_prompt = raw_item.get("sprite_prompt", f"16-bit pixel art {name}, isolated on white background")
            try:
                gen_res = jetson_generate_image(
                    prompt=f"{sprite_prompt}, pixel art, 16-bit",
                    negative_prompt="blurry, photorealistic, 3d, smooth",
                    steps=15,
                    width=256,
                    height=256,
                    remove_background=True
                )
                if "asset_url" in gen_res:
                    src_p = _resolve_asset(gen_res["asset_url"])
                    if src_p.exists():
                        shutil.copy2(src_p, icon_file_path)
                        pixelize_asset(icon_rel_path, target_resolution=32, max_colors=16)
            except Exception as e:
                print(f"[VLM Grid Placer] Sprite gen error for {clean_id}: {e}")

        # Fallback badge if no sprite generated
        if not icon_file_path.exists():
            ph = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
            dph = ImageDraw.Draw(ph)
            dph.rounded_rectangle([4, 4, 44, 44], radius=8, fill=(180, 120, 40, 230), outline=(255, 230, 80, 255), width=2)
            dph.text((12, 16), name[:3].upper(), fill=(255, 255, 255))
            ph.save(icon_file_path)

        # 1. Register inventory item in project.json
        item_entry = {
            "id": clean_id,
            "name": name,
            "description": raw_item.get("look_text", "An intriguing object."),
            "icon": icon_rel_path
        }
        proj.setdefault("items", []).append(item_entry)

        # 2. Register room pickup hotspot
        hotspot_id = f"pickup_{clean_id}"
        hs_entry = {
            "id": hotspot_id,
            "name": name,
            "type": "pickup",
            "rect": {"x": x, "y": y, "w": w, "h": h},
            "walk_to": {"x": walk_x, "y": walk_y},
            "look_text": raw_item.get("look_text", f"It's {name}."),
            "use_text": "",
            "talk_text": "",
            "item_id": clean_id,
            "icon": icon_rel_path,
            "pickup_text": raw_item.get("pickup_text", f"Picked up {name}!")
        }
        room.setdefault("hotspots", []).append(hs_entry)
        created_items.append({
            "item": item_entry,
            "hotspot": hs_entry,
            "surface": raw_item.get("surface_description", "")
        })

    _save_proj(proj)
    return {
        "status": "ok",
        "room_id": room_id,
        "created_count": len(created_items),
        "items": created_items
    }


def vlm_describe_hotspot(room_id: str, hotspot_id: str) -> dict[str, Any]:
    """Use Gemini VLM to visually inspect a specific hotspot's bounding box on the room background (and/or its icon) and auto-fill its name, look_text, and use_text."""
    proj = _load_proj()
    room = next((r for r in proj["rooms"] if r["id"] == room_id), None)
    if not room:
        return {"error": f"Room '{room_id}' not found."}
    hs = next((h for h in room.get("hotspots", []) if h.get("id") == hotspot_id), None)
    if not hs:
        return {"error": f"Hotspot '{hotspot_id}' not found in room '{room_id}'."}

    load_env()
    client = genai.Client()
    contents: list[Any] = []

    if hs.get("icon"):
        try:
            p = _resolve_asset(hs["icon"])
            if p.exists():
                contents.append(Image.open(p).convert("RGB"))
        except Exception:
            pass

    if room.get("background"):
        try:
            bg_path = _resolve_asset(room["background"])
            if bg_path.exists():
                bg_img = Image.open(bg_path).convert("RGB").resize((1280, 720))
                r = hs.get("rect") or {"x": 100, "y": 100, "w": 100, "h": 100}
                rx, ry, rw, rh = int(r["x"]), int(r["y"]), int(r["w"]), int(r["h"])
                crop = bg_img.crop((max(0, rx - 15), max(0, ry - 15), min(1280, rx + rw + 15), min(720, ry + rh + 15)))
                contents.append(crop)
                ov = bg_img.copy()
                ImageDraw.Draw(ov).rectangle([rx, ry, rx + rw, ry + rh], outline=(255, 40, 40), width=4)
                contents.append(ov)
        except Exception:
            pass

    prompt = f"""You are a classic LucasArts adventure writer. Inspect the highlighted object "{hs.get('name', hotspot_id)}" in room "{room.get('name', room_id)}".
Return JSON with:
{{
  "suggested_name": "2-4 word object name",
  "look_text": "Witty 1-2 sentence Look At line",
  "use_text": "Short 1 sentence Use line"
}}"""
    contents.append(prompt)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    data = json.loads(response.text)
    if isinstance(data, list) and data:
        data = data[0]
    if data.get("suggested_name"):
        hs["name"] = data["suggested_name"]
    if data.get("look_text"):
        hs["look_text"] = data["look_text"]
    if data.get("use_text"):
        hs["use_text"] = data["use_text"]
    _save_proj(proj)
    return {"status": "ok", "hotspot": hs}


def vlm_inspect_room_scene(room_id: str, query_question: str) -> dict[str, Any]:
    """Ask Gemini VLM any question about a room's background image (e.g. 'What clues or exits would fit here?', 'Describe the aesthetic and tone')."""
    proj = _load_proj()
    room = next((r for r in proj["rooms"] if r["id"] == room_id), None)
    if not room:
        return {"error": f"Room '{room_id}' not found."}
    bg_url = room.get("background", "")
    if not bg_url:
        return {"error": f"Room '{room_id}' has no background image."}
    bg_path = _resolve_asset(bg_url)
    if not bg_path.exists():
        return {"error": f"Background file not found: {bg_url}"}

    load_env()
    client = genai.Client()
    bg_img = Image.open(bg_path).convert("RGB").resize((1280, 720))

    prompt = f"""You are a veteran adventure game vision architect analyzing the background scene of room "{room.get('name', room_id)}".
User question: {query_question}
Provide a detailed, highly observant game-design assessment."""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[bg_img, prompt]
    )
    return {"room_id": room_id, "analysis": response.text}


# ============================================================================
# MASTER MCP & AGENT TOOL REGISTRY (ALL FUNCTIONS)
# ============================================================================

TOOLS_LIST = [
    # 1. Project & Engine
    get_project_summary,
    get_full_project,
    set_project_title,
    set_character_roles,
    launch_pygame_game,
    stop_pygame_game,

    # 2. Rooms & World Map
    list_rooms,
    get_room,
    create_or_update_room,
    delete_room,
    update_room_map_position,
    set_room_walkable_polygon,
    set_start_room,

    # 3. Hotspots, Props, NPCs & Doors
    list_hotspots,
    get_hotspot,
    create_or_update_hotspot,
    delete_hotspot,
    link_door,
    set_hotspot_lock,

    # 4. Items & Inventory
    list_items,
    get_item,
    create_or_update_item,
    delete_item,
    link_item_usage,

    # 5. Puzzles & Rules
    list_puzzles,
    get_puzzle,
    create_or_update_puzzle,
    delete_puzzle,

    # 6. Branching Dialog Trees
    list_dialog_trees,
    get_dialog_tree,
    create_or_update_dialog_tree,
    delete_dialog_tree,
    add_or_update_dialog_node,
    delete_dialog_node,
    add_dialog_player_choice,
    delete_dialog_player_choice,
    ai_generate_dialog_tree,

    # 7. Cutscenes & Cinematics Timeline
    list_cutscenes,
    get_cutscene,
    create_or_update_cutscene,
    delete_cutscene,
    add_cutscene_step,
    delete_cutscene_step,
    ai_generate_cutscene,

    # 8. Sprites & Animation Studio
    list_sprites,
    get_sprite,
    add_or_update_sprite_animation,
    delete_sprite_animation,
    assign_sprite_direction_role,
    set_sprite_scale,

    # 9. Asset Library & Background Remover
    list_assets,
    remove_asset_background,
    restore_asset_original,
    delete_asset_file,
    pixelize_asset,

    # 10. AI Media Generation, Search & Sound Effects (.env Powered)
    list_available_media_apis,
    search_and_download_images,
    search_and_download_sound_effects,
    generate_image_ai,
    jetson_generate_image,
    spritefusion_generate_pixel_art,
    spritefusion_get_credits,
    spritefusion_list_saved_assets,
    download_asset_from_url,

    # 11. Gemini VLM Vision
    vlm_auto_detect_and_place_props,
    vlm_generate_and_place_items,
    vlm_describe_hotspot,
    vlm_inspect_room_scene,
]

TOOLS_BY_NAME = {fn.__name__: fn for fn in TOOLS_LIST}


# ============================================================================
# AGENT INTERACTION LOOP (NVIDIA NIM PRIMARY + GEMINI FALLBACK)
# ============================================================================

def _coerce_tool_args(fn, raw_args: dict[str, Any]) -> dict[str, Any]:
    """Coerce string arguments from LLM function calls into typed integers, floats, or booleans based on function signature."""
    if not callable(fn) or not isinstance(raw_args, dict):
        return raw_args or {}
    try:
        sig = inspect.signature(fn)
    except Exception:
        return raw_args

    coerced = {}
    for name, val in raw_args.items():
        if name not in sig.parameters:
            coerced[name] = val
            continue
        param = sig.parameters[name]
        ann = param.annotation
        if ann == int and isinstance(val, (str, float)):
            try:
                coerced[name] = int(val)
                continue
            except Exception:
                pass
        elif ann == float and isinstance(val, (str, int)):
            try:
                coerced[name] = float(val)
                continue
            except Exception:
                pass
        elif ann == bool and isinstance(val, str):
            coerced[name] = val.lower() in ("true", "1", "yes")
            continue
        coerced[name] = val
    return coerced


def function_to_openai_tool(fn) -> dict[str, Any]:
    """Convert a Python function into an OpenAI-compatible function calling tool schema."""
    doc = (fn.__doc__ or "").strip()
    sig = inspect.signature(fn)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for param_name, param in sig.parameters.items():
        param_type = "string"
        if param.annotation == int:
            param_type = "integer"
        elif param.annotation == float:
            param_type = "number"
        elif param.annotation == bool:
            param_type = "boolean"
        elif getattr(param.annotation, "__origin__", None) == list or param.annotation == list:
            param_type = "array"
        elif getattr(param.annotation, "__origin__", None) == dict or param.annotation == dict:
            param_type = "object"

        properties[param_name] = {"type": param_type}
        if param.default == inspect.Parameter.empty:
            required.append(param_name)

    return {
        "type": "function",
        "function": {
            "name": fn.__name__,
            "description": doc,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }
    }


def _run_nvidia_agent(
    user_message: str,
    current_room_id: str = "",
    include_room_vision: bool = True,
    history: list[dict[str, Any]] | None = None,
    model_name: str = "meta/llama-3.2-11b-vision-instruct"
) -> dict[str, Any]:
    """Run autonomous MCP agent powered by NVIDIA NIM (multimodal vision + 63 tool calling)."""
    keys = _get_api_keys()
    nv_key = keys.get("nvidia")
    if not nv_key:
        raise ValueError("NVIDIA_API_KEY not configured in .env")

    proj = _load_proj()
    openai_tools = [function_to_openai_tool(fn) for fn in TOOLS_LIST]

    summary_str = json.dumps(get_project_summary(), indent=2)
    system_instruction = f"""You are the AdventureForge AI Co-Creator & MCP Game Engine Architect, powered by NVIDIA NIM ({model_name}).
You have direct tool-calling access to inspect and modify data/project.json and /assets/*.
You have {len(TOOLS_LIST)} tools available. Call appropriate tools to fulfill the user's request.
Project Summary:
{summary_str}

Guidelines:
1. Always call the appropriate tool(s) to execute the user's intent. You can call multiple tools!
2. When the user asks for sound effects, audio, or music, use `search_and_download_sound_effects` with Freesound.
3. When the user asks for pixel art sprites, icons, props, or background images, use `jetson_generate_image` (NVIDIA Jetson GPU local Sakura-Iris-3B diffusion model), `spritefusion_generate_pixel_art`, `generate_image_ai`, or `search_and_download_images`. If the user asks for local/offline generation, prioritize `jetson_generate_image`.
4. When creating items that should appear in the world, use `create_or_update_item` with `place_in_room`.
5. When wiring items to doors, use `link_item_usage`.
6. Keep final responses clear, concise, and report what tools were called and what assets were created."""

    # Room Visual Inspection via NVIDIA Vision Encoder
    room_visual_summary = ""
    if include_room_vision and current_room_id:
        room = next((r for r in proj.get("rooms", []) if r.get("id") == current_room_id), None)
        if room and room.get("background"):
            bg_path = _resolve_asset(room["background"])
            if bg_path.exists():
                try:
                    with Image.open(bg_path).convert("RGB") as im:
                        im.thumbnail((800, 450))
                        buf = io.BytesIO()
                        im.save(buf, format="JPEG", quality=80)
                        b64_img = base64.b64encode(buf.getvalue()).decode("utf-8")
                        v_payload = {
                            "model": model_name,
                            "messages": [{
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": "<|image|>\nDescribe the key objects, scenery, doors, and visual style of this adventure game room scene in 2-3 sentences."},
                                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                                ]
                            }],
                            "max_tokens": 120,
                            "temperature": 0.2
                        }
                        v_req = urllib.request.Request(
                            "https://integrate.api.nvidia.com/v1/chat/completions",
                            data=json.dumps(v_payload).encode("utf-8"),
                            headers={"Authorization": f"Bearer {nv_key}", "Content-Type": "application/json"}
                        )
                        with urllib.request.urlopen(v_req, timeout=12) as v_resp:
                            v_data = json.loads(v_resp.read().decode("utf-8"))
                            room_visual_summary = v_data["choices"][0]["message"]["content"].strip()
                except Exception:
                    pass

    if room_visual_summary:
        system_instruction += f"\n\nVisual Inspection of Active Room ('{current_room_id}'):\n{room_visual_summary}"

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_instruction}
    ]

    # Add conversation history
    if history:
        for h in history[-4:]:
            r = "user" if h.get("role") == "user" else "assistant"
            messages.append({"role": r, "content": h.get("text", "")})

    user_text = f"[Active Room in Editor: '{current_room_id}']\n{user_message}" if current_room_id else user_message
    messages.append({"role": "user", "content": user_text})

    tool_logs: list[dict[str, Any]] = []
    final_text = ""

    for _turn in range(8):
        req_payload = {
            "model": model_name,
            "messages": messages,
            "tools": openai_tools,
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "temperature": 0.1
        }
        req_bytes = json.dumps(req_payload).encode("utf-8")
        nv_req = urllib.request.Request(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            data=req_bytes,
            headers={
                "Authorization": f"Bearer {nv_key}",
                "Content-Type": "application/json"
            }
        )
        try:
            with urllib.request.urlopen(nv_req, timeout=35) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as http_err:
            body = http_err.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"NVIDIA API Error {http_err.code}: {body}")

        msg = data["choices"][0]["message"]
        tcalls = msg.get("tool_calls") or []

        if not tcalls:
            content_text = (msg.get("content") or "").strip()
            # Handle text-formatted JSON tool calls from LLaMA 3.2
            if content_text.startswith("{") and ("name" in content_text or "function" in content_text):
                try:
                    cleaned_json = re.sub(r":\s*True\b", ": true", re.sub(r":\s*False\b", ": false", content_text))
                    obj = json.loads(cleaned_json)
                    fn_name = obj.get("name") or obj.get("function")
                    if isinstance(obj, dict) and fn_name in TOOLS_BY_NAME:
                        args_dict = obj.get("parameters") or obj.get("arguments") or obj.get("args") or {}
                        tcalls = [{
                            "id": f"call_inline_{int(time.time()*1000)}",
                            "type": "function",
                            "function": {
                                "name": fn_name,
                                "arguments": json.dumps(args_dict)
                            }
                        }]
                except Exception:
                    pass

            if not tcalls:
                final_text = content_text or "Done!"
                break

        # NVIDIA NIM enforces single tool-call per message
        tc = tcalls[0]
        fname = tc["function"]["name"]
        raw_args = tc["function"].get("arguments") or "{}"
        try:
            fargs = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except Exception:
            fargs = {}

        fn = TOOLS_BY_NAME.get(fname)
        if fn:
            coerced_args = _coerce_tool_args(fn, fargs)
            try:
                fres = fn(**coerced_args)
            except Exception as e:
                fres = {"error": str(e)}
        else:
            fres = {"error": f"Tool '{fname}' not found"}

        tool_logs.append({
            "tool": fname,
            "args": coerced_args if fn else fargs,
            "result": fres
        })

        messages.append({
            "role": "assistant",
            "content": msg.get("content") or None,
            "tool_calls": [tc]
        })
        messages.append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": json.dumps(fres)
        })

    if not final_text:
        final_text = "Completed the requested actions!"

    return {
        "reply": final_text,
        "tool_calls": tool_logs,
        "project": _load_proj(),
        "model_used": f"NVIDIA NIM ({model_name})"
    }


def _run_gemini_agent(
    user_message: str,
    current_room_id: str = "",
    include_room_vision: bool = True,
    history: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Run a multi-step Gemini LLM/VLM Agent with full MCP tool-calling access to AdventureForge."""
    client = genai.Client()
    proj = _load_proj()

    system_instruction = f"""You are the AdventureForge AI Co-Creator & MCP Game Engine Architect (LLM + VLM).
You have direct tool-calling access to inspect and modify the entire point-and-click adventure game project (`data/project.json` and `/assets/*`).
You have {len(TOOLS_LIST)} comprehensive tools covering:
- Project titles, character sprite roles, and launching/stopping the Pygame runtime
- World Map screen nodes, positions, walkable floor polygons, and start room
- Hotspot props, pickups, NPCs, doors, and door locks
- Inventory items and puzzle interaction rules
- Branching Dialog Trees (nodes, speaker lines, player choices, conditions)
- Cutscenes (timeline steps: walk, say, fade, wait, change_room, give_item, set_flag, start_dialog)
- Sprite Studio animations (frames, fps, walk/up/down/idle role mappings, scale)
- Asset Library & Background removal (corner flood fill, global key, auto-trim, and original file restore)
- AI Media Generation, Sound Effects & Search (.env API keys):
  * `search_and_download_sound_effects`: Search and download sound effects and ambient music from FreeSound.org via FREESOUND_API_KEY
  * `search_and_download_images`: Search and download Google Images via SERP_API_KEY with auto-transparency
  * `generate_image_ai`: Generate or acquire game asset graphics with auto background removal and entity linking
  * `spritefusion_generate_pixel_art`: Generate authentic 16/32/64px pixel art using the Sprite Fusion MCP Server (https://www.spritefusion.com/mcp) via SPRITE_FUSION_API_KEY
  * `download_asset_from_url`: Download any web media asset directly into the game project
  * `list_available_media_apis`: Inspect available media generation and search API keys
- Gemini VLM visual inspection (detecting props from room background, Look At/Use lines, room scene inspection)

Guidelines:
1. Always call the appropriate tool(s) to execute the user's intent. You can call multiple tools in sequence!
2. When the user asks for sound effects, audio, or music, use `search_and_download_sound_effects` with Freesound.
3. When the user asks for item icons, props, or background images, use `generate_image_ai` or `search_and_download_images` with SerpApi and auto background removal.
4. When creating items that should appear in the world, use `create_or_update_item` with `place_in_room`.
5. When wiring items to doors, use `link_item_usage`.
6. Keep final responses clear, concise, and report what tools and assets were created."""

    contents: list[Any] = []
    summary_str = json.dumps(get_project_summary(), indent=2)
    context_header = f"Current Active Room in Editor: {current_room_id or proj.get('start_room', 'reception')}\nProject State Summary:\n{summary_str}"
    contents.append(context_header)

    if include_room_vision and current_room_id:
        room = next((r for r in proj.get("rooms", []) if r.get("id") == current_room_id), None)
        if room and room.get("background"):
            try:
                bg_path = _resolve_asset(room["background"])
                if bg_path.exists():
                    bg_img = Image.open(bg_path).convert("RGB").resize((1280, 720))
                    contents.append(bg_img)
            except Exception:
                pass

    if history:
        for h in history[-6:]:
            role_label = "User" if h.get("role") == "user" else "Assistant"
            contents.append(f"{role_label}: {h.get('text', '')}")

    contents.append(f"User Request: {user_message}")

    tool_logs: list[dict[str, Any]] = []
    chat_contents = list(contents)
    final_text = ""

    try:
        for _step in range(10):
            response = None
            last_err = None
            for model_candidate in ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"):
                try:
                    response = client.models.generate_content(
                        model=model_candidate,
                        contents=chat_contents,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            tools=TOOLS_LIST,
                            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                            temperature=0.2,
                        )
                    )
                    if response:
                        break
                except Exception as model_err:
                    last_err = model_err
                    err_str = str(model_err)
                    if "503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str:
                        continue
                    raise

            if not response:
                if last_err:
                    raise last_err
                break

            cand = response.candidates[0] if response.candidates else None
            if not cand or not cand.content:
                break

            chat_contents.append(cand.content)

            fn_calls = [p.function_call for p in (cand.content.parts or []) if p.function_call]
            if not fn_calls:
                text_parts = [p.text for p in (cand.content.parts or []) if getattr(p, "text", None)]
                final_text = "\n".join(text_parts).strip() or getattr(response, "text", "") or "Done!"
                break

            fn_response_parts = []
            for fc in fn_calls:
                fn_name = fc.name
                fn_args = dict(fc.args) if fc.args else {}
                fn_obj = TOOLS_BY_NAME.get(fn_name)
                if fn_obj:
                    coerced_args = _coerce_tool_args(fn_obj, fn_args)
                    try:
                        res = fn_obj(**coerced_args)
                    except Exception as e:
                        res = {"error": str(e)}
                else:
                    res = {"error": f"Unknown tool: {fn_name}"}

                tool_logs.append({
                    "tool": fn_name,
                    "args": coerced_args if fn_obj else fn_args,
                    "result": res
                })
                fn_response_parts.append(
                    types.Part.from_function_response(
                        name=fn_name,
                        response={"result": res}
                    )
                )

            chat_contents.append(types.Content(role="tool", parts=fn_response_parts))
    except Exception as e:
        return {
            "reply": f"Agent notification: {e}",
            "tool_calls": tool_logs,
            "project": _load_proj()
        }

    if not final_text:
        final_text = "Completed the requested actions!"

    return {
        "reply": final_text,
        "tool_calls": tool_logs,
        "project": _load_proj(),
        "model_used": "Gemini (gemini-2.5-flash)"
    }


def run_agent_instruction(
    user_message: str,
    current_room_id: str = "",
    include_room_vision: bool = True,
    history: list[dict[str, Any]] | None = None,
    preferred_model: str = ""
) -> dict[str, Any]:
    """Run autonomous AI Agent with full MCP tool-calling access to AdventureForge.
    Prioritizes NVIDIA NIM models (meta/llama-3.2-11b-vision-instruct / meta/llama-3.2-90b-vision-instruct)
    when NVIDIA_API_KEY is configured in .env."""
    load_env()
    keys = _get_api_keys()

    nv_key = keys.get("nvidia")
    # If NVIDIA API key is available and Gemini is not specifically forced
    if nv_key and ("gemini" not in preferred_model.lower()):
        nv_model = preferred_model if ("llama" in preferred_model or "nvidia" in preferred_model) else os.getenv("NVIDIA_MODEL", "meta/llama-3.2-11b-vision-instruct")
        try:
            return _run_nvidia_agent(
                user_message=user_message,
                current_room_id=current_room_id,
                include_room_vision=include_room_vision,
                history=history,
                model_name=nv_model
            )
        except Exception as nv_err:
            print(f"NVIDIA Agent error, attempting fallback: {nv_err}")
            if not keys.get("gemini"):
                return {
                    "reply": f"NVIDIA Agent error: {nv_err}",
                    "tool_calls": [],
                    "project": _load_proj()
                }

    # Fallback / Gemini Agent
    return _run_gemini_agent(
        user_message=user_message,
        current_room_id=current_room_id,
        include_room_vision=include_room_vision,
        history=history
    )

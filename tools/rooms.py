"""
AdventureForge — Rooms & World Map MCP Tools
"""
from typing import Any
from config import config
from agent_tools import (
    _load_proj,
    _save_proj,
)


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


import json
"""
AdventureForge — Rooms & World Map MCP Tools
"""
import json
from typing import Any
from engine_geometry import normalize_collider
from ._core import (
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


# ============================================================================
# COLLISION GEOMETRY
#
# Colliders are the *negative* space of a room: walls, furniture and other
# things the characters must not walk through. The room's walkable polygon
# says where they *may* go; colliders carve obstacles out of that area.
# ============================================================================

def _clean_collider_id(raw: str, taken: set[str]) -> str:
    """Build a unique, safe collider id."""
    base = "".join(ch for ch in str(raw or "").lower() if ch.isalnum() or ch == "_")
    base = base or "collider"
    candidate = base
    n = 2
    while candidate in taken:
        candidate = f"{base}_{n}"
        n += 1
    return candidate


def list_room_colliders(room_id: str) -> dict[str, Any]:
    """List the collision shapes (walls, furniture, blocked space) in a room."""
    proj = _load_proj()
    room = next((r for r in proj.get("rooms", []) if r.get("id") == room_id), None)
    if not room:
        return {"error": f"Room '{room_id}' not found."}
    colliders = room.get("colliders") or []
    return {
        "room_id": room_id,
        "count": len(colliders),
        "colliders": colliders,
    }


def add_room_collider(
    room_id: str,
    collider_type: str = "rect",
    x: int = 0,
    y: int = 0,
    w: int = 100,
    h: int = 100,
    points_json: str = "",
    collider_id: str = "",
) -> dict[str, Any]:
    """Add a blocked area (wall, furniture, obstacle) to a room.

    Use collider_type 'rect' with x/y/w/h for a box, or 'poly' with
    points_json (a JSON array of {"x":..,"y":..} points) for an arbitrary
    shape. Characters slide along colliders instead of stopping dead.
    """
    proj = _load_proj()
    room = next((r for r in proj.get("rooms", []) if r.get("id") == room_id), None)
    if not room:
        return {"error": f"Room '{room_id}' not found."}

    colliders = room.get("colliders") or []
    taken = {str(c.get("id") or "") for c in colliders}

    if collider_type == "poly":
        try:
            points = json.loads(points_json) if points_json else []
        except Exception as e:
            return {"error": f"Invalid points_json: {e}"}
        if not isinstance(points, list):
            return {"error": "points_json must be a JSON array of points."}
        candidate = {
            "id": _clean_collider_id(collider_id or f"poly_{len(colliders) + 1}", taken),
            "type": "poly",
            "points": [{"x": int(p.get("x", 0)), "y": int(p.get("y", 0))} for p in points],
        }
    else:
        candidate = {
            "id": _clean_collider_id(collider_id or f"collider_{len(colliders) + 1}", taken),
            "type": "rect",
            "x": int(x),
            "y": int(y),
            "w": max(1, int(w)),
            "h": max(1, int(h)),
        }

    try:
        candidate = normalize_collider(candidate)
    except ValueError as e:
        return {"error": str(e)}

    colliders.append(candidate)
    room["colliders"] = colliders
    _save_proj(proj)
    return {"status": "ok", "room_id": room_id, "collider": candidate, "count": len(colliders)}


def set_room_colliders(room_id: str, colliders_json: str) -> dict[str, Any]:
    """Replace every collision shape in a room with the supplied list.

    colliders_json is a JSON array of objects, each either
    {"type":"rect","x":..,"y":..,"w":..,"h":..} or
    {"type":"poly","points":[{"x":..,"y":..}, ...]}.
    """
    proj = _load_proj()
    room = next((r for r in proj.get("rooms", []) if r.get("id") == room_id), None)
    if not room:
        return {"error": f"Room '{room_id}' not found."}

    try:
        raw = json.loads(colliders_json)
    except Exception as e:
        return {"error": f"Invalid colliders_json: {e}"}
    if not isinstance(raw, list):
        return {"error": "colliders_json must be a JSON array of collider objects."}

    taken: set[str] = set()
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            return {"error": f"Collider #{idx + 1} is not an object."}
        item = dict(item)
        item.setdefault("id", f"collider_{idx + 1}")
        item["id"] = _clean_collider_id(item.get("id", ""), taken)
        try:
            norm = normalize_collider(item)
        except ValueError as e:
            return {"error": f"Collider #{idx + 1}: {e}"}
        taken.add(norm["id"])
        out.append(norm)

    room["colliders"] = out
    _save_proj(proj)
    return {"status": "ok", "room_id": room_id, "count": len(out), "colliders": out}


def clear_room_colliders(room_id: str) -> dict[str, Any]:
    """Remove every collision shape from a room, making the whole floor walkable."""
    proj = _load_proj()
    room = next((r for r in proj.get("rooms", []) if r.get("id") == room_id), None)
    if not room:
        return {"error": f"Room '{room_id}' not found."}
    removed = len(room.get("colliders") or [])
    room["colliders"] = []
    _save_proj(proj)
    return {"status": "ok", "room_id": room_id, "removed": removed}

"""
AdventureForge — Room Hotspots, Props, NPCs & Doors MCP Tools
"""
from typing import Any
from ._core import (
    _load_proj,
    _save_proj,
)


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
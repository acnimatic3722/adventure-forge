"""
AdventureForge — Items & Inventory MCP Tools
"""
from typing import Any
from config import config
from agent_tools import (
    _load_proj,
    _save_proj,
    _resolve_asset,
)


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
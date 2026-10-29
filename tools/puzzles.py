"""
AdventureForge — Puzzles & Rules MCP Tools
"""
from typing import Any
from config import config
from agent_tools import (
    _load_proj,
    _save_proj,
)


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
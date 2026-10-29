"""
AdventureForge — Cutscenes & Cinematics Timeline MCP Tools
"""
import json
from typing import Any
from config import config
from agent_tools import (
    _load_proj,
    _save_proj,
    load_env,
)
from google import genai
from google.genai import types


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
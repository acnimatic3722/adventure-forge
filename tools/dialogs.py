"""
AdventureForge — Branching Dialog Trees MCP Tools
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
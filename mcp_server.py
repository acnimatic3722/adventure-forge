#!/usr/bin/env python3
"""
AdventureForge — Model Context Protocol (MCP) Server
Exposes AdventureForge's 57 game editor & VLM tools, resources, and prompt templates over standard MCP (stdio).

Usage in any MCP client config (e.g. mcp_config.json):
{
  "mcpServers": {
    "adventure-forge": {
      "command": "python3",
      "args": ["/home/x/Desktop/IDEAS/adventure_forge/mcp_server.py"]
    }
  }
}
"""

import sys
import json
import inspect
import typing
from pathlib import Path
from typing import Any

# Ensure directory is on sys.path so imports work regardless of cwd
SERVER_DIR = Path(__file__).resolve().parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from config import config
from tools import TOOLS_LIST, TOOLS_BY_NAME
from agent_tools import _load_proj


def _build_json_schema(fn) -> dict[str, Any]:
    """Generates an OpenAPI/JSON-Schema compliant dictionary for a Python function."""
    sig = inspect.signature(fn)
    props = {}
    required = []
    
    for name, param in sig.parameters.items():
        ann = param.annotation
        origin = typing.get_origin(ann)
        
        # Check union / optional
        if origin is typing.Union:
            args = [a for a in typing.get_args(ann) if a is not type(None)]
            if args:
                ann = args[0]
                origin = typing.get_origin(ann)
        
        ptype = "string"
        if ann is int:
            ptype = "integer"
        elif ann is float:
            ptype = "number"
        elif ann is bool:
            ptype = "boolean"
        elif ann is list or origin is list:
            ptype = "array"
        elif ann is dict or origin is dict:
            ptype = "object"
            
        desc = f"Parameter {name}"
        if param.default is not inspect.Parameter.empty and param.default is not None:
            desc += f" (default: {param.default})"
            
        props[name] = {"type": ptype, "description": desc}
        if param.default is inspect.Parameter.empty:
            required.append(name)
            
    return {
        "type": "object",
        "properties": props,
        "required": required
    }


def _get_resources() -> list[dict[str, Any]]:
    return [
        {
            "uri": "adventureforge://project",
            "name": "AdventureForge Project Manifest",
            "description": "Full project JSON containing rooms, items, puzzles, dialogs, cutscenes, and settings.",
            "mimeType": "application/json"
        },
        {
            "uri": "adventureforge://rooms",
            "name": "AdventureForge Rooms & Hotspots",
            "description": "Overview of all rooms, background assets, and configured hotspots.",
            "mimeType": "application/json"
        },
        {
            "uri": "adventureforge://items",
            "name": "AdventureForge Inventory Items",
            "description": "List of all inventory items, descriptions, and their target usage links.",
            "mimeType": "application/json"
        },
        {
            "uri": "adventureforge://puzzles",
            "name": "AdventureForge Puzzle Dependency Graph",
            "description": "Inventory puzzles, requirements, actions, and unlock states.",
            "mimeType": "application/json"
        },
        {
            "uri": "adventureforge://dialogs",
            "name": "AdventureForge Dialog Trees",
            "description": "Branching dialog trees and NPC conversation nodes.",
            "mimeType": "application/json"
        },
        {
            "uri": "adventureforge://cutscenes",
            "name": "AdventureForge Cinematic Cutscenes",
            "description": "Timeline sequences and cinematic steps.",
            "mimeType": "application/json"
        }
    ]


def _read_resource(uri: str) -> dict[str, Any]:
    proj = _load_proj()
    if uri == "adventureforge://project":
        content = json.dumps(proj, indent=2)
    elif uri == "adventureforge://rooms":
        content = json.dumps(proj.get("rooms", {}), indent=2)
    elif uri == "adventureforge://items":
        content = json.dumps(proj.get("items", {}), indent=2)
    elif uri == "adventureforge://puzzles":
        content = json.dumps(proj.get("puzzles", {}), indent=2)
    elif uri == "adventureforge://dialogs":
        content = json.dumps(proj.get("dialogs", {}), indent=2)
    elif uri == "adventureforge://cutscenes":
        content = json.dumps(proj.get("cutscenes", {}), indent=2)
    else:
        raise ValueError(f"Unknown resource URI: {uri}")
    return {
        "contents": [
            {
                "uri": uri,
                "mimeType": "application/json",
                "text": content
            }
        ]
    }


def _get_prompts() -> list[dict[str, Any]]:
    return [
        {
            "name": "create_adventure_scene",
            "description": "Template to construct an adventure room with background, interactive hotspots, examine text, and linked doors.",
            "arguments": [
                {"name": "theme", "description": "Visual theme (e.g. Cyberpunk Alley, Victorian Mansion, Pirate Ship)", "required": True},
                {"name": "room_name", "description": "Display name of the room", "required": True}
            ]
        },
        {
            "name": "design_multi_step_puzzle",
            "description": "Template to architect a classic point-and-click inventory puzzle chain with keys, clues, and environmental locks.",
            "arguments": [
                {"name": "objective", "description": "Goal of the puzzle (e.g. Unlock the secret basement laboratory)", "required": True}
            ]
        },
        {
            "name": "write_branching_dialog",
            "description": "Template to author interactive multi-choice NPC dialog with conditions and quest rewards.",
            "arguments": [
                {"name": "npc_name", "description": "Name and personality of the NPC", "required": True},
                {"name": "topic", "description": "Conversation topic or quest context", "required": True}
            ]
        }
    ]


def _get_prompt(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "create_adventure_scene":
        theme = args.get("theme", "Fantasy Tavern")
        room_name = args.get("room_name", "Main Hall")
        msg = f"You are an adventure game designer. Use AdventureForge MCP tools to create room '{room_name}' with theme '{theme}'. List rooms first, create the room, add 3-4 interactive hotspots (examine, pick up, use), and link exit doors."
    elif name == "design_multi_step_puzzle":
        objective = args.get("objective", "Open the vault")
        msg = f"Architect a 3-step adventure puzzle to '{objective}'. Use list_items, create_or_update_item, link_item_usage, and create_or_update_puzzle to define items, targets, and conditions."
    elif name == "write_branching_dialog":
        npc_name = args.get("npc_name", "Mysterious Merchant")
        topic = args.get("topic", "Selling rare artifacts")
        msg = f"Create a full branching dialog tree for '{npc_name}' discussing '{topic}'. Use create_or_update_dialog_tree, add_or_update_dialog_node, and add_dialog_player_choice to build a 3-tier conversation with multiple player branches."
    else:
        msg = f"AdventureForge prompt: {name}"
    return {
        "messages": [
            {
                "role": "user",
                "content": {"type": "text", "text": msg}
            }
        ]
    }


def run_stdio_mcp_server():
    """Standard JSON-RPC 2.0 MCP Server over stdin/stdout."""
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue

        msg_id = msg.get("id")
        method = msg.get("method", "")
        params = msg.get("params") or {}

        # 1. Initialize
        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {},
                        "resources": {},
                        "prompts": {}
                    },
                    "serverInfo": {
                        "name": "adventure-forge-mcp",
                        "version": "1.0.0"
                    }
                }
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        elif method == "ping":
            resp = {"jsonrpc": "2.0", "id": msg_id, "result": {}}
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        # 2. Tools
        elif method == "tools/list":
            tools_meta = []
            for fn in TOOLS_LIST:
                tools_meta.append({
                    "name": fn.__name__,
                    "description": (fn.__doc__ or "").strip(),
                    "inputSchema": _build_json_schema(fn)
                })
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": tools_meta}
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        elif method == "tools/call":
            tname = params.get("name", "")
            targs = params.get("arguments") or {}
            fn = TOOLS_BY_NAME.get(tname)
            if not fn:
                result_payload = {"error": f"Unknown tool: {tname}"}
                is_err = True
            else:
                try:
                    result_payload = fn(**targs)
                    is_err = False
                except Exception as e:
                    result_payload = {"error": str(e)}
                    is_err = True

            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result_payload, indent=2)}],
                    "isError": is_err
                }
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        # 3. Resources
        elif method == "resources/list":
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"resources": _get_resources()}
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        elif method == "resources/read":
            uri = params.get("uri", "")
            try:
                res_data = _read_resource(uri)
                resp = {"jsonrpc": "2.0", "id": msg_id, "result": res_data}
            except Exception as e:
                resp = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32602, "message": str(e)}
                }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        # 4. Prompts
        elif method == "prompts/list":
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"prompts": _get_prompts()}
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        elif method == "prompts/get":
            pname = params.get("name", "")
            pargs = params.get("arguments") or {}
            try:
                pdata = _get_prompt(pname, pargs)
                resp = {"jsonrpc": "2.0", "id": msg_id, "result": pdata}
            except Exception as e:
                resp = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32602, "message": str(e)}
                }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        elif msg_id is not None:
            resp = {"jsonrpc": "2.0", "id": msg_id, "result": {}}
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


def print_cli_summary():
    print(f"=== AdventureForge MCP Server ===")
    print(f"Registered Tools: {len(TOOLS_LIST)}")
    print(f"Server Directory: {SERVER_DIR}")
    print("\nCategorized Tools:")
    categories = {
        "Project & Engine": ["project", "launch_pygame", "stop_pygame", "character_roles"],
        "Rooms & World Map": ["room", "walkable", "start_room"],
        "Hotspots & Doors": ["hotspot", "door"],
        "Items & Inventory": ["item"],
        "Puzzles & Rules": ["puzzle"],
        "Branching Dialog Trees": ["dialog"],
        "Cutscenes & Cinematics": ["cutscene"],
        "Sprites & Animations": ["sprite"],
        "Assets & BG Remover": ["asset"],
        "AI Media & Sound Effects (.env)": ["sound", "media", "search_and_download", "generate_image"],
        "Gemini VLM Vision": ["vlm"]
    }
    for cat, kw_list in categories.items():
        matches = [fn.__name__ for fn in TOOLS_LIST if any(kw in fn.__name__ for kw in kw_list)]
        print(f"\n  [{cat}] ({len(matches)} tools):")
        for m in sorted(matches):
            print(f"    - {m}")
    print("\nRun without arguments to start JSON-RPC stdio MCP server.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h", "--list", "--summary", "--tools"):
        print_cli_summary()
    else:
        run_stdio_mcp_server()

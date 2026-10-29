#!/usr/bin/env python3
"""
AdventureForge — Model Context Protocol (MCP) Server

Exposes AdventureForge's game editor & VLM tools, live project resources and
prompt templates over standard MCP (stdio), built on FastMCP.

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
from pathlib import Path
# Ensure directory is on sys.path so imports work regardless of cwd
SERVER_DIR = Path(__file__).resolve().parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from fastmcp import FastMCP  # noqa: E402

from tools import TOOLS_LIST  # noqa: E402
from tools._core import _load_proj  # noqa: E402

mcp = FastMCP(
    name="adventure-forge",
    instructions=(
        "AdventureForge is a point-and-click adventure game studio. Use these tools "
        "to build rooms, hotspots, inventory items, puzzles, branching dialog trees, "
        "cutscenes, sprites and assets, then launch the Pygame runtime to playtest."
    ),
)


# ============================================================================
# Tools — registered straight from the canonical registry so the MCP surface
# and the in-app agent can never drift apart.
# ============================================================================

for _tool_fn in TOOLS_LIST:
    mcp.tool(_tool_fn)


# ============================================================================
# Resources — live views of the project manifest
# ============================================================================

def _project_json() -> str:
    import json
    return json.dumps(_load_proj(), indent=2)


@mcp.resource(
    "adventureforge://project",
    name="AdventureForge Project Manifest",
    description="Full project JSON containing rooms, items, puzzles, dialogs, cutscenes, and settings.",
    mime_type="application/json",
)
def project_manifest() -> str:
    """Complete active project.json."""
    return _project_json()


@mcp.resource(
    "adventureforge://rooms",
    name="AdventureForge Rooms & Hotspots",
    description="Overview of all rooms, background assets, and configured hotspots.",
    mime_type="application/json",
)
def rooms_resource() -> str:
    """All room and hotspot definitions."""
    import json
    return json.dumps(_load_proj().get("rooms", []), indent=2)


@mcp.resource(
    "adventureforge://items",
    name="AdventureForge Inventory Items",
    description="List of all inventory items, descriptions, and their target usage links.",
    mime_type="application/json",
)
def items_resource() -> str:
    """Inventory items and usage targets."""
    import json
    return json.dumps(_load_proj().get("items", []), indent=2)


@mcp.resource(
    "adventureforge://puzzles",
    name="AdventureForge Puzzle Dependency Graph",
    description="Inventory puzzles, requirements, actions, and unlock states.",
    mime_type="application/json",
)
def puzzles_resource() -> str:
    """Puzzle dependency graph."""
    import json
    return json.dumps(_load_proj().get("puzzles", []), indent=2)


@mcp.resource(
    "adventureforge://dialogs",
    name="AdventureForge Dialog Trees",
    description="Branching dialog trees and NPC conversation nodes.",
    mime_type="application/json",
)
def dialogs_resource() -> str:
    """Dialog trees and conversation nodes."""
    import json
    return json.dumps(_load_proj().get("dialogs", []), indent=2)


@mcp.resource(
    "adventureforge://cutscenes",
    name="AdventureForge Cinematic Cutscenes",
    description="Timeline sequences and cinematic steps.",
    mime_type="application/json",
)
def cutscenes_resource() -> str:
    """Cinematic timeline cutscenes."""
    import json
    return json.dumps(_load_proj().get("cutscenes", []), indent=2)


# ============================================================================
# Prompt templates
# ============================================================================

@mcp.prompt
def create_adventure_scene(theme: str, room_name: str) -> str:
    """Construct a fully fleshed-out room with background, hotspots, descriptions and exits."""
    return (
        f"You are an adventure game designer. Use AdventureForge MCP tools to create room "
        f"'{room_name}' with theme '{theme}'. List rooms first, create the room, add 3-4 "
        f"interactive hotspots (examine, pick up, use), and link exit doors."
    )


@mcp.prompt
def design_multi_step_puzzle(objective: str) -> str:
    """Architect a multi-step inventory puzzle chain with keys, clues and environmental locks."""
    return (
        f"Architect a 3-step adventure puzzle to '{objective}'. Use list_items, "
        f"create_or_update_item, link_item_usage, and create_or_update_puzzle to define "
        f"items, targets, and conditions."
    )


@mcp.prompt
def write_branching_dialog(npc_name: str, topic: str) -> str:
    """Author interactive multi-choice NPC dialog with conditions and quest rewards."""
    return (
        f"Create a full branching dialog tree for '{npc_name}' discussing '{topic}'. Use "
        f"create_or_update_dialog_tree, add_or_update_dialog_node, and add_dialog_player_choice "
        f"to build a 3-tier conversation with multiple player branches."
    )


# ============================================================================
# CLI helpers
# ============================================================================

CATEGORIES = {
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
    "Gemini VLM Vision": ["vlm"],
}


def print_cli_summary() -> None:
    print("=== AdventureForge MCP Server ===")
    print(f"Registered Tools: {len(TOOLS_LIST)}")
    print(f"Server Directory: {SERVER_DIR}")
    print("\nCategorized Tools:")
    for cat, kw_list in CATEGORIES.items():
        matches = [fn.__name__ for fn in TOOLS_LIST if any(kw in fn.__name__ for kw in kw_list)]
        print(f"\n  [{cat}] ({len(matches)} tools):")
        for m in sorted(matches):
            print(f"    - {m}")
    print("\nRun without arguments to start the MCP stdio server.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h", "--list", "--summary", "--tools"):
        print_cli_summary()
    else:
        mcp.run()

# AdventureForge MCP Server

AdventureForge features a **Model Context Protocol (MCP)** server that exposes full game studio editing and Gemini VLM capabilities to any LLM/VLM agent (Claude Desktop, Cursor, Antigravity, or custom agents).

## 🚀 Quick Setup

Add AdventureForge to your MCP client configuration (e.g. `claude_desktop_config.json`, `.gemini/antigravity-cli/mcp_config.json`, or Cursor):

```json
{
  "mcpServers": {
    "adventure-forge": {
      "command": "python3",
      "args": ["/home/x/Desktop/IDEAS/adventure_forge/mcp_server.py"]
    }
  }
}
```

### CLI Inspection
```bash
# Print summary of all 57 registered tools and categories
python3 /home/x/Desktop/IDEAS/adventure_forge/mcp_server.py --summary
```

---

## 🛠️ Complete Tool Catalog (57 Tools)

### 1. Project & Pygame Engine (6 tools)
- `get_project_summary()`: Summary of title, rooms, items, puzzles, and start room.
- `get_full_project()`: Returns the full raw `project.json` manifest.
- `set_project_title(title)`: Update the game's display title.
- `set_character_roles(player_sprite, partner_sprite)`: Bind player and partner sprite names.
- `launch_pygame_game(room_id, cutscene_id, dialog_id)`: Launch live Pygame runtime on a specific room, cutscene, or dialog.
- `stop_pygame_game()`: Terminate running Pygame instance.

### 2. Rooms & World Map Navigation (8 tools)
- `list_rooms()`: List all rooms with names and hotspots.
- `get_room(room_id)`: Retrieve full room definition.
- `create_or_update_room(room_id, name, background, map_x, map_y, music, ambient)`: Create or update a room.
- `delete_room(room_id)`: Delete a room.
- `update_room_map_position(room_id, map_x, map_y)`: Set node coordinates on the World Map editor.
- `set_room_walkable_polygon(room_id, points_json)`: Define floor polygon points for character pathfinding.
- `set_start_room(room_id)`: Set the starting room for new playthroughs.
- `vlm_inspect_room_scene(room_id, query)`: Run Gemini VLM visual inspection on a room's background.

### 3. Hotspots, Props, NPCs & Doors (7 tools)
- `list_hotspots(room_id)`: List all interactive hotspots in a room.
- `get_hotspot(room_id, hotspot_id)`: Retrieve specific hotspot metadata.
- `create_or_update_hotspot(room_id, hotspot_id, name, type, rect_json, look_text, use_text, ...)`: Define prop, door, NPC, or item hotspot.
- `delete_hotspot(room_id, hotspot_id)`: Remove a hotspot.
- `link_door(source_room_id, hotspot_id, target_room_id, create_return_door, ...)`: Connect a door hotspot to a destination room with automatic return door creation.
- `set_hotspot_lock(room_id, hotspot_id, locked, required_flag, locked_text)`: Set lock conditions on doors or props.
- `vlm_describe_hotspot(room_id, hotspot_id, style)`: Generate descriptive look_at and use text using Gemini VLM.

### 4. Items & Inventory Interaction (5 tools)
- `list_items()`: List all inventory items.
- `get_item(item_id)`: Get detailed item data.
- `create_or_update_item(item_id, name, description, icon, place_in_room, rect_json, ...)`: Create or edit an item and optionally place it as an in-world pickup.
- `delete_item(item_id)`: Remove an item.
- `link_item_usage(item_id, target_hotspot_id, target_room_id, success_dialog, consumes_item, grants_flag, unlocks_door)`: Wire what happens when an item is used on a hotspot (e.g. key on door).

### 5. Puzzles & Rule Dependency Graph (4 tools)
- `list_puzzles()`: List all registered puzzles.
- `get_puzzle(puzzle_id)`: Retrieve specific puzzle definition.
- `create_or_update_puzzle(puzzle_id, title, description, required_items, target_hotspot, target_room, grants_flag, sets_dialog)`: Create or update a puzzle rule.
- `delete_puzzle(puzzle_id)`: Remove a puzzle.

### 6. Branching Dialog Trees (9 tools)
- `list_dialog_trees()`: List all dialog trees.
- `get_dialog_tree(dialog_id)`: Retrieve a tree and all branching nodes.
- `create_or_update_dialog_tree(dialog_id, title, npc_id, start_node_id)`: Create or update conversation container.
- `delete_dialog_tree(dialog_id)`: Delete dialog tree.
- `add_or_update_dialog_node(dialog_id, node_id, speaker, text, condition_flag, set_flag, give_item)`: Define NPC or narrator lines.
- `delete_dialog_node(dialog_id, node_id)`: Delete a node.
- `add_dialog_player_choice(dialog_id, node_id, choice_text, next_node_id, condition_flag)`: Add branching player dialogue responses.
- `delete_dialog_player_choice(dialog_id, node_id, choice_index)`: Remove a player choice.
- `ai_generate_dialog_tree(npc_name, personality, topic, room_id)`: Generate a 3-tier branching dialog tree with Gemini.

### 7. Cutscenes & Cinematics Timeline (7 tools)
- `list_cutscenes()`: List all cutscenes.
- `get_cutscene(cutscene_id)`: Retrieve cutscene timeline steps.
- `create_or_update_cutscene(cutscene_id, title, trigger)`: Create or update cutscene definition.
- `delete_cutscene(cutscene_id)`: Delete cutscene.
- `add_cutscene_step(cutscene_id, type, actor, target_x, target_y, text, duration, ...)`: Add sequential timeline action.
- `delete_cutscene_step(cutscene_id, step_index)`: Remove step.
- `ai_generate_cutscene(title, premise, actors_csv)`: Generate complete cinematic script timeline with Gemini.

### 8. Sprites & Animation Studio (6 tools)
- `list_sprites()`: List all sprite sheets and animations.
- `get_sprite(sprite_id)`: Get frames, fps, and direction mappings.
- `add_or_update_sprite_animation(sprite_id, anim_name, frames, fps, loop)`: Register or edit an animation sequence.
- `delete_sprite_animation(sprite_id, anim_name)`: Remove an animation.
- `assign_sprite_direction_role(sprite_id, role, anim_name)`: Map standard roles (`idle`, `walk_down`, `walk_up`, `walk_left`, `walk_right`) to animation tracks.
- `set_sprite_scale(sprite_id, scale)`: Adjust in-game sprite rendering scale.

### 9. Assets & Background Remover (4 tools)
- `list_assets(category)`: List image and sound files.
- `remove_asset_background(asset_path, method, tolerance, auto_trim)`: Remove backgrounds retroactively across all rooms/sprites.
- `restore_asset_original(asset_path)`: Revert modified asset to its original unmodified backup.
- `delete_asset_file(asset_path)`: Delete an unused asset.

### 10. Gemini VLM Visual Vision (3 tools)
- `vlm_auto_detect_and_place_props(room_id, max_props)`: Detect interactable props in room backgrounds and place hotspots.
- `vlm_describe_hotspot(room_id, hotspot_id, style)`: Generate LucasArts-style examine descriptions.
- `vlm_inspect_room_scene(room_id, query)`: Ask visual questions about any room background.

---

## 📦 MCP Resources

Clients can read live game state through standard MCP resource URIs:
- `adventureforge://project`: Complete active `project.json`
- `adventureforge://rooms`: All rooms and hotspot definitions
- `adventureforge://items`: Inventory items and usage targets
- `adventureforge://puzzles`: Puzzle dependency graph
- `adventureforge://dialogs`: Dialog trees and conversation nodes
- `adventureforge://cutscenes`: Cinematic timeline cutscenes

## 💬 MCP Prompt Templates

- `create_adventure_scene`: Generates a fully fleshed-out room with props, descriptions, and exits.
- `design_multi_step_puzzle`: Architect a multi-step inventory puzzle chain with keys, clues, and environmental locks.
- `write_branching_dialog`: Authors interactive multi-choice NPC dialog with conditions and quest rewards.

# AdventureForge MCP Server

AdventureForge exposes its full game studio over the
[Model Context Protocol](https://modelcontextprotocol.io) — so Claude Desktop,
Cursor, Antigravity or any custom agent can build the game directly.

Built on [FastMCP](https://github.com/jlowin/fastmcp): tool schemas are
generated from real type hints and docstrings, so clients get correct types
(`integer`, `number`, `boolean`, `string`) instead of guesswork.

## Setup

```json
{
  "mcpServers": {
    "adventure-forge": {
      "command": "python3",
      "args": ["/absolute/path/to/adventure-forge/mcp_server.py"]
    }
  }
}
```

Inspect the surface without connecting:

```bash
python3 mcp_server.py --summary
```

---

## Tool catalogue (68 tools)

### 1. Project & Engine (6)
- `get_project_summary()` — title, rooms, hotspots, items, puzzles, sprites, dialogs, cutscenes.
- `get_full_project()` — the entire raw `project.json`.
- `set_project_title(title)` — change the display title.
- `set_character_roles(player_sprite, partner_sprite)` — bind player and partner sprites.
- `launch_pygame_game(room_id, cutscene_id, dialog_id)` — launch the live Pygame runtime.
- `stop_pygame_game()` — terminate the running runtime.

### 2. Rooms & World Map (7)
- `list_rooms()` — rooms with names, map coordinates and hotspot counts.
- `get_room(room_id)` — full room definition.
- `create_or_update_room(room_id, name, background, player_start_x, player_start_y, set_as_start)` — create or update.
- `delete_room(room_id)` — remove a room.
- `update_room_map_position(room_id, map_x, map_y)` — position on the world map.
- `set_room_walkable_polygon(room_id, points_json)` — floor polygon for pathfinding.
- `set_start_room(room_id)` — set the starting room.

### 3. Hotspots, Props, NPCs & Doors (6)
- `list_hotspots(room_id)` — interactive hotspots in a room.
- `get_hotspot(room_id, hotspot_id)` — one hotspot's metadata.
- `create_or_update_hotspot(...)` — define a prop, door, NPC or item hotspot.
- `delete_hotspot(room_id, hotspot_id)` — remove a hotspot.
- `link_door(source_room_id, hotspot_id, target_room_id, create_return_door, ...)` — connect rooms, optionally auto-creating the return door.
- `set_hotspot_lock(room_id, hotspot_id, locked, required_flag, locked_text)` — lock conditions.

### 4. Items & Inventory (5)
- `list_items()` — inventory items.
- `get_item(item_id)` — item detail.
- `create_or_update_item(item_id, name, description, icon, place_in_room, ...)` — edit an item, optionally placing it in the world.
- `delete_item(item_id)` — remove an item.
- `link_item_usage(item_id, target_hotspot_id, target_room_id, success_dialog, consumes_item, grants_flag, unlocks_door)` — what happens when the item is used on a hotspot.

### 5. Puzzles & Rules (4)
- `list_puzzles()` — registered puzzles.
- `get_puzzle(puzzle_id)` — one puzzle.
- `create_or_update_puzzle(puzzle_id, title, description, required_items, target_hotspot, target_room, grants_flag, sets_dialog)` — create or update a rule.
- `delete_puzzle(puzzle_id)` — remove a puzzle.

### 6. Branching Dialog Trees (9)
- `list_dialog_trees()` — all conversations.
- `get_dialog_tree(dialog_id)` — a tree with every node.
- `create_or_update_dialog_tree(dialog_id, title, npc_id, start_node_id)` — conversation container.
- `delete_dialog_tree(dialog_id)` — remove a tree.
- `add_or_update_dialog_node(dialog_id, node_id, speaker, text, condition_flag, set_flag, give_item)` — an NPC or narrator line.
- `delete_dialog_node(dialog_id, node_id)` — remove a node.
- `add_dialog_player_choice(dialog_id, node_id, choice_text, next_node_id, condition_flag)` — a player branch.
- `delete_dialog_player_choice(dialog_id, node_id, choice_index)` — remove a branch.
- `ai_generate_dialog_tree(npc_name, personality, topic, room_id)` — Gemini writes a 3-tier branching tree.

### 7. Cutscenes & Cinematics (7)
- `list_cutscenes()` / `get_cutscene(cutscene_id)` — timeline definitions.
- `create_or_update_cutscene(cutscene_id, title, trigger_type, trigger_target, requires_flag, sets_flag, once)` — cutscene metadata.
- `delete_cutscene(cutscene_id)` — remove a cutscene.
- `add_cutscene_step(cutscene_id, type, actor, target_x, target_y, text, duration, ...)` — append a timeline action.
- `delete_cutscene_step(cutscene_id, step_index)` — remove a step.
- `ai_generate_cutscene(title, premise, actors_csv)` — Gemini writes the whole timeline.

### 8. Sprites & Animation Studio (6)
- `list_sprites()` / `get_sprite(sprite_id)` — sprite sheets and animations.
- `add_or_update_sprite_animation(sprite_id, anim_name, frames, fps, loop)` — register an animation.
- `delete_sprite_animation(sprite_id, anim_name)` — remove an animation.
- `assign_sprite_direction_role(sprite_id, role, anim_name)` — map `idle`, `walk_down`, `walk_up`, `walk_left`, `walk_right` to tracks.
- `set_sprite_scale(sprite_id, scale)` — in-game render scale.

### 9. Assets & Background Remover (5)
- `list_assets(category)` — images and sounds.
- `remove_asset_background(asset_path, method, tolerance, auto_trim)` — strip backgrounds retroactively.
- `restore_asset_original(asset_path)` — revert to the `.orig` backup.
- `delete_asset_file(asset_path)` — remove an unused asset.
- `pixelize_asset(asset_path, pixel_size, num_colors, auto_remove_bg)` — convert to 16/32-bit pixel art.

### 10. AI Media & Sound Effects (9)
- `list_available_media_apis()` — which providers are configured.
- `search_and_download_sound_effects(query, category, count)` — Freesound.
- `search_and_download_images(query, count)` — Google Images via SerpAPI.
- `spritefusion_get_credits()` / `spritefusion_list_saved_assets()` / `spritefusion_generate_pixel_art(...)` — Sprite Fusion MCP.
- `jetson_generate_image(prompt, category, filename, ...)` — local SD on the Jetson GPU.
- `generate_image_ai(prompt, category, filename, auto_remove_bg, ...)` — cloud generator with backend fallback.
- `download_asset_from_url(url, category, filename)` — fetch an asset directly.

### 11. Gemini VLM Vision (4)
- `vlm_auto_detect_and_place_props(room_id, count, hint)` — read the room background through a coordinate grid overlay, detect props, write Look At / Use lines, place them.
- `vlm_generate_and_place_items(room_id, count, generate_sprites, hint)` — find surfaces, place item hotspots at pixel-accurate coordinates and generate their icons.
- `vlm_describe_hotspot(room_id, hotspot_id, style)` — auto-fill a hotspot's name, look text and use text.
- `vlm_inspect_room_scene(room_id, query_question)` — ask any question about a room's background.

---

## Resources

Clients can read live game state through standard MCP resource URIs:

| URI | Contents |
|---|---|
| `adventureforge://project` | Complete active `project.json` |
| `adventureforge://rooms` | Rooms and hotspot definitions |
| `adventureforge://items` | Inventory items and usage targets |
| `adventureforge://puzzles` | Puzzle dependency graph |
| `adventureforge://dialogs` | Dialog trees and conversation nodes |
| `adventureforge://cutscenes` | Cinematic timeline cutscenes |

## Prompt templates

| Prompt | Arguments | Purpose |
|---|---|---|
| `create_adventure_scene` | `theme`, `room_name` | Build a room with props, descriptions and exits |
| `design_multi_step_puzzle` | `objective` | Architect a key/clue/lock puzzle chain |
| `write_branching_dialog` | `npc_name`, `topic` | Multi-choice NPC conversation with conditions and rewards |

---

## Notes

- Tools mutate `data/project.json` in place. `get_full_project` and the
  `adventureforge://project` resource both reflect the current state.
- AI tools need their API keys in `.env`; `list_available_media_apis()` tells
  you what is configured.
- `create_coordinate_grid_overlay` is an internal helper (it takes a PIL image)
  and is therefore not registered as an MCP tool.

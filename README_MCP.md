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
python3 mcp_server.py --summary     # 86 tools by category
```

---

## Tool catalogue (86 tools)

Signatures below are the real ones — generated from the Python source, so they
always match the implementation.

### 1. Project & Engine (6)
- `get_project_summary()` — title, rooms, hotspots, items, puzzles, **characters**, sprites, dialogs, cutscenes, **events**.
- `get_full_project()` — the entire raw `project.json`.
- `set_project_title(title)` — change the display title.
- `set_character_roles(player_sprite, partner_sprite)` — legacy shortcut that binds a player sprite and a companion sprite. It writes through to `project.characters` as well.
- `launch_pygame_game(room_id, cutscene_id, dialog_id)` — launch the live Pygame runtime.
- `stop_pygame_game()` — terminate the running runtime.

### 2. Rooms & World Map (7)
- `list_rooms()` — rooms with names, map coordinates and hotspot counts.
- `get_room(room_id)` — full room definition, including colliders and the walkable polygon.
- `create_or_update_room(room_id, name, background, player_start_x, player_start_y, set_as_start)` — create or update.
- `delete_room(room_id)` — remove a room.
- `update_room_map_position(room_id, map_x, map_y)` — position on the world map.
- `set_room_walkable_polygon(room_id, points_json)` — floor polygon for pathfinding.
- `set_start_room(room_id)` — set the starting room.

### 3. Collision Geometry (4)
The **negative space** of a room: walls, furniture, obstacles. Characters slide
along colliders instead of stopping dead, and are kept out of them entirely.

- `list_room_colliders(room_id)` — every blocked shape in a room.
- `add_room_collider(room_id, collider_type, x, y, w, h, points_json, collider_id)` — add one shape. `collider_type` is `"rect"` (uses `x/y/w/h`) or `"poly"` (uses `points_json`, a JSON array of `{"x":..,"y":..}`).
- `set_room_colliders(room_id, colliders_json)` — replace every shape at once with a JSON array of rect/poly objects.
- `clear_room_colliders(room_id)` — remove every blocked shape, making the whole floor walkable.

### 4. Characters (6)
AdventureForge is a **generic engine**: a project owns a roster of characters,
not a hard-coded player-and-buddy pair. Each character has a `role`:

| Role | Meaning |
|---|---|
| `player` | the character the player controls (exactly one) |
| `companion` | follows the player around (`follow` can be turned off) |
| `npc` | lives in a room and is talked to through a hotspot |

- `list_characters()` — the whole roster with sprites, roles, follow settings and who the player is.
- `get_character(character_id)` — one character's full definition.
- `create_or_update_character(character_id, name, sprite, role, color, scale, dialog_id, follow, follow_distance, follow_speed, set_as_player)` — create or edit. `color` takes `"r,g,b"` or `"#rrggbb"`; `scale=0` means "use the sprite's own scale"; leave `follow` unset to keep the current value.
- `delete_character(character_id)` — remove a character and detach it from any hotspot that referenced it.
- `set_player_character(character_id)` — choose who the player controls.
- `assign_character_to_hotspot(room_id, hotspot_id, character_id)` — bind a character to an NPC hotspot (pass an empty id to unbind).

### 5. Hotspots, Props, NPCs & Doors (6)
- `list_hotspots(room_id)` — interactive hotspots in a room.
- `get_hotspot(room_id, hotspot_id)` — one hotspot's metadata.
- `create_or_update_hotspot(room_id, hotspot_id, name, hs_type, x, y, w, h, look_text, use_text, talk_text, icon, item_id, pickup_text, target_room, locked, required_flag, locked_text, sprite_id, npc_anim, dialog_id, cutscene_id)` — define a prop, door, NPC or item hotspot. `hs_type` is `prop`, `pickup`, `npc` or `exit`.
- `delete_hotspot(room_id, hotspot_id)` — remove a hotspot.
- `link_door(source_room_id, hotspot_id, target_room_id, door_name, locked, required_flag, create_return_door)` — connect rooms, optionally auto-creating the return door.
- `set_hotspot_lock(room_id, hotspot_id, locked, required_flag, locked_text)` — lock conditions.

### 6. Items & Inventory (5)
- `list_items()` — inventory items.
- `get_item(item_id)` — item detail.
- `create_or_update_item(item_id, name, description, icon, place_in_room, x, y, w, h)` — edit an item, optionally placing it in the world.
- `delete_item(item_id)` — remove an item.
- `link_item_usage(item_id, target_id, purpose, sets_flag, success_text, consume_item, gives_item, cutscene_id)` — what happens when the item is used on a hotspot. `purpose` is a free-text label (`unlock_door` by default).

### 7. Puzzles & Rules (4)
- `list_puzzles()` — registered puzzles.
- `get_puzzle(puzzle_id)` — one puzzle.
- `create_or_update_puzzle(puzzle_id, name, trigger, item_id, target_id, requires_flag, sets_flag, gives_item, cutscene_id, consume_item, success_text)` — create or update a rule. `trigger` is `use_item_on_hotspot` or `interact_hotspot`.
- `delete_puzzle(puzzle_id)` — remove a puzzle.

### 8. Branching Dialog Trees (9)
- `list_dialog_trees()` — all conversations.
- `get_dialog_tree(dialog_id)` — a tree with every node.
- `create_or_update_dialog_tree(dialog_id, name, npc_name, root_node, set_as_partner)` — conversation container.
- `delete_dialog_tree(dialog_id)` — remove a tree.
- `add_or_update_dialog_node(dialog_id, node_id, speaker, npc_text)` — a line of dialogue. `speaker` may be `npc`, `player`, `narrator` or any character id.
- `delete_dialog_node(dialog_id, node_id)` — remove a node.
- `add_dialog_player_choice(dialog_id, node_id, text, reply_text, next_node, requires_flag, sets_flag, gives_item, triggers_cutscene, once)` — a player branch. `next_node` is a node id, `"__stay__"` or `"__exit__"`.
- `delete_dialog_player_choice(dialog_id, node_id, choice_index)` — remove a branch.
- `ai_generate_dialog_tree(dialog_id, npc_name, topic_prompt, attach_to_hotspot, set_as_partner_dialog)` — Gemini writes a 3-tier branching tree.

### 9. Events & Triggers (8)
One dispatch path for the whole game: an event pairs a **trigger** with a list
of **actions**.

| Trigger type | Fires when | `trigger_target` matches |
|---|---|---|
| `on_game_start` | the runtime boots | — |
| `on_enter_room` | the player walks into a room | room id |
| `on_flag_set` | a story flag is raised | flag name |
| `on_item_pickup` | an item is collected | item id |
| `on_hotspot_use` | an object is interacted with | hotspot id |
| `on_dialog_end` | a conversation finishes | dialog id |

| Action type | Effect |
|---|---|
| `set_flag` / `clear_flag` | raise or drop a story flag |
| `play_cutscene` | start a cutscene |
| `start_dialog` | open a dialog tree |
| `give_item` | add an item to the inventory |
| `unlock_door` | clear a hotspot's `locked` flag |
| `show_text` | say a line |
| `play_sound` | play a sound effect |

- `list_events()` — every event with its trigger, actions and settings.
- `get_event(event_id)` — one event.
- `create_or_update_event(event_id, name, trigger_type, trigger_target, once, priority, enabled, requires_flag)` — create or edit an event. Leave `trigger_target` empty to match any target; `requires_flag` gates the event behind a flag; `priority` orders matching events (highest first).
- `delete_event(event_id)` — remove an event.
- `add_event_action(event_id, action_type, value, speaker)` — append an action.
- `remove_event_action(event_id, action_index)` — remove an action by index.
- `set_event_actions(event_id, actions_json)` — replace every action with a JSON array of `{"type":..,"value":..}` objects.
- `migrate_legacy_triggers()` — convert old `trigger_type` / `trigger_target` fields on cutscenes into real events.

### 10. Cutscenes & Cinematics (7)
- `list_cutscenes()` / `get_cutscene(cutscene_id)` — timeline definitions.
- `create_or_update_cutscene(cutscene_id, name, trigger_type, trigger_target, requires_flag, sets_flag, once)` — cutscene metadata.
- `delete_cutscene(cutscene_id)` — remove a cutscene.
- `add_cutscene_step(cutscene_id, step_type, actor, text, x, y, duration, target_room_id, flag_name, item_id, dialog_id, anim_name, effect)` — append a timeline action. `step_type` is `say`, `walk`, `wait`, `fade`, `play_anim`, `change_room`, `set_flag`, `play_sound` or `give_item`.
- `delete_cutscene_step(cutscene_id, step_index)` — remove a step.
- `ai_generate_cutscene(cutscene_id, room_id, scene_prompt, trigger_type, trigger_target)` — Gemini writes the whole timeline.

### 11. Sprites & Animation Studio (6)
- `list_sprites()` / `get_sprite(sprite_id)` — sprite sheets and animations.
- `add_or_update_sprite_animation(sprite_id, anim_name, fps, loop, frame_indices)` — register an animation. `frame_indices` is a comma-separated list such as `"0,1,2"`.
- `delete_sprite_animation(sprite_id, anim_name)` — remove an animation.
- `assign_sprite_direction_role(sprite_id, role, anim_name)` — map `idle`, `walk_down`, `walk_up`, `walk_left`, `walk_right` to tracks.
- `set_sprite_scale(sprite_id, scale)` — in-game render scale.

### 12. Assets & Background Remover (5)
- `list_assets(category)` — images and sounds.
- `remove_asset_background(asset_url, mode, tolerance, trim)` — strip backgrounds retroactively (`mode` is `corners`, `floodfill` or `alpha`).
- `restore_asset_original(asset_url)` — revert to the `.orig` backup.
- `delete_asset_file(asset_url)` — remove an unused asset.
- `pixelize_asset(asset_url, pixel_size, num_colors, auto_remove_bg)` — convert to 16/32-bit pixel art.

### 13. AI Media & Sound Effects (9)
- `list_available_media_apis()` — which providers are configured.
- `search_and_download_sound_effects(query, category, filename, min_duration, max_duration, link_to_room_id, link_to_puzzle_id)` — Freesound.
- `search_and_download_images(query, category, filename, transparent_only, auto_remove_bg, link_to_room_id, link_to_item_id, link_to_hotspot_id)` — Google Images via SerpAPI.
- `spritefusion_get_credits()` / `spritefusion_list_saved_assets()` / `spritefusion_generate_pixel_art(...)` — Sprite Fusion MCP.
- `jetson_generate_image(prompt, category, filename, ...)` — local SD on the Jetson GPU.
- `generate_image_ai(prompt, category, filename, aspect_ratio, auto_remove_bg, ...)` — cloud generator with backend fallback.
- `download_asset_from_url(url, category, filename, auto_remove_bg)` — fetch an asset directly.

### 14. Gemini VLM Vision (4)
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
| `adventureforge://rooms` | Rooms, colliders and hotspot definitions |
| `adventureforge://items` | Inventory items and usage targets |
| `adventureforge://puzzles` | Puzzle dependency graph |
| `adventureforge://dialogs` | Dialog trees and conversation nodes |
| `adventureforge://cutscenes` | Cinematic timeline cutscenes |
| `adventureforge://characters` | The character roster, normalised (player / companion / npc) |
| `adventureforge://events` | Events and triggers, including not-yet-migrated legacy cutscene triggers |

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
- **Backward compatibility**: projects that still use `player_sprite`,
  `partner_sprite` and `partner_dialog_id` keep working. The runtime derives a
  two-character roster from them when `project.characters` is absent, and the
  legacy `partner` cutscene-actor token still resolves to the first companion.

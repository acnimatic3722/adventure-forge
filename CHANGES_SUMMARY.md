# AdventureForge — Refactoring Notes

This document records the work done to turn the original one-night prototype
into a maintainable, deployable project. It replaces the earlier summary,
which described intentions rather than the final state.

---

## 0. The engine is generic now (2026-10)

The prototype was a Sam & Max game wearing an engine's clothes. Three
subsystems were added to turn it into a real point-and-click engine, plus the
audit and UI work that came with them.

### 0.1 Audit findings

A full pass over the backend and the editor turned up these problems before
any of them were fixed:

- `locked` / `required_flag` were honoured **only** on `exit` hotspots — a
  locked prop was never gated.
- `README_MCP.md` documented three parameters that **did not exist**:
  `grants_flag`, `sets_dialog` and `unlocks_door`.
- `hide_if_flag` was an orphan field.
- `start_cutscene` / `start_dialog` bypassed `requires_flag` via `force=True`.
- One global flag namespace, four different flag field names
  (`required_flag`, `sets_flag`, `grants_flag`, `requires_flag`) and three
  different "once" mechanisms.
- Flags were never persisted.
- There was no way for a hotspot to set a flag.
- A dialog that set a flag suppressed the cutscene trigger for that flag.
- Sam & Max wording was baked into the runtime, the AI prompts and the docs.

### 0.2 Collision geometry — `engine_geometry.py`

Rooms now carry a `colliders` list — the *negative* space of the room:

```jsonc
"colliders": [
  {"id": "desk", "type": "rect", "x": 400, "y": 380, "w": 260, "h": 60},
  {"id": "pool",  "type": "poly", "points": [{"x": 0, "y": 0}, ...]}
]
```

- Characters are a circle of radius 14 centred on their **feet** point (the
  engine draws sprites bottom-centre there), so they can stand flush against
  a wall without their head poking through it.
- `resolve_movement()` slides: full step → horizontal only → vertical only →
  stay put. Walking diagonally into a wall slides along it.
- A spawn point that ends up inside geometry is rescued by
  `nearest_free_point()`.
- A hotspot tucked against a wall still fires — the player gets within
  `BLOCKED_ARRIVE_DISTANCE` (56 px) and the interaction runs. When they
  genuinely cannot reach it, the game says *"I can't get any closer."*
- Companions respect the same geometry.
- The maths is **pure** (no Pygame, no I/O) so it is unit-testable, and the
  MCP tools use exactly the same code as the runtime.

New tools: `list_room_colliders`, `add_room_collider`, `set_room_colliders`,
`clear_room_colliders`.

Editor: a new **🚧 Blocked Area** tool under *Room & Hotspots → Place & Edit
Tools*, with drag-to-draw, click-to-select, drag-to-move, corner-resize, a
red dashed overlay with a `BLOCKED` label, a sidebar card listing every shape,
and undo/redo.

### 0.3 Character roster — `engine_characters.py`

`player_sprite` + `partner_sprite` + one global `partner_dialog_id` became a
roster:

```jsonc
"player_character": "detective",
"characters": {
  "detective": {"name": "Vex", "sprite": "vex", "role": "player", "color": [240, 200, 80]},
  "sidekick":  {"name": "Bibi", "sprite": "bibi", "role": "companion", "follow": true,
                "follow_distance": 130, "follow_speed": 245},
  "clerk":     {"name": "Mira", "sprite": "mira", "role": "npc", "dialog_id": "dlg_mira"}
}
```

- Roles: `player`, `companion`, `npc`. Any number of companions can follow.
- The engine keeps `self.partner_*` as **property proxies** onto
  `self.companions[0]`, so all ~12 legacy call sites keep working while the
  underlying model is free to follow many characters.
- NPC hotspots resolve a `character_id` to a sprite, a display name and a
  dialogue tree.
- Cutscene actors accept any character id (the legacy `partner` token still
  works).
- **Backward compatible:** when `project.characters` is absent, the runtime
  derives a two-character roster from `player_sprite` / `partner_sprite` /
  `partner_dialog_id`.

New tools: `list_characters`, `get_character`, `create_or_update_character`,
`delete_character`, `set_player_character`, `assign_character_to_hotspot`.

Editor: a new **Characters** card in *Sprite & Animation Studio*, plus a
character selector on every NPC hotspot.

### 0.4 Event system — `engine_events.py`

Trigger fields scattered across cutscenes, hotspots and puzzles were replaced
by one trigger/action system:

```jsonc
"events": [{
  "id": "ev_intro", "name": "Arrival", "once": true, "priority": 0,
  "requires_flag": "",
  "trigger": {"type": "on_enter_room", "target": "reception"},
  "actions": [{"type": "play_cutscene", "value": "intro"},
              {"type": "set_flag", "value": "met_the_manager"}]
}]
```

- Triggers: `on_game_start`, `on_enter_room`, `on_flag_set`, `on_item_pickup`,
  `on_hotspot_use`, `on_dialog_end`.
- Actions: `set_flag`, `clear_flag`, `play_cutscene`, `start_dialog`,
  `give_item`, `unlock_door`, `show_text`, `play_sound`.
- Actions are **queued** and drained one at a time by `process_event_queue()`,
  and only when no cutscene or dialog is running — so one event cannot clobber
  another. The queue is capped at 64 items.
- Legacy cutscene `trigger_type` / `trigger_target` fields are converted to
  real events at load time (`migrate_cutscene_triggers`), so there is exactly
  one dispatch path. Legacy events respect the old `allow_cutscene_trigger`
  switch; authored events always fire.
- `end_dialog()` fires `on_dialog_end` — except when a cutscene interrupts the
  conversation, because then the dialog did not really finish.

New tools: `list_events`, `get_event`, `create_or_update_event`,
`delete_event`, `add_event_action`, `remove_event_action`, `set_event_actions`,
`migrate_legacy_triggers`.

Editor: a new tab **7. Events & Triggers** with a trigger editor, an action
list with inline value fields and id pickers, and reference cards for every
trigger and action type.

### 0.5 Bugs found and fixed along the way

- A dangling `start_room` pointed at a room that no longer existed — the game
  booted black and the editor showed an empty screen. The engine now falls
  back to the first room; the editor validates `selectedRoomId` on load.
- The **Test Room** button called `testCurrentRoom()`, which did not exist.
  It now calls `playGame(true)`.
- No favicon → the browser tab showed a broken icon on every 404.
- `_as_color()` rejected the `"r,g,b"` format its own tool documented.
- `create_or_update_character` always overwrote `follow`, so a companion
  created without it would not follow. `follow` is now tri-state
  (`bool | None`).
- The UI smoke test was writing into the live `data/project.json`. It now
  runs against a throwaway data directory via `ADVENTURE_FORGE_DATA_DIR`.

### 0.6 Sam & Max hardcoding removed

The runtime, the MCP tools and every AI prompt assumed a player-and-buddy
pair named Sam and Max. Now:

- The player name comes from the character roster.
- The partner click handler speaks the companion's own name and dialogue.
- "You crack me up, little buddy." → *"{name} has nothing to say right now."*
- AI prompts (prop description, dialog tree, cutscene director, VLM prop and
  item detection) are **project-aware**: they read the real roster and offer
  the real character ids as speakers and actors.
- The engine docstring no longer calls itself "LucasArts-style".

The LoRA model file `lucasarts_retro_style.safetensors` keeps its name — that
is a filename, not a hardcoded character.

### 0.7 Numbers

| | Before | After |
|---|---|---|
| MCP tools | 68 | **86** |
| MCP resources | 6 | **8** |
| Runtime subsystems | — | collision, characters, events |
| Editor tabs | 6 | **7** (+ Events & Triggers) |
| pytest | 83 | **188** |
| UI smoke checks | — | **24** (Playwright, headless Chrome) |

---

## 1. The duplication problem

`agent_tools.py` (3,449 lines) held every tool implementation. The `tools/`
package was then added as a *copy* of it rather than a move:

- **75 functions existed in both places**, 71 byte-identical.
- **4 had already diverged**, including `vlm_generate_and_place_items` and
  `launch_pygame_game`.
- `tools/agent.py` imported `TOOLS_LIST` from `agent_tools`, so the **in-app
  chat agent ran the old implementations** while external MCP clients ran the
  new ones — the same project could be edited differently depending on who
  asked.
- The split silently dropped `vlm_describe_hotspot` and
  `vlm_inspect_room_scene` from the MCP surface, even though
  `README_MCP.md` still advertised them.

### Resolution

- `tools/_core.py` now owns the shared internals (project persistence, asset
  resolution, credential discovery, runtime state).
- `agent_tools.py` is **deleted**.
- Every tool module imports from `tools/_core`.
- `tools/agent.py` uses the canonical `tools.TOOLS_LIST`.
- Both dropped VLM tools were restored.
- The MCP server and the in-app agent now execute **the same function
  objects** — drift is structurally impossible.

| | Before | After |
|---|---|---|
| `agent_tools.py` | 3,449 lines | deleted |
| Duplicate functions | 75 | 0 |
| Diverged functions | 4 | 0 |
| Registered tools | 57 (two registries) | 68 (one registry) |

---

## 2. VLM item placement (merged)

`vlm_generate_and_place_items` existed in two incompatible versions. The
merged implementation keeps both strengths:

- **Placement** — the coordinate-grid-overlay pipeline, with pixel-accurate
  `rect` / `walk_to` positions and a pickup hotspot registered alongside the
  inventory item.
- **Icons** — the legacy Jetson-first generation path: local SD when
  available, then cloud backends (Sprite Fusion → Gemini → Serp), then
  pixelisation to 32×32 / 16 colours, and finally a letter-badge fallback so
  an item is never left without a sprite.
- Both payload shapes are accepted (`{"rect": {...}}` and flat `x/y/w/h`), so
  older prompts keep working.

---

## 3. Configuration and secrets

- **`.env` was never read.** `load_env()` defaulted to the *parent* directory's
  `.env`; the project's own `.env` was dead weight and editing it alone had no
  effect. Loading now happens in `config.py`: project `.env` first, parent
  `.env` as fallback, and real environment variables always win.
- **Path overrides now work.** `config.py` captured `os.getenv()` at import
  time, before any `.env` was loaded, so `ADVENTURE_FORGE_*` settings in a
  `.env` were ignored. The `.env` is now loaded before the class body
  evaluates those values.
- **Paths are resolved at call time** (`config.PROJECT_FILE`, not a module
  constant captured at import), which is what makes runtime overrides and
  test isolation work.
- **`ensure_dirs()` derives its sub-directories** from `ASSETS_DIR` at call
  time rather than from class attributes frozen at import.
- **Asset traversal guard tightened** — `startswith()` let a sibling directory
  such as `data/assets_evil/` pass; it now uses `Path.is_relative_to()`.

---

## 4. Sprite slicer integrated

The sprite slicer lived in a sibling project (`/home/x/Desktop/IDEAS/tools/`)
and was imported by absolute path, so the repo could not run without it.

- Vendored into `sprite_slicer/` as a real package (`slicer.py`, `__init__.py`,
  `__main__.py` CLI).
- **Godot export code removed** — the tool predates the editor and its Godot
  `SpriteFrames` output was not used by AdventureForge.
- `export_frames()` was folded in, removing a duplicated copy of the frame
  export loop from `app.py`.
- `app.py` imports it directly, with a fallback to an external checkout if
  `ADVENTURE_FORGE_SPRITE_SLICER_PATH` points elsewhere.
- `scipy` (required by the segmentation) added to `requirements.txt` — it was
  installed locally but never pinned, so the Docker image could not import it.

---

## 5. MCP server rebuilt on FastMCP

The hand-rolled JSON-RPC implementation typed every parameter as `"string"`
unless its annotation was exactly `int`, `float` or `bool`, and descriptions
were literally `"Parameter x"`.

- Rebuilt on FastMCP 4.1 — schemas now come from real type hints and
  docstrings.
- All 86 tools, 8 resources and 3 prompt templates register correctly.
- Verified over real stdio JSON-RPC (`initialize` → `tools/list`).
- `create_coordinate_grid_overlay` is no longer registered as a tool (it takes
  a PIL image object, which a client cannot pass); it stays importable as a
  helper.

---

## 6. Tests

The suite had **21 failures** and, worse, **wrote into the live
`data/project.json`** — the test fixture patched `Config.PROJECT_FILE`, but the
tools read a module-level constant captured at import time, so the patch never
applied. Running the tests mutated the real project (1 room → 6 rooms).

Fixes:

- Paths resolve through `config` at call time → the fixture now isolates the
  project file. **The live project is never touched by tests.**
- 10 tool functions were used but never imported (`get_room`, `set_start_room`,
  `link_door`, `get_cutscene`, …) → imported.
- Patch targets pointed at names that had moved (`app.run_agent_instruction`
  → `tools.agent.run_agent_instruction`, `tools.project.PYGAME_PROC` →
  `tools._core.PYGAME_PROC`, `app.load_env` → `app.config.load_env`).
- The fixture mocked `PIL` and `numpy` wholesale, which broke the image
  endpoints; only the Gemini client is mocked now.
- Asset tests used MagicMock paths that made `shutil.copy2` fail with
  `SameFileError`; they use real temp files now.
- Two assertions encoded stale behaviour (the sound cache is keyed by resolved
  path; `create_or_update_cutscene` seeds two default steps).

**Result: 188 passed, 0 failed** (26% statement coverage over `tools/`,
`config/` and `sprite_slicer/`; the untested bulk is network-bound AI code).

The new subsystems added their own coverage:

- `tests/test_new_systems.py` — 43 tests over the pure geometry, character and
  event models.
- `tests/test_engine.py` — runtime-level tests: the player cannot walk through
  a wall, slides along one, is rescued from a spawn point inside geometry,
  tells the player when it cannot reach a hotspot, and can still use a hotspot
  that sits against a wall; companions respect the geometry; events fire,
  queue, drain one at a time, wait for a clear stage, honour `once`,
  `requires_flag` and `enabled`; `end_dialog` fires `on_dialog_end` but a
  cutscene interrupt does not; legacy cutscene triggers migrate into events.
- `tests/ui_smoke.py` — 24 headless-Chrome checks that drive the real editor:
  the collision tool (draw, undo, redo, move, clear), the character roster
  (create, rename, set as player) and the events tab (create, edit trigger,
  add action, edit action value, save round-trip). It runs against a
  throwaway data directory and asserts zero console errors.

---

## 7. Docker

The image could not start:

- `ADVENTURE_FORGE_SPRITE_SLICER_PATH` pointed at `/app/tools/sprite_slicer`,
  which was never copied into the image → `ImportError` at startup.
- `pip install -r requirements.txt 2>/dev/null || true` **masked install
  failures**, so a broken dependency set silently produced a broken image.
- The `dev` stage re-pinned dependencies that are now in `requirements.txt`.

Fixes: the slicer ships with the repo, install failures are fatal, the dev
stage was simplified, and a `.dockerignore` was added so `.env`, `.venv/` and
`.git/` never enter the build context.

---

## 8. Repository hygiene

- **Git initialised** (the project had no version control).
- `.gitignore` (secrets, venvs, caches) and `.env.example` added.
- `.dockerignore` added.
- `requirements.txt` repinned to the versions actually in use, and completed
  with the packages that were missing but required (`scipy`, `pygame-ce`,
  `fastmcp`).

---

## Still open

- `static/index.html` is ~6,800 lines in one file — worth splitting into ES
  modules, best done separately from behavioural work.
- `app.py` keeps its own VLM *preview* endpoints (`/api/vlm/describe-prop`,
  `/api/vlm/generate-dialog`, `/api/vlm/generate-cutscene`). They return JSON
  for the editor UI instead of writing to `project.json`, so they are not
  duplicates of the MCP tools, but the prompts overlap.
- `app.py`'s `POST /api/project` now preserves every legacy key on save
  (`player_sprite`, `partner_sprite`, `partner_dialog_id`) as well as the
  character roster and event list.
- `locked` / `required_flag` are still only enforced on `exit` hotspots.
- Flags are still not persisted across sessions — there is no save-game yet.
- No license file yet.
- Coverage is concentrated on the deterministic tool layer; the AI/network
  paths need integration tests against a running server.
- The GitHub Actions workflow could not be pushed with the token that was
  available (it lacked the `workflow` scope).

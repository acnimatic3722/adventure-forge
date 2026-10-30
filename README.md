# AdventureForge

**A point-and-click adventure game studio** — web editor, Pygame runtime, and an
86-tool MCP server so AI agents can build the whole game: rooms, hotspots,
collision geometry, a character roster, inventory, puzzles, branching dialog,
cutscenes, event triggers, sprites, audio and art.

![python](https://img.shields.io/badge/python-3.12-blue) ![fastapi](https://img.shields.io/badge/FastAPI-0.162-009688) ![mcp](https://img.shields.io/badge/MCP-FastMCP-4.1-ff69b4)

---

## What it does

- **Web editor** — build rooms, place hotspots, mark blocked space, wire doors
  and puzzles, edit dialog trees and cutscene timelines, author events, manage
  assets.
- **Pygame runtime** — launch and playtest the game immediately from the
  editor; the engine reads the same `project.json` the editor writes.
- **MCP server** — exposes the entire editor as tools any MCP client (Claude
  Desktop, Cursor, Antigravity, custom agents) can call.
- **AI layer** — Gemini VLM reads room backgrounds through a coordinate grid
  overlay to detect props and place item icons at pixel-accurate positions;
  generates branching dialog and cutscenes; generates pixel art (local Jetson
  SD, Sprite Fusion, or Gemini image models) and sound effects.
- **Sprite slicer** — CV segmentation of sprite sheets into transparent frames
  plus Gemini-driven animation/direction mapping.

### The engine is generic

AdventureForge is **not** a Sam & Max clone with the names swapped. The
project manifest describes the cast, the world and the logic:

- **Characters** — a roster of `player`, `companion` and `npc` entries, each
  with its own sprite, name, colour, dialogue tree and follow settings. Any
  number of companions can trail the player.
- **Collision** — rooms carry `colliders` (rectangles and polygons). Characters
  cannot walk through walls or furniture; they slide along them instead of
  stopping dead, and say so when they cannot reach a hotspot.
- **Events** — one trigger/action system for the whole game
  (`on_game_start`, `on_enter_room`, `on_flag_set`, `on_item_pickup`,
  `on_hotspot_use`, `on_dialog_end`) instead of trigger fields scattered
  across cutscenes and hotspots.

Legacy projects using `player_sprite` / `partner_sprite` keep working: the
runtime derives a roster from them automatically.

---

## Quick start

```bash
git clone https://github.com/acnimatic3722/adventure-forge.git
cd adventure-forge

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # add your API keys (optional but unlocks AI features)

python3 app.py            # http://127.0.0.1:8780
```

The editor works without any API keys — you just lose the AI-assisted
features. Run `python3 forge_cli.py` for the terminal agent, or
`python3 forge_cli.py "add a brass key to the reception room"`.

### Pygame runtime

The editor can launch the runtime directly (`POST /api/play`). To run it
standalone:

```bash
python3 engine_pygame.py --room reception
python3 engine_pygame.py --cutscene intro
```

On a headless box, point `DISPLAY` at an X server (the Docker image ships
Xvfb).

---

## MCP setup

Add to your MCP client config (e.g. `claude_desktop_config.json`,
`.cursor/mcp.json`, or `mcp_config.json`):

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

The server is built on [FastMCP](https://github.com/jlowin/fastmcp), so tool
schemas are generated from real type hints and docstrings rather than
hand-written.

See [`README_MCP.md`](README_MCP.md) for the full tool catalogue, resources and
prompt templates.

---

## Layout

```
adventure_forge/
├── app.py                  # FastAPI web editor (routes + static hosting)
├── engine_pygame.py        # Pygame runtime — reads project.json
├── engine_geometry.py      # Collision maths (pure, no Pygame)
├── engine_characters.py    # Character roster model (pure)
├── engine_events.py        # Event/trigger model (pure)
├── config.py               # All paths, env vars, .env loading, validation
├── mcp_server.py           # FastMCP server (tools, resources, prompts)
├── forge_cli.py            # Terminal AI agent
├── tools/                  # The 86 tools, grouped by domain
│   ├── _core.py            # Shared internals: persistence, assets, runtime state
│   ├── project.py          # Project + Pygame launch/stop
│   ├── rooms.py            # Rooms, world map and collision geometry
│   ├── characters.py       # Character roster
│   ├── events.py           # Event triggers and actions
│   ├── hotspots.py         # Props, NPCs, doors, locks
│   ├── items.py            # Inventory and usage links
│   ├── puzzles.py          # Rules and flag dependencies
│   ├── dialogs.py          # Branching dialog trees
│   ├── cutscenes.py        # Cinematic timelines
│   ├── sprites.py          # Animation sequences and roles
│   ├── assets.py           # Asset library, background remover, pixelizer
│   ├── media.py            # Sound/image search + AI generation
│   ├── vlm.py              # Gemini vision: prop detection, item placement
│   └── agent.py            # LLM agent loop (NVIDIA NIM / Gemini)
├── sprite_slicer/          # CV sprite-sheet slicing + VLM animation mapping
├── static/                 # Editor UI (index.html, generator.html)
├── data/
│   ├── project.json        # The game. Single source of truth.
│   └── assets/             # backgrounds, items, sprites, sounds, music
└── tests/                  # pytest suite (188 tests) + a Playwright UI smoke test
```

### The project file

`data/project.json` is the single source of truth. The editor, the MCP tools
and the Pygame runtime all read and write it:

```jsonc
{
  "title": "The Hotel That Forgot Tomorrow",
  "start_room": "reception",
  "player_character": "detective",
  "characters": {
    "detective": {
      "name": "Detective Vex", "sprite": "vex", "role": "player",
      "color": [240, 200, 80], "scale": 0, "dialog_id": ""
    },
    "sidekick": {
      "name": "Bibi", "sprite": "bibi", "role": "companion",
      "follow": true, "follow_distance": 130, "follow_speed": 245
    }
  },
  "rooms": [{
    "id": "reception", "name": "office", "map_x": 133, "map_y": 181,
    "background": "/assets/backgrounds/lobby.png",
    "player_start": {"x": 850, "y": 594},
    "walkable_polygon": [],
    "colliders": [
      {"id": "desk", "type": "rect", "x": 400, "y": 380, "w": 260, "h": 60}
    ],
    "hotspots": []
  }],
  "events": [
    {
      "id": "ev_intro", "name": "Arrival", "once": true, "priority": 0,
      "trigger": {"type": "on_enter_room", "target": "reception"},
      "actions": [{"type": "play_cutscene", "value": "intro"}]
    }
  ],
  "items": [], "puzzles": [], "dialogs": [], "cutscenes": [],
  "sprites": {}
}
```

Legacy `player_sprite` / `partner_sprite` / `partner_dialog_id` keys are still
honoured when `characters` is absent — the runtime derives a two-character
roster from them.

---

## Configuration

Every path and setting is overridable through the environment (see
`.env.example`). `ADVENTURE_FORGE_*` variables take effect at runtime.

| Variable | Default | Purpose |
|---|---|---|
| `ADVENTURE_FORGE_API_KEY` | *(unset)* | Enables `X-API-Key` auth on mutating endpoints |
| `ADVENTURE_FORGE_SECRET_KEY` | `dev-secret-change-in-production` | Session secret |
| `ADVENTURE_FORGE_HOST` / `_PORT` | `0.0.0.0` / `8780` | Bind address |
| `ADVENTURE_FORGE_DATA_DIR` | `<repo>/data` | Point the whole app at a different data directory (used by the test suite) |
| `ADVENTURE_FORGE_SPRITE_SLICER_PATH` | `<repo>/sprite_slicer` | Sprite slicer location |
| `ADVENTURE_FORGE_JETSON_MODELS_DIR` | `/home/x/jetson-containers/data/models` | Local diffusion models |
| `ADVENTURE_FORGE_SD_CPP_DIR` | `/home/x/jetson-containers/data/stable-diffusion.cpp` | stable-diffusion.cpp build |
| `GEMINI_API_KEY` | — | VLM, dialog/cutscene generation, image gen |
| `SERP_API_KEY` | — | Google Images search |
| `FREESOUND_API_KEY` | — | Sound effect search |
| `SPRITE_FUSION_API_KEY` | — | Pixel art generation |
| `NVIDIA_API_KEY` | — | NVIDIA NIM agent |
| `HF_TOKEN` | — | Hugging Face Hub |

`.env` is read from the project root first, then the parent directory as a
fallback. Real environment variables always win over file values.

---

## Testing

```bash
source .venv/bin/activate
pytest                          # 188 tests
pytest --cov=tools --cov=config # with coverage
```

The suite runs against a temporary project directory — it never touches your
real `data/project.json`.

There is also a headless browser smoke test that drives the real editor UI
(collision tool, character roster, events tab, save round-trip) against a
throwaway data directory:

```bash
pip install playwright
python3 tests/ui_smoke.py
```

It needs a local Chrome (`/usr/bin/google-chrome-stable` by default).

---

## Docker

```bash
docker build -t adventure-forge .
docker run -p 8780:8780 -v $(pwd)/data:/app/data adventure-forge
```

Multi-stage build: `base` → `python-deps` → `app`, plus `jetson` (CUDA
stable-diffusion.cpp) and `dev` targets. Runs as a non-root user with a
`/health` endpoint for orchestration.

---

## License

No license file yet — add one (MIT, Apache-2.0, …) before you want others to
reuse the code. Until then, all rights reserved by default.

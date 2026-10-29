# AdventureForge — Refactoring Notes

This document records the work done to turn the original one-night prototype
into a maintainable, deployable project. It replaces the earlier summary,
which described intentions rather than the final state.

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
- All 68 tools, 6 resources and 3 prompt templates register correctly.
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

**Result: 83 passed, 0 failed** (26% statement coverage over `tools/`,
`config/` and `sprite_slicer/`; the untested bulk is network-bound AI code).

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

- `static/index.html` is 6,112 lines in one file — worth splitting into ES
  modules, best done separately from behavioural work.
- `app.py` keeps its own VLM *preview* endpoints (`/api/vlm/describe-prop`,
  `/api/vlm/generate-dialog`, `/api/vlm/generate-cutscene`). They return JSON
  for the editor UI instead of writing to `project.json`, so they are not
  duplicates of the MCP tools, but the prompts overlap.
- No license file yet.
- Coverage is concentrated on the deterministic tool layer; the AI/network
  paths need integration tests against a running server.

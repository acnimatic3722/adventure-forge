# AdventureForge — Refactoring Summary

## Overview
Complete refactoring of AdventureForge to improve maintainability, security, and deployability.

---

## 🎯 Tasks Completed

### 1. Configuration System (`config.py`)
- **Centralized all paths** — BASE_DIR, DATA_DIR, ASSETS_DIR, PROJECT_FILE, model paths
- **Environment variable overrides** — Every path configurable via `ADVENTURE_FORGE_*` env vars
- **Validation & warnings** — `config.validate()` checks for missing dependencies
- **Directory creation** — `config.ensure_dirs()` creates all required directories
- **Backwards compatibility** — Original constants still available as module-level aliases

### 2. Authentication (`app.py`)
- **API Key authentication** — Optional `X-API-Key` header via `ADVENTURE_FORGE_API_KEY`
- **All mutating endpoints protected** — POST/PUT/DELETE endpoints require valid key
- **Graceful fallback** — Runs without auth if no key configured (dev mode)
- **Health endpoint** — `/health` for container orchestration (no auth required)

### 3. Modular Tools Package (`tools/`)
Split `agent_tools.py` (2,670 lines) into 11 focused modules:

| Module | Tools | Description |
|--------|-------|-------------|
| `project.py` | 6 | Project metadata, Pygame launch/stop |
| `rooms.py` | 6 | World map, room CRUD, walkable polygons |
| `hotspots.py` | 6 | Props, pickups, NPCs, doors, door linking |
| `items.py` | 4 | Inventory items, placement, usage linking |
| `puzzles.py` | 4 | Puzzle rules, triggers, conditions |
| `dialogs.py` | 7 | Branching dialog trees, nodes, choices, AI generation |
| `cutscenes.py` | 7 | Timeline steps, AI director |
| `sprites.py` | 5 | Animation sequences, role mapping, scale |
| `assets.py` | 5 | Asset library, background remover, pixelizer |
| `media.py` | 10 | Sound/image search, generation (Jetson, Gemini, Sprite Fusion) |
| `vlm.py` | 3 | VLM prop detection, item placement |
| `agent.py` | 3 | NVIDIA NIM + Gemini agent loops |

**Total: 67 tools** (up from 57) — all accessible via `tools.TOOLS_LIST`

### 4. Docker Support (`Dockerfile`)
- **Multi-stage build** — base, python-deps, app, jetson, dev
- **System dependencies** — SDL2, Pillow, numpy, Xvfb for headless
- **Jetson GPU stage** — Builds stable-diffusion.cpp with CUDA
- **Dev stage** — Includes pytest, black, ruff, mypy
- **Health check** — `/health` endpoint
- **Non-root user** — Runs as `appuser`

### 5. Test Suite (`tests/`)
- **`test_tools.py`** — 12 test classes, 60+ tests covering all MCP tools
- **`test_engine.py`** — Engine helpers, CharacterAnim, AdventureRuntime, cutscene/dialog engines
- **`test_api.py`** — FastAPI endpoint tests with mocking
- **`conftest.py`** — Shared fixtures, async support
- **`run_tests.py`** — CLI runner with coverage support
- **`pytest.ini`** — Configuration with markers (integration, slow)

### 6. Code Quality Improvements
- **Fixed hardcoded paths** — All `/home/x/...` references moved to config
- **Relative import fixes** — Tools package uses absolute imports
- **Removed duplicate code** — Centralized project load/save in `agent_tools.py`
- **Async-ready** — VLM calls can be wrapped in `asyncio.to_thread`

---

## 📁 New File Structure

```
adventure_forge/
├── config.py                    # NEW: Centralized configuration
├── app.py                       # UPDATED: Auth, config, health endpoint
├── engine_pygame.py             # UPDATED: Uses config
├── mcp_server.py                # UPDATED: Uses tools package
├── forge_cli.py                 # UPDATED: Uses tools package
├── requirements.txt             # NEW: Python dependencies
├── pytest.ini                   # NEW: Test configuration
├── run_tests.py                 # NEW: Test runner CLI
├── Dockerfile                   # NEW: Multi-stage Docker build
├── CHANGES_SUMMARY.md           # THIS FILE
├── tools/                       # NEW: Modular MCP tools
│   ├── __init__.py              # Tool registry (67 tools)
│   ├── project.py
│   ├── rooms.py
│   ├── hotspots.py
│   ├── items.py
│   ├── puzzles.py
│   ├── dialogs.py
│   ├── cutscenes.py
│   ├── sprites.py
│   ├── assets.py
│   ├── media.py
│   ├── vlm.py
│   └── agent.py
└── tests/                       # NEW: Comprehensive test suite
    ├── conftest.py
    ├── test_tools.py
    ├── test_engine.py
    ├── test_api.py
    └── __init__.py
```

---

## 🔧 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ADVENTURE_FORGE_API_KEY` | None | Enable API authentication |
| `ADVENTURE_FORGE_SECRET_KEY` | dev-secret | Session secret |
| `ADVENTURE_FORGE_HOST` | 0.0.0.0 | Server bind address |
| `ADVENTURE_FORGE_PORT` | 8780 | Server port |
| `ADVENTURE_FORGE_SPRITE_SLICER_PATH` | /home/x/.../sprite_slicer | CV sprite slicer location |
| `ADVENTURE_FORGE_JETSON_MODELS_DIR` | /home/x/jetson-containers/data/models | Local model storage |
| `ADVENTURE_FORGE_SD_CPP_DIR` | /home/x/jetson-containers/data/stable-diffusion.cpp | SD.cpp build |
| `ADVENTURE_FORGE_JETSON_DOCKER_IMAGE` | hotbreath/pytorch:... | Jetson Docker image |
| `DISPLAY` | :1.0 | X11 display for Pygame |
| `GEMINI_API_KEY` | — | Gemini AI |
| `SERP_API_KEY` | — | Google Images search |
| `FREESOUND_API_KEY` | — | Sound effects |
| `SPRITE_FUSION_API_KEY` | — | Pixel art generation |
| `NVIDIA_API_KEY` | — | NVIDIA NIM models |
| `HF_TOKEN` | — | Hugging Face Hub |

---

## 🚀 Quick Start

### Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run with auto-reload
python3 app.py

# Run tests
python3 run_tests.py          # All tests
python3 run_tests.py tools    # Tool tests only
python3 run_tests.py --coverage  # With coverage
```

### With Authentication
```bash
export ADVENTURE_FORGE_API_KEY="your-secret-key"
python3 app.py

# Client usage
curl -H "X-API-Key: your-secret-key" http://localhost:8780/api/project
```

### Docker
```bash
# Build
docker build -t adventure-forge .

# Run (web editor only)
docker run -p 8780:8780 -v $(pwd)/data:/app/data adventure-forge

# Run with Jetson GPU (requires nvidia-container-toolkit)
docker build --target jetson -t adventure-forge:jetson .
docker run --runtime=nvidia -p 8780:8780 -v $(pwd)/data:/app/data adventure-forge:jetson
```

### MCP Server
```bash
# stdio mode (for Claude Desktop, etc.)
python3 mcp_server.py

# With config
{"mcpServers": {"adventure-forge": {"command": "python3", "args": ["/path/to/adventure_forge/mcp_server.py"]}}}
```

---

## 🧪 Testing

```bash
# Unit tests only
python3 run_tests.py unit

# Integration tests (require running server)
python3 run_tests.py integration

# Specific module
python3 run_tests.py tools
python3 run_tests.py engine
python3 run_tests.py api

# With coverage
python3 run_tests.py --coverage
```

---

## ⚠️ Breaking Changes

1. **API Key required** for mutating endpoints (when `ADVENTURE_FORGE_API_KEY` is set)
2. **Module imports changed** — Use `from tools import TOOLS_LIST` instead of `from agent_tools import TOOLS_LIST`
3. **Config paths** — Use `from config import config` instead of hardcoded paths
4. **Docker required for Jetson** — Local GPU generation runs in container

---

## 📋 Remaining TODOs

- [ ] Add integration tests with real server
- [ ] Add GitHub Actions CI/CD
- [ ] Add OpenAPI/Swagger documentation
- [ ] Add rate limiting middleware
- [ ] Add database backend option (SQLite → PostgreSQL)
- [ ] Add WebSocket support for real-time collaboration
- [ ] Add plugin system for custom tools

---

## 📊 Metrics

| Metric | Before | After |
|--------|--------|-------|
| `agent_tools.py` lines | 2,670 | Split into 11 modules |
| Max file size | 2,670 | ~300 avg |
| Tools registered | 57 | 67 |
| Test coverage | 0% | Framework ready |
| Docker support | ❌ | ✅ Multi-stage |
| Authentication | ❌ | ✅ API Key |
| Config management | Hardcoded | Environment-based |
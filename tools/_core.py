"""
AdventureForge — Shared Core Internals

Project persistence, asset path resolution, API key discovery and runtime
state live here so every tool module imports from exactly one place.

This module replaces the old monolithic `agent_tools.py`, which held a full
duplicate copy of every tool function alongside the `tools/` package.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from config import config

# ---- Paths -------------------------------------------------------------
BASE_DIR = config.BASE_DIR
DATA_DIR = config.DATA_DIR
ASSETS_DIR = config.ASSETS_DIR
PROJECT_FILE = config.PROJECT_FILE
SPRITES_DIR = config.SPRITES_DIR

# ---- Local model paths (Jetson / stable-diffusion.cpp) -----------------
LOCAL_SD15_GGUF = config.get_sd15_model_path("q8")
LOCAL_SD15_GGUF_Q4 = config.get_sd15_model_path("q4")
LOCAL_REDMOND_LORA = config.get_lora_path(config.REDMOND_LORA)
LOCAL_LUCASARTS_LORA = config.get_lora_path(config.LUCASARTS_LORA)
LOCAL_IRIS_GGUF = config.get_iris_model_path()
LOCAL_IRIS_TE = config.get_iris_te_path()

# ---- Shared runtime state ----------------------------------------------
# The live Pygame playtest process. Tools that need to read or replace it
# must go through this module so every caller sees the same handle.
PYGAME_PROC: subprocess.Popen | None = None


# ============================================================================
# Project persistence
# ============================================================================

def _load_proj() -> dict[str, Any]:
    """Load the project manifest, normalising collection types.

    Paths are resolved through `config` at call time (not captured at import
    time) so runtime overrides and test fixtures take effect.
    """
    project_file = config.PROJECT_FILE
    if not project_file.exists():
        return {
            "title": "New Adventure",
            "start_room": "",
            "rooms": [],
            "items": [],
            "puzzles": [],
            "dialogs": [],
            "cutscenes": [],
            "sprites": {}
        }
    data = json.loads(project_file.read_text())
    for k in ("rooms", "items", "puzzles", "dialogs", "cutscenes"):
        if k not in data or not isinstance(data[k], list):
            data[k] = []
    if "sprites" not in data or not isinstance(data["sprites"], dict):
        data["sprites"] = {}
    return data


def _save_proj(data: dict[str, Any]) -> None:
    """Write the project manifest back to disk."""
    config.PROJECT_FILE.write_text(json.dumps(data, indent=2))


# ============================================================================
# Asset helpers
# ============================================================================

def _resolve_asset(web_url: str) -> Path:
    """Resolve a web asset URL to a path inside the assets directory.

    Raises ValueError if the resolved path escapes ASSETS_DIR (path traversal).
    """
    clean = web_url.split("?")[0].lstrip("/")
    if not clean.startswith("assets/"):
        clean = "assets/" + clean
    target = (config.DATA_DIR / clean).resolve()
    assets_root = config.ASSETS_DIR.resolve()
    if not target.is_relative_to(assets_root):
        raise ValueError("Forbidden asset path")
    return target


def _normalize_vlm_meta(meta: dict[str, Any], fallback_name: str) -> dict[str, Any]:
    """Normalise legacy list-shaped VLM sprite metadata into a dict."""
    vlm = meta.get("vlm")
    if isinstance(vlm, list):
        merged_anims = []
        char_names = []
        for item in vlm:
            if isinstance(item, dict):
                cname = item.get("character_name", "")
                if cname:
                    char_names.append(str(cname))
                for anim in item.get("animations", []):
                    if isinstance(anim, dict):
                        merged_anims.append(anim)
        meta["vlm"] = {
            "character_name": " & ".join(char_names[:3]) if char_names else fallback_name,
            "animations": merged_anims
        }
    elif not isinstance(vlm, dict):
        meta["vlm"] = {"character_name": fallback_name, "animations": []}
    return meta


# ============================================================================
# Environment / credentials
# ============================================================================

def load_env(env_path: "str | Path | None" = None) -> None:
    """Load .env values into os.environ (see `config.Config.load_env`)."""
    config.load_env(env_path)


def _get_api_keys() -> dict[str, str]:
    """Retrieve API keys from the environment / .env files."""
    return config.get_api_keys()

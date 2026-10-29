#!/usr/bin/env python3
"""
AdventureForge — WebUI Point-and-Click Game Editor & Pygame Launcher
Run: python3 app.py   (http://127.0.0.1:8780)
"""

import os
import sys
import io
import base64
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Depends, Header
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

# Import config first
from config import config

# Import our CV + VLM sprite slicer helpers
sys.path.insert(0, str(config.SPRITE_SLICER_PATH))
from slice_sprites import segment_sprites, create_annotated_image, call_vlm_analyzer, load_env

from PIL import Image, ImageDraw
import numpy as np
from google import genai
from google.genai import types

# Use config for all paths
BASE_DIR = config.BASE_DIR
STATIC_DIR = config.STATIC_DIR
DATA_DIR = config.DATA_DIR
ASSETS_DIR = config.ASSETS_DIR
PROJECT_FILE = config.PROJECT_FILE

app = FastAPI(title="AdventureForge Editor")

# Track active Pygame process
pygame_proc: subprocess.Popen | None = None

# Authentication
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Depends(api_key_header)) -> str:
    """Verify API key if configured."""
    if config.API_KEY is None:
        return "no-auth-configured"
    if api_key != config.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return api_key


def get_pygame_env() -> dict[str, str]:
    """Get environment for Pygame subprocess with proper DISPLAY."""
    env = os.environ.copy()
    if "DISPLAY" not in env:
        env["DISPLAY"] = config.DISPLAY
    if "XAUTHORITY" not in env and config.XAUTHORITY:
        env["XAUTHORITY"] = config.XAUTHORITY
    return env


@app.middleware("http")
async def disable_asset_caching(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/assets/") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        if "etag" in response.headers:
            del response.headers["etag"]
        if "last-modified" in response.headers:
            del response.headers["last-modified"]
    return response


def normalize_vlm_data(vlm_res: Any, fallback_name: str = "sprite") -> dict[str, Any]:
    """Ensure VLM output is always a single dict with 'character_name' and 'animations'."""
    if isinstance(vlm_res, list):
        merged_anims = []
        char_names = []
        for item in vlm_res:
            if isinstance(item, dict):
                cname = item.get("character_name", "")
                if cname:
                    char_names.append(str(cname))
                for anim in item.get("animations", []):
                    if isinstance(anim, dict):
                        merged_anims.append(anim)
        return {
            "character_name": " & ".join(char_names[:3]) if char_names else fallback_name,
            "animations": merged_anims
        }
    if isinstance(vlm_res, dict):
        if "animations" not in vlm_res or not isinstance(vlm_res["animations"], list):
            vlm_res["animations"] = []
        if "character_name" not in vlm_res:
            vlm_res["character_name"] = fallback_name
        return vlm_res
    return {"character_name": fallback_name, "animations": []}


def load_project() -> dict[str, Any]:
    if not PROJECT_FILE.exists():
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
    data = json.loads(PROJECT_FILE.read_text())
    if "dialogs" not in data or not isinstance(data["dialogs"], list):
        data["dialogs"] = []
    if "cutscenes" not in data or not isinstance(data["cutscenes"], list):
        data["cutscenes"] = []
    return data


def save_project(data: dict[str, Any]) -> None:
    PROJECT_FILE.write_text(json.dumps(data, indent=2))


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/generator")
@app.get("/playground")
def generator_page():
    return FileResponse(STATIC_DIR / "generator.html")


@app.get("/api/project")
def get_project():
    return load_project()


@app.post("/api/project")
async def update_project(payload: dict[str, Any], api_key: str = Depends(verify_api_key)):
    existing = load_project()
    if "sprites" not in payload or not isinstance(payload["sprites"], dict):
        payload["sprites"] = {}
    for k, v in existing.get("sprites", {}).items():
        if k not in payload["sprites"]:
            payload["sprites"][k] = v
    if "partner_sprite" not in payload and "partner_sprite" in existing:
        payload["partner_sprite"] = existing["partner_sprite"]
    if "dialogs" not in payload:
        payload["dialogs"] = existing.get("dialogs", [])
    if "cutscenes" not in payload:
        payload["cutscenes"] = existing.get("cutscenes", [])
    save_project(payload)
    return {"status": "ok"}


@app.post("/api/upload/{category}")
async def upload_asset(category: str, file: UploadFile = File(...), api_key: str = Depends(verify_api_key)):
    if category not in ("backgrounds", "items", "sprites", "sounds", "music"):
        raise HTTPException(400, "Invalid asset category")
    target_dir = ASSETS_DIR / category
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_name = "".join(c for c in (file.filename or "asset.png") if c.isalnum() or c in "._-").lower()
    if not safe_name:
        safe_name = "upload.png"
    dest = target_dir / safe_name
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    web_path = f"/assets/{category}/{safe_name}"
    return {"status": "ok", "url": web_path, "filename": safe_name}


@app.post("/api/sprites/slice")
async def slice_uploaded_spritesheet(
    file: UploadFile = File(None),
    existing_sheet: str = Form(""),
    sprite_id: str = Form("hero"),
    use_vlm: bool = Form(True),
    hint: str = Form(""),
    api_key: str = Depends(verify_api_key)
):
    sprites_dir = ASSETS_DIR / "sprites"
    sprites_dir.mkdir(parents=True, exist_ok=True)

    clean_id = "".join(c for c in sprite_id if c.isalnum() or c == "_").lower() or "sprite"

    if file and file.filename:
        sheet_path = sprites_dir / f"{clean_id}.png"
        with sheet_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    elif existing_sheet:
        rel = existing_sheet.lstrip("/")
        sheet_path = DATA_DIR / rel
        if not sheet_path.exists():
            raise HTTPException(404, f"Sheet not found: {existing_sheet}")
    else:
        raise HTTPException(400, "Provide a file or existing_sheet")

    orig_img, boxes, bg_color = segment_sprites(sheet_path)
    frames_dir = sprites_dir / f"{clean_id}_frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    frame_urls = []
    for idx, b in enumerate(boxes):
        crop = orig_img.crop((b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"])).convert("RGBA")
        if bg_color is not None:
            arr = np.array(crop)
            diff = np.sum(np.abs(arr[:, :, :3].astype(int) - bg_color.astype(int)), axis=2)
            arr[diff < 20, 3] = 0
            crop = Image.fromarray(arr, "RGBA")
        fname = f"frame_{idx:03d}.png"
        crop.save(frames_dir / fname)
        frame_urls.append(f"/assets/sprites/{clean_id}_frames/{fname}")

    if use_vlm and len(boxes) > 0:
        try:
            annotated = create_annotated_image(orig_img, boxes)
            vlm_res = call_vlm_analyzer(annotated, boxes, prompt_hint=hint or None)
        except Exception as e:
            vlm_res = {
                "character_name": clean_id,
                "animations": [
                    {"name": "idle_down", "fps": 8.0, "loop": False, "indices": [0]},
                    {"name": "walk_right", "fps": 8.0, "loop": True, "indices": list(range(min(6, len(boxes))))}
                ],
                "error": str(e)
            }
    else:
        vlm_res = {
            "character_name": clean_id,
            "animations": [
                {"name": "idle_down", "fps": 8.0, "loop": False, "indices": [0]},
                {"name": "walk_right", "fps": 8.0, "loop": True, "indices": list(range(min(6, len(boxes))))}
            ]
        }

    vlm_res = normalize_vlm_data(vlm_res, fallback_name=clean_id)

    meta_payload = {
        "vlm": vlm_res,
        "boxes": boxes,
        "char_name": clean_id,
        "frame_urls": frame_urls
    }
    meta_file = sprites_dir / f"{clean_id}_slicer.json"
    meta_file.write_text(json.dumps(meta_payload, indent=2))

    # Register in project.json
    proj = load_project()
    if "sprites" not in proj:
        proj["sprites"] = {}
    proj["sprites"][clean_id] = {
        "id": clean_id,
        "name": vlm_res.get("character_name", clean_id),
        "sheet": f"/assets/sprites/{sheet_path.name}",
        "frames_dir": f"/assets/sprites/{clean_id}_frames",
        "scale": 3.0,
        "metadata_file": f"/assets/sprites/{clean_id}_slicer.json"
    }
    save_project(proj)

    return {
        "status": "ok",
        "sprite_id": clean_id,
        "frame_count": len(boxes),
        "frame_urls": frame_urls,
        "metadata": meta_payload
    }


@app.get("/api/sprites/{sprite_id}")
def get_sprite_details(sprite_id: str):
    proj = load_project()
    sp = proj.get("sprites", {}).get(sprite_id)
    if not sp:
        raise HTTPException(404, "Sprite not found")
    meta_rel = sp.get("metadata_file", "").lstrip("/")
    meta_path = DATA_DIR / meta_rel
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    if "vlm" in meta:
        meta["vlm"] = normalize_vlm_data(meta["vlm"], fallback_name=sprite_id)
    frames_rel = sp.get("frames_dir", "").lstrip("/")
    frames_dir = DATA_DIR / frames_rel
    frame_urls = []
    if frames_dir.exists():
        for p in sorted(frames_dir.glob("*.png")):
            frame_urls.append(f"/{frames_rel}/{p.name}")
    return {
        "sprite": sp,
        "metadata": meta,
        "frame_urls": frame_urls
    }


@app.post("/api/sprites/{sprite_id}/animations")
async def save_sprite_animations(sprite_id: str, payload: dict[str, Any], api_key: str = Depends(verify_api_key)):
    proj = load_project()
    sp = proj.get("sprites", {}).get(sprite_id)
    if not sp:
        raise HTTPException(404, "Sprite not found")
    if "scale" in payload:
        sp["scale"] = float(payload["scale"])
    if "anim_roles" in payload:
        sp["anim_roles"] = payload["anim_roles"]
    save_project(proj)

    meta_rel = sp.get("metadata_file", "").lstrip("/")
    meta_path = DATA_DIR / meta_rel
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {"vlm": {}}
    meta["vlm"] = normalize_vlm_data(meta.get("vlm"), fallback_name=sprite_id)
    if "animations" in payload:
        meta["vlm"]["animations"] = payload["animations"]
    if "anim_roles" in payload:
        meta["anim_roles"] = payload["anim_roles"]
    meta_path.write_text(json.dumps(meta, indent=2))
    return {"status": "ok"}


@app.get("/api/assets")
def list_all_assets():
    """Return all uploaded image assets across items, backgrounds, sprites, and sliced frames."""
    assets = []
    if not ASSETS_DIR.exists():
        return {"assets": assets}

    for path in sorted(ASSETS_DIR.rglob("*")):
        if not path.is_file():
            continue
        suf = path.suffix.lower()
        if suf not in (".png", ".jpg", ".jpeg", ".webp", ".mp3", ".wav", ".ogg"):
            continue
        if ".orig." in path.name:
            continue
        rel_to_data = path.relative_to(DATA_DIR)
        web_url = "/" + str(rel_to_data).replace("\\", "/")
        parts = path.relative_to(ASSETS_DIR).parts
        top_cat = parts[0] if len(parts) > 0 else "other"
        if top_cat == "sprites" and len(parts) > 1 and parts[1].endswith("_frames"):
            cat = "frames"
        else:
            cat = top_cat

        is_audio = suf in (".mp3", ".wav", ".ogg")
        w, h = 0, 0
        if not is_audio:
            try:
                with Image.open(path) as im:
                    w, h = im.size
            except Exception:
                pass

        orig_backup = path.with_name(f"{path.stem}.orig{path.suffix}")
        assets.append({
            "url": web_url,
            "name": path.name,
            "category": cat,
            "width": w,
            "height": h,
            "is_audio": is_audio,
            "has_backup": orig_backup.exists()
        })
    return {"assets": assets}


def _resolve_safe_asset_path(web_url: str) -> Path:
    clean = web_url.split("?")[0].lstrip("/")
    if not clean.startswith("assets/"):
        raise HTTPException(400, "Invalid asset path")
    target = (DATA_DIR / clean).resolve()
    if not str(target).startswith(str(ASSETS_DIR.resolve())):
        raise HTTPException(403, "Forbidden asset path")
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "Asset file not found")
    return target


@app.post("/api/assets/save-edited")
async def save_edited_asset(payload: dict[str, Any], api_key: str = Depends(verify_api_key)):
    """Save a background-removed PNG image back to disk (creating a .orig backup first)."""
    web_url = payload.get("url", "")
    data_url = payload.get("image_data", "")
    trim = bool(payload.get("trim", False))
    target = _resolve_safe_asset_path(web_url)

    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    raw_bytes = base64.b64decode(data_url)
    img = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")

    if trim:
        bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)

    # Save backup of original if not already backed up
    orig_backup = target.with_name(f"{target.stem}.orig{target.suffix}")
    if not orig_backup.exists():
        shutil.copy2(target, orig_backup)

    img.save(target, format="PNG")
    # If Pygame runtime is currently open, hot-restart it so edited assets update live
    if pygame_proc and pygame_proc.poll() is None:
        await launch_pygame({})
    return {
        "status": "ok",
        "url": web_url.split("?")[0],
        "width": img.width,
        "height": img.height,
        "has_backup": True
    }


@app.post("/api/assets/restore-original")
async def restore_original_asset(payload: dict[str, Any], api_key: str = Depends(verify_api_key)):
    """Restore an asset from its .orig backup."""
    web_url = payload.get("url", "")
    target = _resolve_safe_asset_path(web_url)
    orig_backup = target.with_name(f"{target.stem}.orig{target.suffix}")
    if not orig_backup.exists():
        raise HTTPException(404, "No original backup found for this asset")
    shutil.copy2(orig_backup, target)
    if pygame_proc and pygame_proc.poll() is None:
        await launch_pygame({})
    return {"status": "ok", "url": web_url.split("?")[0]}


@app.post("/api/assets/delete")
async def delete_asset_file(payload: dict[str, Any], api_key: str = Depends(verify_api_key)):
    """Delete an asset file (and its .orig backup if present)."""
    web_url = payload.get("url", "")
    target = _resolve_safe_asset_path(web_url)
    orig_backup = target.with_name(f"{target.stem}.orig{target.suffix}")
    target.unlink(missing_ok=True)
    if orig_backup.exists():
        orig_backup.unlink(missing_ok=True)
    return {"status": "ok"}


@app.post("/api/vlm/describe-prop")
async def vlm_describe_prop(payload: dict[str, Any], api_key: str = Depends(verify_api_key)):
    """Use Gemini VLM to inspect a prop's bounding box in the room (or its sprite) and generate a 'Look at' line."""
    load_env()
    client = genai.Client()

    room_name = payload.get("room_name", "Adventure Room")
    room_bg = payload.get("room_background", "")
    prop_name = payload.get("prop_name", "")
    prop_icon = payload.get("prop_icon", "")
    rect = payload.get("rect") or {"x": 100, "y": 100, "w": 120, "h": 120}

    contents: list[Any] = []

    # 1. If the prop has its own uploaded sprite/icon, include it
    if prop_icon:
        try:
            icon_path = _resolve_safe_asset_path(prop_icon)
            contents.append(Image.open(icon_path).convert("RGB"))
        except Exception:
            pass

    # 2. If the room has a background, crop the hotspot region and also provide a highlighted room overview
    if room_bg:
        try:
            bg_path = _resolve_safe_asset_path(room_bg)
            bg_img = Image.open(bg_path).convert("RGB").resize((1280, 720))
            rx = max(0, min(1279, int(rect.get("x", 0))))
            ry = max(0, min(719, int(rect.get("y", 0))))
            rw = max(16, int(rect.get("w", 100)))
            rh = max(16, int(rect.get("h", 100)))
            x1 = max(0, rx - 15)
            y1 = max(0, ry - 15)
            x2 = min(1280, rx + rw + 15)
            y2 = min(720, ry + rh + 15)

            crop_img = bg_img.crop((x1, y1, x2, y2))
            contents.append(crop_img)

            overview_img = bg_img.copy()
            draw = ImageDraw.Draw(overview_img)
            draw.rectangle([rx, ry, min(1279, rx + rw), min(719, ry + rh)], outline=(255, 40, 40), width=4)
            contents.append(overview_img)
        except Exception:
            pass

    prompt = f"""You are a witty classic LucasArts point-and-click adventure game writer (in the style of Sam & Max / Day of the Tentacle / Monkey Island).
The player is in a room called "{room_name}".
The designer placed a prop hotspot currently labeled "{prop_name}".
{"Look at the close-up cropped image of the prop and the full room image where the prop is highlighted inside a red box." if contents else "Generate a description based on the room and prop name."}

Identify what the object inside the highlighted region is, and write:
1. "suggested_name": A concise 2-4 word display name for this object (e.g. "Dusty Gramophone", "Rain-Streaked Window", "Suspicious Gargoyle").
2. "look_text": A flavorful, witty 1-2 sentence "Look at" dialogue line spoken by the detective protagonist when inspecting this object.
3. "use_text": A short 1 sentence response spoken if the player tries to "Use" it directly without an item.

Return ONLY valid JSON matching:
{{
  "suggested_name": "string",
  "look_text": "string",
  "use_text": "string"
}}"""

    contents.append(prompt)
    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )
    res_data = json.loads(response.text)
    if isinstance(res_data, list) and len(res_data) > 0:
        res_data = res_data[0]
    return res_data


@app.post("/api/vlm/generate-dialog")
async def vlm_generate_dialog(payload: dict[str, Any], api_key: str = Depends(verify_api_key)):
    """Use Gemini LLM to generate a classic LucasArts branching dialog tree."""
    load_env()
    client = genai.Client()

    prompt_hint = payload.get("prompt", "A witty conversation about the mystery in the hotel.")
    npc_name = payload.get("npc_name", "Max")
    dialog_id = payload.get("dialog_id", "dialog_1")
    proj = load_project()
    room_names = [r.get("name", r.get("id", "")) for r in proj.get("rooms", [])]
    item_names = [f"{i.get('name')} ({i.get('id')})" for i in proj.get("items", [])]

    prompt = f"""You are a senior LucasArts adventure game writer (Sam & Max Hit the Road, Day of the Tentacle, Monkey Island).
Create a branching Dialog Tree with ID "{dialog_id}" for a conversation with "{npc_name}".
User prompt / situation: {prompt_hint}
Rooms in game: {", ".join(room_names) or "Hotel Reception, Observatory"}
Items in game: {", ".join(item_names) or "pizza, star_lens"}

Build 3 to 5 connected dialog nodes starting at root_node "root".
Each node has:
- "id": string (e.g. "root", "ask_clues", "joke_branch", "secret_info")
- "speaker": "npc" | "partner" | "player"
- "npc_text": The line spoken when entering this node (1-2 witty sentences).
- "options": array of 2 to 4 player dialogue choices. Each option has:
  - "text": What the player says
  - "reply_text": Immediate witty comeback or answer before moving to next_node
  - "next_node": target node "id", or "__exit__" to end conversation
  - "requires_flag": "" (or optional flag name)
  - "sets_flag": "" (or optional flag name unlocked by this branch)
  - "gives_item": "" (or optional item ID if they hand the player an item)
  - "triggers_cutscene": ""
  - "once": boolean (true for side questions, false for hub navigation or exit)

Always include a way to end the conversation ("next_node": "__exit__").
Return ONLY valid JSON matching:
{{
  "name": "string",
  "npc_name": "{npc_name}",
  "root_node": "root",
  "nodes": [
    {{
      "id": "root",
      "speaker": "npc",
      "npc_text": "string",
      "options": [
        {{
          "text": "string",
          "reply_text": "string",
          "next_node": "string",
          "requires_flag": "",
          "sets_flag": "",
          "gives_item": "",
          "triggers_cutscene": "",
          "once": false
        }}
      ]
    }}
  ]
}}"""

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=[prompt],
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    res_data = json.loads(response.text)
    if isinstance(res_data, list) and len(res_data) > 0:
        res_data = res_data[0]
    return res_data


@app.post("/api/vlm/generate-cutscene")
async def vlm_generate_cutscene(payload: dict[str, Any], api_key: str = Depends(verify_api_key)):
    """Use Gemini LLM to generate a choreographed LucasArts cutscene timeline."""
    load_env()
    client = genai.Client()

    prompt_hint = payload.get("prompt", "Sam and Max walk into the room, look around, and banter about the mystery.")
    room_id = payload.get("room_id", "reception")
    proj = load_project()
    room_ids = [r.get("id", "") for r in proj.get("rooms", [])]

    prompt = f"""You are a LucasArts cutscene director (Sam & Max, Monkey Island).
Create a choreographed cutscene sequence taking place primarily in room "{room_id}" (available rooms: {", ".join(room_ids)}).
User prompt / scene description: {prompt_hint}

Available step types:
1. {{"type": "fade", "effect": "fade_in" | "fade_out" | "flash_white" | "shake", "duration": 0.8}}
2. {{"type": "walk", "actor": "player" | "partner", "x": 300..950, "y": 490..650}}
3. {{"type": "say", "actor": "player" | "partner" | "narrator", "text": "Witty dialogue line", "duration": 3.5}}
4. {{"type": "wait", "duration": 1.0}}
5. {{"type": "play_anim", "actor": "player" | "partner", "anim": "walk_down", "duration": 1.2}}
6. {{"type": "change_room", "room_id": "{room_id}", "x": 600, "y": 560}}
7. {{"type": "set_flag", "flag": "flag_name"}}

Create 5 to 9 cinematic steps that tell a fun mini-scene with movement and banter between "player" (Sam) and "partner" (Max).
Return ONLY valid JSON matching:
{{
  "name": "string",
  "steps": [
    {{
      "type": "fade",
      "effect": "fade_in",
      "duration": 0.8
    }}
  ]
}}"""

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=[prompt],
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    res_data = json.loads(response.text)
    if isinstance(res_data, list) and len(res_data) > 0:
        res_data = res_data[0]
    return res_data


@app.post("/api/play")
async def launch_pygame(payload: dict[str, Any] | None = None, api_key: str = Depends(verify_api_key)):
    global pygame_proc
    if pygame_proc and pygame_proc.poll() is None:
        pygame_proc.terminate()
        try:
            pygame_proc.wait(timeout=2)
        except Exception:
            pygame_proc.kill()

    payload = payload or {}
    room_id = payload.get("room_id")
    cutscene_id = payload.get("cutscene_id")
    dialog_id = payload.get("dialog_id")

    cmd = [sys.executable, str(BASE_DIR / "engine_pygame.py")]
    if room_id:
        cmd.extend(["--room", str(room_id)])
    if cutscene_id:
        cmd.extend(["--cutscene", str(cutscene_id)])
    if dialog_id:
        cmd.extend(["--dialog", str(dialog_id)])

    pygame_proc = subprocess.Popen(cmd, cwd=str(BASE_DIR), env=get_pygame_env())
    return {
        "status": "launched",
        "pid": pygame_proc.pid,
        "room": room_id or "start",
        "cutscene": cutscene_id,
        "dialog": dialog_id
    }


@app.post("/api/stop")
async def stop_pygame(api_key: str = Depends(verify_api_key)):
    global pygame_proc
    if pygame_proc and pygame_proc.poll() is None:
        pygame_proc.terminate()
        return {"status": "stopped"}
    return {"status": "not_running"}


@app.get("/api/agent/tools")
def get_mcp_agent_tools(api_key: str = Depends(verify_api_key)):
    from tools import TOOLS_LIST
    return {
        "server": "adventure-forge-mcp",
        "cli_command": "python3 /home/x/Desktop/IDEAS/adventure_forge/forge_cli.py",
        "mcp_stdio_command": "python3 /home/x/Desktop/IDEAS/adventure_forge/mcp_server.py",
        "tools": [
            {
                "name": fn.__name__,
                "description": (fn.__doc__ or "").strip()
            }
            for fn in TOOLS_LIST
        ]
    }


@app.post("/api/agent/chat")
async def run_mcp_agent_chat(payload: dict[str, Any], api_key: str = Depends(verify_api_key)):
    from tools.agent import run_agent_instruction
    user_msg = (payload.get("message") or "").strip()
    if not user_msg:
        raise HTTPException(400, "Empty message")
    room_id = payload.get("current_room_id") or ""
    include_vision = bool(payload.get("include_room_vision", True))
    history = payload.get("history") or []
    preferred_model = payload.get("model") or ""

    try:
        res = run_agent_instruction(
            user_message=user_msg,
            current_room_id=room_id,
            include_room_vision=include_vision,
            history=history,
            preferred_model=preferred_model
        )
    except Exception as e:
        res = {"reply": f"Agent error: {e}", "tool_calls": [], "project": load_project()}
    if pygame_proc and pygame_proc.poll() is None and res.get("tool_calls"):
        await launch_pygame({"room_id": room_id} if room_id else {})
    return res


@app.get("/api/media/status")
def get_media_status(api_key: str = Depends(verify_api_key)):
    from tools.media import list_available_media_apis
    return list_available_media_apis()


@app.post("/api/media/search-sounds")
def api_search_sounds(payload: dict[str, Any], api_key: str = Depends(verify_api_key)):
    from tools.media import search_and_download_sound_effects
    query = (payload.get("query") or "").strip()
    if not query:
        raise HTTPException(400, "Query cannot be empty")
    return search_and_download_sound_effects(
        query=query,
        category=payload.get("category", "sounds"),
        filename=payload.get("filename", ""),
        min_duration=float(payload.get("min_duration", 0.2)),
        max_duration=float(payload.get("max_duration", 20.0)),
        link_to_room_id=payload.get("link_to_room_id", ""),
        link_to_puzzle_id=payload.get("link_to_puzzle_id", "")
    )


@app.post("/api/media/search-images")
def api_search_images(payload: dict[str, Any], api_key: str = Depends(verify_api_key)):
    from tools.media import search_and_download_images
    query = (payload.get("query") or "").strip()
    if not query:
        raise HTTPException(400, "Query cannot be empty")
    return search_and_download_images(
        query=query,
        category=payload.get("category", "items"),
        filename=payload.get("filename", ""),
        transparent_only=bool(payload.get("transparent_only", False)),
        auto_remove_bg=bool(payload.get("auto_remove_bg", True)),
        link_to_room_id=payload.get("link_to_room_id", ""),
        link_to_item_id=payload.get("link_to_item_id", ""),
        link_to_hotspot_id=payload.get("link_to_hotspot_id", "")
    )


@app.post("/api/media/generate-image")
def api_generate_image(payload: dict[str, Any], api_key: str = Depends(verify_api_key)):
    from tools.media import generate_image_ai
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "Prompt cannot be empty")
    return generate_image_ai(
        prompt=prompt,
        category=payload.get("category", "items"),
        filename=payload.get("filename", ""),
        aspect_ratio=payload.get("aspect_ratio", "1:1"),
        auto_remove_bg=bool(payload.get("auto_remove_bg", True)),
        link_to_room_id=payload.get("link_to_room_id", ""),
        link_to_item_id=payload.get("link_to_item_id", ""),
        link_to_hotspot_id=payload.get("link_to_hotspot_id", "")
    )


@app.post("/api/media/jetson-generate")
def api_jetson_generate(payload: dict[str, Any], api_key: str = Depends(verify_api_key)):
    from tools.media import jetson_generate_image
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "Prompt cannot be empty")
    return jetson_generate_image(
        prompt=prompt,
        category=payload.get("category", "items"),
        filename=payload.get("filename", ""),
        width=int(payload.get("width", 512)),
        height=int(payload.get("height", 512)),
        steps=int(payload.get("steps", 20)),
        cfg_scale=float(payload.get("cfg_scale", 7.0)),
        sampling_method=str(payload.get("sampling_method", "euler_a")),
        model_engine=str(payload.get("model_engine", "sd15")),
        base_model_file=str(payload.get("base_model_file", "")),
        active_loras=payload.get("active_loras"),
        negative_prompt=str(payload.get("negative_prompt", "")),
        seed=int(payload.get("seed", -1)),
        lucasarts_weight=float(payload.get("lucasarts_weight", 0.0)),
        redmond_weight=float(payload.get("redmond_weight", 0.0)),
        pixel_art=bool(payload.get("pixel_art", False)),
        pixel_size=int(payload.get("pixel_size", 32)),
        num_colors=int(payload.get("num_colors", 16)),
        auto_remove_bg=bool(payload.get("auto_remove_bg", False)),
        link_to_room_id=payload.get("link_to_room_id", ""),
        link_to_item_id=payload.get("link_to_item_id", ""),
        link_to_hotspot_id=payload.get("link_to_hotspot_id", "")
    )


@app.get("/api/models/installed")
def api_get_installed_models(api_key: str = Depends(verify_api_key)):
    """Return all locally installed base models, LoRAs, and free disk space."""
    import shutil
    from pathlib import Path

    loras_dir = Path("/home/x/jetson-containers/data/models/loras")
    sd15_dir = Path("/home/x/jetson-containers/data/models/sd15")
    iris_dir = Path("/home/x/jetson-containers/data/models/iris-3b")

    loras = []
    if loras_dir.exists():
        for p in sorted(loras_dir.glob("*.safetensors")):
            sz_mb = round(p.stat().st_size / (1024 * 1024), 1)
            name = p.stem.replace("_", " ").replace("-", " ")
            trigger = ""
            desc = "Stable Diffusion 1.5 LoRA Style Adapter"
            fn_low = p.name.lower()

            if "lucasarts" in fn_low:
                name = "🌟 LucasArts 1993 Adventure (Sam & Max / DOTT)"
                trigger = "lucasarts_retro_style, pixel art"
                desc = "1993 SCUMM adventure aesthetic, skewed angles, colorful noir"
            elif "pixelart" in fn_low or "pixel" in fn_low:
                name = "👾 PixelArt Redmond 16-Bit Dithering"
                trigger = "Pixel Art, PixArFK"
                desc = "Authentic Amiga / SNES 16-bit pixel art dithering and game palette"
            elif "ghibli" in fn_low:
                name = "🍃 Studio Ghibli Anime Adventure"
                trigger = "Studio Ghibli, StdGBRedmAF"
                desc = "Lush painted anime landscapes, fluffy clouds, and warm Miyazaki colors"
            elif "cutecartoon" in fn_low or "cartoon" in fn_low:
                name = "📺 90s Cute Cartoon Adventure"
                trigger = "Cartoon, CuteCartoonAF"
                desc = "Saturday morning retro cartoon outlines and expressive color palettes"
            elif "clayanimation" in fn_low or "clay" in fn_low:
                name = "🗿 Clay Animation (The Neverhood)"
                trigger = "Clay Animation, Clay"
                desc = "Plasticine clay textures, stop-motion lighting, and handcrafted clay figures"
            elif "storybook" in fn_low:
                name = "📖 StoryBook Hand-Drawn Adventure"
                trigger = "StoryBook, KidsRedmAF"
                desc = "Hand-illustrated fantasy storybook art with storybook warmth"
            elif "retrocgi" in fn_low:
                name = "🕹️ Retro 90s 3D CGI (Myst / Donkey Kong)"
                trigger = "retrocgi style"
                desc = "Early 90s pre-rendered SGI workstation 3D graphics and nostalgic textures"
            elif "sticker" in fn_low:
                name = "🏷️ Game Item & Sticker Icons"
                trigger = "Stickers, Sticker"
                desc = "Crisp item pickups, sticker sprites, and game inventory icons"

            loras.append({
                "id": p.stem,
                "filename": p.name,
                "display_name": name,
                "description": desc,
                "size_mb": sz_mb,
                "trigger_hint": trigger,
                "path": str(p),
                "is_protected": p.name in ["lucasarts_retro_style.safetensors"]
            })

    base_models = []
    if sd15_dir.exists():
        for p in sorted(sd15_dir.glob("*.gguf")):
            sz_mb = round(p.stat().st_size / (1024 * 1024), 1)
            name = p.name
            speed = "Fast (~21s)"
            desc = "Stable Diffusion 1.5 Base GGUF Checkpoint"
            if "q4_0" in p.name.lower():
                name = f"⚡ SD 1.5 Q4_0 Ultra-Fast ({p.name})"
                speed = "Ultra-Fast (~13s)"
                desc = "4-bit quantized base model. Generates in ~13 seconds on Jetson CUDA0!"
            elif "q8_0" in p.name.lower():
                name = f"🚀 SD 1.5 Q8_0 High-Fidelity ({p.name})"
                speed = "Fast (~21s)"
                desc = "8-bit quantized base model. Maximum image fidelity and full LoRA dynamic range."

            base_models.append({
                "id": p.name,
                "filename": p.name,
                "engine": "sd15",
                "display_name": name,
                "description": desc,
                "size_mb": sz_mb,
                "speed_estimate": speed,
                "lora_compatible": True,
                "is_protected": p.name in ["sd-v1-5-pruned-emaonly-Q8_0.gguf"]
            })

    if iris_dir.exists():
        for p in sorted(iris_dir.glob("*Iris-3B*.gguf")):
            sz_mb = round(p.stat().st_size / (1024 * 1024), 1)
            base_models.append({
                "id": p.name,
                "filename": p.name,
                "engine": "iris",
                "display_name": f"🌸 Sakura-Iris-3B DiT ({p.name})",
                "description": "3.1 Billion parameter Diffusion Transformer for high-detail anime illustrations.",
                "size_mb": sz_mb,
                "speed_estimate": "Moderate (~6m)",
                "lora_compatible": False,
                "is_protected": True
            })

    disk = shutil.disk_usage("/")
    free_gb = round(disk.free / (1024 ** 3), 1)
    total_gb = round(disk.total / (1024 ** 3), 1)

    return {
        "status": "ok",
        "free_disk_gb": free_gb,
        "total_disk_gb": total_gb,
        "base_models": base_models,
        "loras": loras
    }


@app.get("/api/models/search-hf")
def api_search_hf_models(q: str = "", limit: int = 15, api_key: str = Depends(verify_api_key)):
    """Live search Hugging Face Hub for SD 1.5 LoRAs and GGUF models."""
    import urllib.request
    import urllib.parse
    import json

    q = (q or "").strip()
    if not q:
        q = "pixel art lora"

    url = f"https://huggingface.co/api/models?search={urllib.parse.quote(q)}&expand[]=siblings&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "AdventureForge/1.0"})

    results = []
    try:
        with urllib.request.urlopen(req, timeout=7) as resp:
            data = json.loads(resp.read().decode())
            for item in data:
                repo_id = item.get("id", "")
                if not repo_id or item.get("private", False):
                    continue
                siblings = item.get("siblings", [])

                safe_files = [s["rfilename"] for s in siblings if s.get("rfilename", "").endswith(".safetensors")]
                gguf_files = [s["rfilename"] for s in siblings if s.get("rfilename", "").endswith(".gguf")]

                if not safe_files and not gguf_files:
                    continue

                mtype = "base_model" if gguf_files else "lora"
                files = gguf_files if gguf_files else safe_files

                results.append({
                    "repo_id": repo_id,
                    "type": mtype,
                    "downloads": item.get("downloads", 0),
                    "likes": item.get("likes", 0),
                    "tags": [t for t in item.get("tags", []) if t in ["lora", "sd-1.5", "gguf", "pixel-art"] or "adapter" in t][:5],
                    "files": files[:8]
                })
        return {"status": "ok", "query": q, "results": results}
    except Exception as e:
        return {"status": "error", "message": str(e), "results": []}


@app.delete("/api/models/delete")
def api_delete_model(filename: str, type: str = "lora", api_key: str = Depends(verify_api_key)):
    """Delete a downloaded model file to free up disk space."""
    from pathlib import Path
    clean_fn = Path(filename).name
    if type == "base_model":
        target = Path("/home/x/jetson-containers/data/models/sd15") / clean_fn
    else:
        target = Path("/home/x/jetson-containers/data/models/loras") / clean_fn

    if not target.exists():
        raise HTTPException(404, f"Model file not found: {clean_fn}")

    if clean_fn in ["lucasarts_retro_style.safetensors", "sd-v1-5-pruned-emaonly-Q8_0.gguf"]:
        raise HTTPException(400, "Cannot delete protected core project model.")

    try:
        target.unlink()
        return {"status": "ok", "message": f"Successfully deleted {clean_fn}"}
    except Exception as e:
        raise HTTPException(500, f"Error deleting file: {e}")


@app.post("/api/models/download")
def api_download_model(payload: dict[str, Any], api_key: str = Depends(verify_api_key)):
    """Download a LoRA (.safetensors) or Base Model (.gguf) from Hugging Face or direct URL."""
    import shutil
    import urllib.request
    from pathlib import Path
    from huggingface_hub import hf_hub_download

    target_type = str(payload.get("type", "lora")).lower()  # lora or base_model
    repo_id = (payload.get("repo_id") or "").strip()
    filename = (payload.get("filename") or "").strip()
    url = (payload.get("url") or "").strip()

    if target_type == "base_model":
        dest_dir = Path("/home/x/jetson-containers/data/models/sd15")
    else:
        dest_dir = Path("/home/x/jetson-containers/data/models/loras")
    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        if url and not repo_id:
            # Direct URL download
            clean_name = filename or url.split("?")[0].split("/")[-1]
            if not clean_name.endswith((".safetensors", ".gguf", ".bin")):
                clean_name += ".safetensors" if target_type == "lora" else ".gguf"
            target_path = dest_dir / clean_name
            urllib.request.urlretrieve(url, str(target_path))
            return {
                "status": "ok",
                "message": f"Successfully downloaded {clean_name}!",
                "filename": clean_name,
                "size_mb": round(target_path.stat().st_size / (1024 * 1024), 1)
            }
        elif repo_id and filename:
            # HuggingFace Hub download
            downloaded = hf_hub_download(repo_id=repo_id, filename=filename)
            target_path = dest_dir / Path(filename).name
            shutil.copy2(downloaded, target_path)
            return {
                "status": "ok",
                "message": f"Successfully downloaded {target_path.name} from Hugging Face ({repo_id})!",
                "filename": target_path.name,
                "size_mb": round(target_path.stat().st_size / (1024 * 1024), 1)
            }
        else:
            raise HTTPException(400, "Must provide either (repo_id + filename) or direct url.")
    except Exception as e:
        raise HTTPException(500, f"Download failed: {e}")


@app.post("/api/assets/pixelize")
def api_pixelize_asset(payload: dict[str, Any], api_key: str = Depends(verify_api_key)):
    from tools.assets import pixelize_asset
    asset_url = (payload.get("asset_url") or "").strip()
    if not asset_url:
        raise HTTPException(400, "Asset URL required")
    res = pixelize_asset(
        asset_url=asset_url,
        pixel_size=int(payload.get("pixel_size", 32)),
        num_colors=int(payload.get("num_colors", 16)),
        auto_remove_bg=bool(payload.get("auto_remove_bg", False))
    )
    if "error" in res:
        raise HTTPException(400, res["error"])
    return res


@app.post("/api/media/download-url")
def api_download_url(payload: dict[str, Any], api_key: str = Depends(verify_api_key)):
    from tools.media import download_asset_from_url
    url = (payload.get("url") or "").strip()
    if not url:
        raise HTTPException(400, "URL cannot be empty")
    return download_asset_from_url(
        url=url,
        category=payload.get("category", "items"),
        filename=payload.get("filename", ""),
        auto_remove_bg=bool(payload.get("auto_remove_bg", False))
    )


@app.post("/api/vlm/generate-place-items")
def api_vlm_generate_place_items(payload: dict[str, Any], api_key: str = Depends(verify_api_key)):
    from tools.vlm import vlm_generate_and_place_items
    room_id = (payload.get("room_id") or "").strip()
    if not room_id:
        raise HTTPException(400, "room_id is required")
    res = vlm_generate_and_place_items(
        room_id=room_id,
        count=int(payload.get("count", 3)),
        generate_sprites=bool(payload.get("generate_sprites", True)),
        hint=str(payload.get("hint", ""))
    )
    if "error" in res:
        raise HTTPException(400, res["error"])
    return res


@app.post("/api/vlm/auto-detect-props")
def api_vlm_auto_detect_props(payload: dict[str, Any], api_key: str = Depends(verify_api_key)):
    from tools.vlm import vlm_auto_detect_and_place_props
    room_id = (payload.get("room_id") or "").strip()
    if not room_id:
        raise HTTPException(400, "room_id is required")
    res = vlm_auto_detect_and_place_props(
        room_id=room_id,
        count=int(payload.get("count", 3)),
        hint=str(payload.get("hint", ""))
    )
    if "error" in res:
        raise HTTPException(400, res["error"])
    return res


@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestration."""
    return {
        "status": "healthy",
        "service": "adventure-forge",
        "version": "1.0.0"
    }


app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    config.ensure_dirs()
    warnings = config.validate()
    for w in warnings:
        print(f"WARNING: {w}")
    uvicorn.run(app, host=config.HOST, port=config.PORT)

"""
AdventureForge — Media Generation, Search & Sound Effects MCP Tools (.env Powered)
"""
import io
import json
import os
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image
from google import genai

from config import config
from ._core import (
    _load_proj,
    _save_proj,
    _get_api_keys,
    LOCAL_SD15_GGUF,
    LOCAL_REDMOND_LORA,
    LOCAL_LUCASARTS_LORA,
    LOCAL_IRIS_GGUF,
    LOCAL_IRIS_TE,
)
from .assets import remove_asset_background, pixelize_asset


def list_available_media_apis() -> dict[str, Any]:
    """Check configuration and availability of media generation and search API keys in .env (Freesound, SerpAPI Google Images, Gemini, Sprite Fusion MCP, Hugging Face, Local Jetson Iris 3B Diffusion)."""
    keys = _get_api_keys()
    iris_path = config.get_iris_model_path()
    return {
        "freesound_audio": bool(keys.get("freesound")),
        "serp_google_images": bool(keys.get("serp")),
        "gemini_image_gen": bool(keys.get("gemini")),
        "spritefusion_mcp": bool(keys.get("spritefusion")),
        "huggingface": bool(keys.get("hf")),
        "nvidia": bool(keys.get("nvidia")),
        "prime": bool(keys.get("prime")),
        "jetson_local_iris_diffusion": iris_path.exists(),
        "jetson_local_model_path": str(iris_path) if iris_path.exists() else "",
        "jetson_text_encoder_path": str(config.get_iris_te_path()) if config.get_iris_te_path().exists() else "",
        "jetson_cuda_accelerated": True,
    }


def search_and_download_sound_effects(
    query: str,
    category: str = "sounds",
    filename: str = "",
    min_duration: float = 0.2,
    max_duration: float = 20.0,
    link_to_room_id: str = "",
    link_to_puzzle_id: str = ""
) -> dict[str, Any]:
    """Search Freesound.org using FREESOUND_API_KEY from .env, download high-quality sound effect or music preview directly into /assets/sounds or /assets/music, and optionally link to a room or puzzle."""
    keys = _get_api_keys()
    fs_key = keys.get("freesound")
    if not fs_key:
        return {"error": "FREESOUND_API_KEY not found in .env"}
    if not query.strip():
        return {"error": "Search query cannot be empty"}

    cat_name = "music" if category.lower() in ("music", "bgm", "ambient") else "sounds"
    cat_dir = config.ASSETS_DIR / cat_name
    cat_dir.mkdir(parents=True, exist_ok=True)

    params = urllib.parse.urlencode({
        "query": query.strip(),
        "token": fs_key,
        "fields": "id,name,duration,previews,tags",
        "filter": f"duration:[{max(0.1, float(min_duration))} TO {min(180.0, float(max_duration))}]",
        "page_size": 10
    })
    url = f"https://freesound.org/apiv2/search/text/?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "AdventureForge/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        return {"error": f"Freesound API request failed: {e}"}

    results = data.get("results") or []
    if not results:
        return {"error": f"No sound effects found for query: '{query}'"}

    cand = next((r for r in results if r.get("previews", {}).get("preview-hq-mp3")), results[0])
    preview_url = cand.get("previews", {}).get("preview-hq-mp3") or cand.get("previews", {}).get("preview-lq-mp3")
    if not preview_url:
        return {"error": "Sound result has no downloadable audio preview"}

    if not filename:
        clean_name = re.sub(r"[^\w\-_\.]", "_", cand.get("name", "sound")).lower()
        if not clean_name.endswith((".mp3", ".wav", ".ogg")):
            clean_name += ".mp3"
        filename = f"{clean_name}"
    else:
        if not filename.endswith((".mp3", ".wav", ".ogg")):
            filename += ".mp3"
        filename = re.sub(r"[^\w\-_\.]", "_", filename).lower()

    dest_path = cat_dir / filename
    dl_req = urllib.request.Request(preview_url, headers={"User-Agent": "AdventureForge/1.0"})
    try:
        with urllib.request.urlopen(dl_req, timeout=15) as dl_resp, open(dest_path, "wb") as f:
            f.write(dl_resp.read())
    except Exception as e:
        return {"error": f"Failed to download audio preview: {e}"}

    rel_url = f"/assets/{cat_name}/{filename}"

    proj = _load_proj()
    linked = []
    if link_to_room_id:
        room = next((r for r in proj.get("rooms", []) if r.get("id") == link_to_room_id), None)
        if room:
            room["music"] = rel_url
            linked.append(f"Room '{room.get('name', link_to_room_id)}' (music/ambient)")

    if link_to_puzzle_id:
        puz = next((p for p in proj.get("puzzles", []) if p.get("id") == link_to_puzzle_id), None)
        if puz:
            puz["sound_effect"] = rel_url
            linked.append(f"Puzzle '{puz.get('name', link_to_puzzle_id)}' (solve sound)")

    if linked:
        _save_proj(proj)

    return {
        "status": "ok",
        "sound_name": cand.get("name"),
        "duration": cand.get("duration"),
        "freesound_id": cand.get("id"),
        "file_url": rel_url,
        "file_path": str(dest_path),
        "size_bytes": dest_path.stat().st_size,
        "linked_to": linked
    }


def search_and_download_images(
    query: str,
    category: str = "items",
    filename: str = "",
    transparent_only: bool = False,
    auto_remove_bg: bool = True,
    link_to_room_id: str = "",
    link_to_item_id: str = "",
    link_to_hotspot_id: str = ""
) -> dict[str, Any]:
    """Search Google Images using SERP_API_KEY from .env, download high-res images directly into /assets/items, /assets/backgrounds, or /assets/sprites, optionally remove background to make it transparent, and link to room, item, or prop."""
    keys = _get_api_keys()
    serp_key = keys.get("serp")
    if not serp_key:
        return {"error": "SERP_API_KEY not found in .env"}
    if not query.strip():
        return {"error": "Search query cannot be empty"}

    valid_cats = {"items", "backgrounds", "sprites"}
    target_cat = category if category in valid_cats else "items"
    cat_dir = config.ASSETS_DIR / target_cat
    cat_dir.mkdir(parents=True, exist_ok=True)

    search_q = query.strip()
    if transparent_only and "transparent" not in search_q.lower():
        search_q += " transparent png"
    if target_cat == "items" and "pixel art" not in search_q.lower() and "icon" not in search_q.lower():
        search_q += " pixel art icon"
    elif target_cat == "backgrounds" and "background" not in search_q.lower() and "room" not in search_q.lower():
        search_q += " adventure game background"

    params = urllib.parse.urlencode({
        "engine": "google_images",
        "q": search_q,
        "api_key": serp_key,
        "num": 10
    })
    url = f"https://serpapi.com/search.json?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        return {"error": f"SerpApi search failed: {e}"}

    imgs = data.get("images_results") or []
    if not imgs:
        return {"error": f"No Google Images results for query: '{query}'"}

    if not filename:
        clean_name = re.sub(r"[^\w\-_\.]", "_", query.strip().split()[0]).lower()
        filename = f"{clean_name}_{int(time.time()) % 10000}.png"
    else:
        if not filename.endswith((".png", ".jpg", ".jpeg", ".webp")):
            filename += ".png"
        filename = re.sub(r"[^\w\-_\.]", "_", filename).lower()

    dest_path = cat_dir / filename

    downloaded = False
    chosen_meta = {}
    for im in imgs[:6]:
        cand_url = im.get("original") or im.get("thumbnail")
        if not cand_url:
            continue
        try:
            ireq = urllib.request.Request(cand_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            with urllib.request.urlopen(ireq, timeout=8) as iresp:
                raw_bytes = iresp.read()
                pil_img = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
                pil_img.save(dest_path, format="PNG")
                downloaded = True
                chosen_meta = im
                break
        except Exception:
            continue

    if not downloaded:
        thumb_url = imgs[0].get("thumbnail")
        if thumb_url:
            try:
                ireq = urllib.request.Request(thumb_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(ireq, timeout=8) as iresp:
                    pil_img = Image.open(io.BytesIO(iresp.read())).convert("RGBA")
                    pil_img.save(dest_path, format="PNG")
                    downloaded = True
                    chosen_meta = imgs[0]
            except Exception as e:
                return {"error": f"Failed downloading image candidates: {e}"}

    if not downloaded:
        return {"error": "Failed to download image from search results"}

    rel_url = f"/assets/{target_cat}/{filename}"

    bg_removed = False
    if auto_remove_bg and target_cat in ("items", "sprites"):
        try:
            res_bg = remove_asset_background(rel_url, mode="corners", tolerance=35, trim=True)
            bg_removed = "error" not in res_bg
        except Exception:
            pass

    proj = _load_proj()
    linked = []
    if link_to_room_id:
        room = next((r for r in proj.get("rooms", []) if r.get("id") == link_to_room_id), None)
        if room:
            room["background"] = rel_url
            linked.append(f"Room '{room.get('name', link_to_room_id)}' (background)")

    if link_to_item_id:
        item = next((i for i in proj.get("items", []) if i.get("id") == link_to_item_id), None)
        if item:
            item["icon"] = rel_url
            linked.append(f"Item '{item.get('name', link_to_item_id)}' (icon)")

    if link_to_hotspot_id:
        for r in proj.get("rooms", []):
            hs = next((h for h in r.get("hotspots", []) if h.get("id") == link_to_hotspot_id), None)
            if hs:
                hs["icon"] = rel_url
                linked.append(f"Hotspot '{hs.get('name', link_to_hotspot_id)}' (icon)")
                break

    if linked:
        _save_proj(proj)

    return {
        "status": "ok",
        "file_url": rel_url,
        "title": chosen_meta.get("title", filename),
        "source": chosen_meta.get("link", ""),
        "background_removed": bg_removed,
        "linked_to": linked
    }


def _call_spritefusion_mcp(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Helper to communicate with Sprite Fusion MCP endpoint (https://www.spritefusion.com/mcp) over SSE stream."""
    keys = _get_api_keys()
    sf_key = keys.get("spritefusion")
    if not sf_key:
        return {"error": "SPRITE_FUSION_API_KEY not found in .env."}

    req_data = json.dumps({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        },
        "id": int(time.time() * 1000)
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://www.spritefusion.com/mcp",
        data=req_data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {sf_key}",
            "User-Agent": "AdventureForge/1.0"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=55) as resp:
            resp_text = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return {"error": f"Failed connecting to Sprite Fusion MCP: {e}"}

    parsed = None
    for line in resp_text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload_str = line[len("data:"):].strip()
            try:
                msg = json.loads(payload_str)
                if "result" in msg or "error" in msg:
                    parsed = msg
                    break
            except Exception:
                pass
    if not parsed:
        try:
            parsed = json.loads(resp_text)
        except Exception:
            return {"error": f"Invalid response from Sprite Fusion: {resp_text[:300]}"}

    if "error" in parsed:
        err = parsed["error"]
        msg = err.get("message") if isinstance(err, dict) else str(err)
        return {"error": f"Sprite Fusion MCP Error: {msg}"}

    return parsed.get("result", {})


def spritefusion_get_credits() -> dict[str, Any]:
    """Get the current Sprite Fusion account credit balance via MCP server."""
    res = _call_spritefusion_mcp("get_credits", {})
    if "error" in res:
        return res
    if "structuredContent" in res and "credits" in res["structuredContent"]:
        return {"credits": res["structuredContent"]["credits"]}
    for c in res.get("content", []):
        try:
            val = json.loads(c.get("text", "{}"))
            if "credits" in val:
                return {"credits": val["credits"]}
        except Exception:
            pass
    return {"credits": 0, "raw": res}


def spritefusion_list_saved_assets() -> dict[str, Any]:
    """List all previously generated pixel art assets saved in the user's Sprite Fusion cloud library."""
    res = _call_spritefusion_mcp("list_assets", {})
    if "error" in res:
        return res
    for c in res.get("content", []):
        try:
            val = json.loads(c.get("text", "{}"))
            if "assets" in val:
                return {"count": len(val["assets"]), "assets": val["assets"]}
        except Exception:
            pass
    return {"count": 0, "assets": []}


def spritefusion_generate_pixel_art(
    prompt: str,
    size: int = 32,
    category: str = "items",
    filename: str = "",
    auto_remove_bg: bool = False,
    link_to_room_id: str = "",
    link_to_item_id: str = "",
    link_to_hotspot_id: str = ""
) -> dict[str, Any]:
    """Generate authentic pixel art using Sprite Fusion MCP Server (https://www.spritefusion.com/mcp) via SPRITE_FUSION_API_KEY from .env, saving sprites directly into /assets/*. If credits are depleted, automatically searches and reuses matching assets from the user's Sprite Fusion cloud library."""
    keys = _get_api_keys()
    sf_key = keys.get("spritefusion")
    if not sf_key:
        return {
            "error": "SPRITE_FUSION_API_KEY not found in .env.",
            "mcp_server_url": "https://www.spritefusion.com/mcp",
            "setup_guide": "Sign up at https://www.spritefusion.com/account/api-keys to get your API key, then add SPRITE_FUSION_API_KEY=sf_live_... to your .env file."
        }
    if not prompt.strip():
        return {"error": "Prompt cannot be empty"}

    try:
        size = int(size)
    except (ValueError, TypeError):
        size = 32
    if size not in (16, 32, 64):
        size = 32

    valid_cats = {"items", "backgrounds", "sprites"}
    target_cat = category if category in valid_cats else "items"
    cat_dir = config.ASSETS_DIR / target_cat
    cat_dir.mkdir(parents=True, exist_ok=True)

    if not filename:
        clean_name = re.sub(r"[^\w\-_\.]", "_", prompt.strip().split()[0]).lower()
        filename = f"{clean_name}_{int(time.time()) % 10000}.png"
    else:
        if not filename.endswith((".png", ".jpg", ".jpeg", ".webp")):
            filename += ".png"
        filename = re.sub(r"[^\w\-_\.]", "_", filename).lower()

    dest_path = cat_dir / filename
    rel_url = f"/assets/{target_cat}/{filename}"

    download_url = ""
    reused_from_library = False

    # Attempt generation via Sprite Fusion MCP
    res = _call_spritefusion_mcp("generate_sprites", {"prompt": prompt, "size": size})

    if "error" in res or res.get("isError"):
        err_msg = ""
        if "error" in res:
            err_msg = str(res["error"])
        elif res.get("isError"):
            for c in res.get("content", []):
                if c.get("text"):
                    err_msg = c["text"]
                    break
        # If out of credits or generation failed, check if we can reuse a matching saved asset from library
        saved_assets_res = spritefusion_list_saved_assets()
        saved_list = saved_assets_res.get("assets", [])
        prompt_words = [w.lower() for w in re.findall(r"\w+", prompt) if len(w) > 2]

        best_match = None
        best_score = 0
        for item in saved_list:
            item_prompt = item.get("prompt", "").lower()
            score = sum(1 for w in prompt_words if w in item_prompt)
            if score > best_score:
                best_score = score
                best_match = item

        if best_match and best_match.get("assetUrl"):
            download_url = best_match["assetUrl"]
            reused_from_library = True
        else:
            return {
                "error": f"Sprite Fusion generation unavailable: {err_msg}",
                "suggestion": "Sprite Fusion credits are depleted (15 credits needed per generation). You can top up at https://www.spritefusion.com/pricing, or use generate_image_ai / search_and_download_images for instant graphic generation."
            }
    else:
        # Extract download URL from successful generation result
        for c in res.get("content", []):
            text_val = c.get("text", "")
            try:
                json_match = re.search(r'(\{.*"outputs"\s*:\s*\[.*\}\])', text_val, re.DOTALL)
                if json_match:
                    embedded = json.loads(json_match.group(1))
                    outputs = embedded.get("outputs", [])
                    if outputs and outputs[0].get("assetUrl"):
                        download_url = outputs[0]["assetUrl"]
                        break
            except Exception:
                pass
            if not download_url:
                urls = re.findall(r'https?://[^\s"\'<>)]+\.png(?:\?[^\s"\'<>)]*)?', text_val)
                if urls:
                    download_url = urls[0]
                    break

    if not download_url:
        return {"error": f"No download URL returned from Sprite Fusion: {res}"}

    try:
        dl_req = urllib.request.Request(download_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(dl_req, timeout=25) as dl_resp, open(dest_path, "wb") as f:
            f.write(dl_resp.read())
    except Exception as dl_err:
        return {"error": f"Failed downloading Sprite Fusion asset from {download_url}: {dl_err}"}

    bg_removed = False
    if auto_remove_bg:
        try:
            res_bg = remove_asset_background(rel_url, mode="corners", tolerance=35, trim=True)
            bg_removed = "error" not in res_bg
        except Exception:
            pass

    proj = _load_proj()
    linked = []
    if link_to_room_id:
        room = next((r for r in proj.get("rooms", []) if r.get("id") == link_to_room_id), None)
        if room:
            room["background"] = rel_url
            linked.append(f"Room '{room.get('name', link_to_room_id)}' (background)")

    if link_to_item_id:
        item = next((i for i in proj.get("items", []) if i.get("id") == link_to_item_id), None)
        if item:
            item["icon"] = rel_url
            linked.append(f"Item '{item.get('name', link_to_item_id)}' (icon)")

    if link_to_hotspot_id:
        for r in proj.get("rooms", []):
            hs = next((h for h in r.get("hotspots", []) if h.get("id") == link_to_hotspot_id), None)
            if hs:
                hs["icon"] = rel_url
                linked.append(f"Hotspot '{hs.get('name', link_to_hotspot_id)}' (icon)")
                break

    if linked:
        _save_proj(proj)

    return {
        "status": "ok",
        "file_url": rel_url,
        "filename": filename,
        "prompt": prompt,
        "size": size,
        "generator_method": "Sprite Fusion Cloud Library (reused asset)" if reused_from_library else "Sprite Fusion Pixel Art MCP",
        "background_removed": bg_removed,
        "linked_to": linked
    }


def jetson_generate_image(
    prompt: str,
    category: str = "items",
    filename: str = "",
    width: int = 512,
    height: int = 512,
    steps: int = 20,
    cfg_scale: float = 7.0,
    sampling_method: str = "euler_a",
    model_engine: str = "sd15",
    base_model_file: str = "",
    active_loras: dict[str, float] | None = None,
    negative_prompt: str = "",
    seed: int = -1,
    lucasarts_weight: float = 0.0,
    redmond_weight: float = 0.0,
    pixel_art: bool = False,
    pixel_size: int = 32,
    num_colors: int = 16,
    auto_remove_bg: bool = False,
    link_to_room_id: str = "",
    link_to_item_id: str = "",
    link_to_hotspot_id: str = ""
) -> dict[str, Any]:
    """Generate image locally and offline on the NVIDIA Jetson GPU.
    Supports raw SD 1.5, Sakura-Iris-3B, or user-selected LoRAs with explicit weights."""
    if not LOCAL_SD15_GGUF.exists() and not LOCAL_IRIS_GGUF.exists():
        return {"error": f"No local diffusion models found in {config.JETSON_MODELS_DIR}."}
    if not prompt.strip():
        return {"error": "Prompt cannot be empty"}

    try:
        width = int(width)
        height = int(height)
        steps = int(steps)
        cfg_scale = float(cfg_scale)
        pixel_size = int(pixel_size)
        num_colors = int(num_colors)
        seed = int(seed)
    except (ValueError, TypeError):
        width, height, steps, cfg_scale, pixel_size, num_colors, seed = 512, 512, 20, 7.0, 32, 16, -1

    width = max(256, min(1024, (width // 64) * 64))
    height = max(256, min(1024, (height // 64) * 64))
    steps = max(10, min(50, steps))
    cfg_scale = max(1.0, min(15.0, cfg_scale))

    valid_cats = {"items", "backgrounds", "sprites"}
    target_cat = category if category in valid_cats else "items"
    cat_dir = config.ASSETS_DIR / target_cat
    cat_dir.mkdir(parents=True, exist_ok=True)

    if not filename:
        clean_name = re.sub(r"[^\w\-_\.]", "_", prompt.strip().split()[0]).lower()
        filename = f"{clean_name}_{int(time.time()) % 10000}.png"
    else:
        if not filename.endswith((".png", ".jpg", ".jpeg", ".webp")):
            filename += ".png"
        filename = re.sub(r"[^\w\-_\.]", "_", filename).lower()

    dest_path = cat_dir / filename
    rel_url = f"/assets/{target_cat}/{filename}"
    out_rel = f"out_{int(time.time() * 1000)}.png"

    sd_bin = config.get_sd_cli_binary()
    if not sd_bin.exists():
        return {"error": f"stable-diffusion.cpp binary not found at {sd_bin}. Please verify build."}

    bin_path = f"/data/stable-diffusion.cpp/build/bin/{sd_bin.name}"

    # Only apply LoRAs if explicitly requested by user (weight > 0.0)
    lora_tags = []
    if active_loras and isinstance(active_loras, dict):
        for lname, lweight in active_loras.items():
            try:
                w = float(lweight)
                if w > 0.01:
                    cname = Path(lname).stem
                    lora_tags.append(f"<lora:{cname}:{w:.2f}>")
            except (ValueError, TypeError):
                pass
    else:
        try:
            lw = float(lucasarts_weight or 0.0)
            if lw > 0.01 and LOCAL_LUCASARTS_LORA.exists():
                lora_tags.append(f"<lora:lucasarts_retro_style:{lw:.2f}>")
        except (ValueError, TypeError):
            pass

        try:
            rw = float(redmond_weight or 0.0)
            if rw > 0.01 and LOCAL_REDMOND_LORA.exists():
                lora_tags.append(f"<lora:PixelArtRedmond:{rw:.2f}>")
        except (ValueError, TypeError):
            pass

    model_prompt = prompt.strip()
    if lora_tags:
        model_prompt += ", " + ", ".join(lora_tags)

    neg = (negative_prompt or "").strip() or "blurry, photograph, 3d render, realistic, smooth gradient, vector"

    target_base_name = LOCAL_SD15_GGUF.name
    if base_model_file:
        cand = config.JETSON_SD15_DIR / Path(base_model_file).name
        if cand.exists():
            target_base_name = cand.name

    data_volume = f"{config.JETSON_MODELS_DIR.parent}:/data"

    if model_engine == "iris" and LOCAL_IRIS_GGUF.exists():
        # Sakura-Iris-3B DiT + Qwen3-VL
        if not sampling_method or sampling_method == "euler_a":
            sampling_method = "dpm++2m"
        if cfg_scale > 4.5:
            cfg_scale = 3.0

        cmd = [
            "docker", "run", "--runtime", "nvidia", "--rm",
            "-u", f"{os.getuid()}:{os.getgid()}",
            "-v", data_volume,
            "-w", "/data",
            config.JETSON_DOCKER_IMAGE,
            bin_path,
            "--diffusion-model", f"/data/models/iris-3b/{LOCAL_IRIS_GGUF.name}",
            "--llm", f"/data/models/iris-3b/{LOCAL_IRIS_TE.name}",
            "--backend", "te=cpu,diffusion=CUDA0",
            "--params-backend", "diffusion=disk,te=disk",
            "--max-vram", "2.0",
            "--sampling-method", sampling_method,
            "--cfg-scale", str(cfg_scale),
            "-p", model_prompt,
            "-n", neg,
            "-W", str(width),
            "-H", str(height),
            "--steps", str(steps),
            "-o", f"/data/{out_rel}"
        ]
        if seed >= 0:
            cmd.extend(["-s", str(seed)])
        method_label = "Jetson GPU (Sakura-Iris-3B DiT)"
    else:
        # Standard SD 1.5 GGUF on CUDA0
        if not sampling_method:
            sampling_method = "euler_a"

        cmd = [
            "docker", "run", "--runtime", "nvidia", "--rm",
            "-u", f"{os.getuid()}:{os.getgid()}",
            "-v", data_volume,
            "-w", "/data",
            config.JETSON_DOCKER_IMAGE,
            bin_path,
            "-m", f"/data/models/sd15/{target_base_name}",
            "--lora-model-dir", "/data/models/loras",
            "--backend", "cuda0",
            "--sampling-method", sampling_method,
            "--cfg-scale", str(cfg_scale),
            "-p", model_prompt,
            "-n", neg,
            "-W", str(width),
            "-H", str(height),
            "--steps", str(steps),
            "-o", f"/data/{out_rel}"
        ]
        if seed >= 0:
            cmd.extend(["-s", str(seed)])

        applied_desc = []
        if lora_tags:
            applied_desc.append(" + ".join(lora_tags))
        method_label = f"Jetson GPU ({target_base_name}{' + ' + ', '.join(applied_desc) if applied_desc else ' Raw Base'})"

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        out_file = Path(f"{config.JETSON_MODELS_DIR.parent}/{out_rel}")
        if not out_file.exists():
            return {
                "error": f"Generation failed: {proc.stderr or proc.stdout[:300]}",
                "returncode": proc.returncode
            }
        shutil.move(str(out_file), str(dest_path))
    except Exception as e:
        return {"error": f"Failed running local diffusion model: {e}"}

    bg_removed = False
    # Automatically pixelize to crisp retro game standard
    if pixel_art:
        try:
            res_pix = pixelize_asset(rel_url, pixel_size=pixel_size, num_colors=num_colors, auto_remove_bg=auto_remove_bg)
            bg_removed = auto_remove_bg and ("error" not in res_pix)
        except Exception:
            pass
    elif auto_remove_bg and target_cat in ("items", "sprites"):
        try:
            res_bg = remove_asset_background(rel_url, mode="corners", tolerance=35, trim=True)
            bg_removed = "error" not in res_bg
        except Exception:
            pass

    proj = _load_proj()
    linked = []
    if link_to_room_id:
        room = next((r for r in proj.get("rooms", []) if r.get("id") == link_to_room_id), None)
        if room:
            room["background"] = rel_url
            linked.append(f"Room '{room.get('name', link_to_room_id)}' (background)")

    if link_to_item_id:
        item = next((i for i in proj.get("items", []) if i.get("id") == link_to_item_id), None)
        if item:
            item["icon"] = rel_url
            linked.append(f"Item '{item.get('name', link_to_item_id)}' (icon)")

    if link_to_hotspot_id:
        for r in proj.get("rooms", []):
            hs = next((h for h in r.get("hotspots", []) if h.get("id") == link_to_hotspot_id), None)
            if hs:
                hs["icon"] = rel_url
                linked.append(f"Hotspot '{hs.get('name', link_to_hotspot_id)}' (icon)")
                break

    if linked:
        _save_proj(proj)

    return {
        "status": "ok",
        "file_url": rel_url,
        "filename": filename,
        "prompt": prompt,
        "generator_method": method_label,
        "background_removed": bg_removed,
        "linked_to": linked
    }


def generate_image_ai(
    prompt: str,
    category: str = "items",
    filename: str = "",
    aspect_ratio: str = "1:1",
    auto_remove_bg: bool = True,
    link_to_room_id: str = "",
    link_to_item_id: str = "",
    link_to_hotspot_id: str = ""
) -> dict[str, Any]:
    """Generate image using Gemini/HF API key from .env (with intelligent SerpApi & procedural fallback), saves to /assets/*, optionally strips background, and wires directly into game entities."""
    keys = _get_api_keys()
    valid_cats = {"items", "backgrounds", "sprites"}
    target_cat = category if category in valid_cats else "items"
    cat_dir = config.ASSETS_DIR / target_cat
    cat_dir.mkdir(parents=True, exist_ok=True)

    if not filename:
        clean_name = re.sub(r"[^\w\-_\.]", "_", prompt.strip().split()[0]).lower()
        filename = f"{clean_name}_{int(time.time()) % 10000}.png"
    else:
        if not filename.endswith((".png", ".jpg", ".jpeg", ".webp")):
            filename += ".png"
        filename = re.sub(r"[^\w\-_\.]", "_", filename).lower()

    dest_path = cat_dir / filename
    rel_url = f"/assets/{target_cat}/{filename}"
    method_used = ""

    # Strategy 0: Sprite Fusion Pixel Art MCP if configured in .env
    if keys.get("spritefusion"):
        res_sf = spritefusion_generate_pixel_art(
            prompt=prompt,
            category=target_cat,
            filename=filename,
            auto_remove_bg=auto_remove_bg,
            link_to_room_id=link_to_room_id,
            link_to_item_id=link_to_item_id,
            link_to_hotspot_id=link_to_hotspot_id
        )
        if "error" not in res_sf:
            return res_sf

    # Strategy 1: Try Gemini API if available
    if keys.get("gemini"):
        try:
            client = genai.Client()
            resp = client.models.generate_content(
                model="gemini-2.5-flash-image",
                contents=f"Generate visual asset for adventure game: {prompt}. High quality graphic, solid plain background.",
            )
            cand = resp.candidates[0] if resp.candidates else None
            if cand and cand.content:
                for part in cand.content.parts or []:
                    if getattr(part, "inline_data", None) and part.inline_data.data:
                        pil_img = Image.open(io.BytesIO(part.inline_data.data)).convert("RGBA")
                        pil_img.save(dest_path, format="PNG")
                        method_used = "Gemini Native Image Model"
                        break
        except Exception:
            pass

    # Strategy 2: If image generation model quota reached, use SerpApi image search engine
    if not method_used and keys.get("serp"):
        res_serp = search_and_download_images(
            query=f"pixel art {prompt} transparent",
            category=target_cat,
            filename=filename,
            auto_remove_bg=auto_remove_bg,
            link_to_room_id=link_to_room_id,
            link_to_item_id=link_to_item_id,
            link_to_hotspot_id=link_to_hotspot_id
        )
        if "error" not in res_serp:
            res_serp["generator_method"] = "SerpApi Google High-Res Asset Search"
            return res_serp

    # Strategy 3: Local offline Jetson CUDA Iris model fallback if available
    if not dest_path.exists() and LOCAL_IRIS_GGUF.exists():
        res_local = jetson_generate_image(
            prompt=prompt,
            category=target_cat,
            filename=filename,
            auto_remove_bg=auto_remove_bg,
            link_to_room_id=link_to_room_id,
            link_to_item_id=link_to_item_id,
            link_to_hotspot_id=link_to_hotspot_id
        )
        if "error" not in res_local:
            return res_local

    if not dest_path.exists():
        return {"error": "Image generation and search providers both unavailable. Please verify API keys in .env or wait for local model compilation."}

    bg_removed = False
    if auto_remove_bg and target_cat in ("items", "sprites"):
        try:
            res_bg = remove_asset_background(rel_url, mode="corners", tolerance=35, trim=True)
            bg_removed = "error" not in res_bg
        except Exception:
            pass

    proj = _load_proj()
    linked = []
    if link_to_room_id:
        room = next((r for r in proj.get("rooms", []) if r.get("id") == link_to_room_id), None)
        if room:
            room["background"] = rel_url
            linked.append(f"Room '{room.get('name', link_to_room_id)}' (background)")

    if link_to_item_id:
        item = next((i for i in proj.get("items", []) if i.get("id") == link_to_item_id), None)
        if item:
            item["icon"] = rel_url
            linked.append(f"Item '{item.get('name', link_to_item_id)}' (icon)")

    if link_to_hotspot_id:
        for r in proj.get("rooms", []):
            hs = next((h for h in r.get("hotspots", []) if h.get("id") == link_to_hotspot_id), None)
            if hs:
                hs["icon"] = rel_url
                linked.append(f"Hotspot '{hs.get('name', link_to_hotspot_id)}' (icon)")
                break

    if linked:
        _save_proj(proj)

    return {
        "status": "ok",
        "file_url": rel_url,
        "method": method_used,
        "background_removed": bg_removed,
        "linked_to": linked
    }


def download_asset_from_url(
    url: str,
    category: str = "items",
    filename: str = "",
    auto_remove_bg: bool = False
) -> dict[str, Any]:
    """Directly download any image or sound asset from a URL into the game project and register it in the asset library."""
    if not url.strip():
        return {"error": "URL cannot be empty"}
    target_cat = category if category in ("items", "backgrounds", "sprites", "sounds", "music") else "items"
    cat_dir = config.ASSETS_DIR / target_cat
    cat_dir.mkdir(parents=True, exist_ok=True)

    if not filename:
        parsed_name = Path(urllib.parse.urlparse(url).path).name
        filename = parsed_name or f"download_{int(time.time())}"
        if "." not in filename:
            filename += ".mp3" if target_cat in ("sounds", "music") else ".png"

    dest_path = cat_dir / filename
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp, open(dest_path, "wb") as f:
            f.write(resp.read())
    except Exception as e:
        return {"error": f"Download failed: {e}"}

    rel_url = f"/assets/{target_cat}/{filename}"
    if auto_remove_bg and target_cat in ("items", "sprites"):
        try:
            remove_asset_background(rel_url, mode="corners", tolerance=35, trim=True)
        except Exception:
            pass

    return {
        "status": "ok",
        "file_url": rel_url,
        "file_path": str(dest_path),
        "size_bytes": dest_path.stat().st_size
    }
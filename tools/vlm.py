"""
AdventureForge — Gemini VLM Vision Intelligence MCP Tools
"""
import json
import re
import shutil
from pathlib import Path
from typing import Any
from config import config
from ._core import (
    _load_proj,
    _save_proj,
    _resolve_asset,
    load_env,
)
from PIL import Image, ImageDraw
from google import genai
from google.genai import types


def _unique_id(base: str, taken: set[str]) -> str:
    """Return `base` if free, otherwise `base_2`, `base_3`, ..."""
    if base not in taken:
        return base
    suffix = 2
    while f"{base}_{suffix}" in taken:
        suffix += 1
    return f"{base}_{suffix}"


def _fallback_badge_icon(name: str, dest: Path) -> None:
    """Draw a simple letter badge so every item has a usable inventory sprite."""
    ph = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    d = ImageDraw.Draw(ph)
    d.rounded_rectangle([4, 4, 44, 44], radius=8, fill=(180, 120, 40, 230), outline=(255, 230, 80, 255), width=2)
    d.text((12, 16), name[:3].upper(), fill=(255, 255, 255))
    ph.save(dest)


def _generate_item_icon(item_id: str, name: str, sprite_prompt: str) -> tuple[str, str]:
    """Generate a pixel-art icon for an item.

    Tries the local Jetson diffusion model first (offline, matches the house
    style), then falls back to the cloud generators (Sprite Fusion / Gemini /
    Serp). The result is pixelised to 32x32 / 16 colours so it matches the
    rest of the sprite work, and a letter badge is drawn if nothing works.

    Returns (icon_url, method).
    """
    from .media import generate_image_ai, jetson_generate_image
    from .assets import pixelize_asset

    items_dir = config.ASSETS_DIR / "items"
    items_dir.mkdir(parents=True, exist_ok=True)
    icon_rel_path = f"/assets/items/{item_id}.png"
    icon_file_path = items_dir / f"{item_id}.png"
    method = "none"

    prompt = sprite_prompt or f"16-bit pixel art {name}, isolated on white background"

    # 1) Local Jetson diffusion model (offline, preferred when available)
    if config.get_sd15_model_path("q8").exists() or config.get_iris_model_path().exists():
        try:
            gen_res = jetson_generate_image(
                prompt=f"{prompt}, pixel art, 16-bit",
                category="items",
                filename=f"{item_id}.png",
                negative_prompt="blurry, photorealistic, 3d, smooth",
                steps=15,
                width=256,
                height=256,
                auto_remove_bg=True,
                pixel_art=True,
                pixel_size=32,
                num_colors=16,
            )
            if "error" not in gen_res and gen_res.get("asset_url"):
                src = _resolve_asset(gen_res["asset_url"])
                if src.exists() and src != icon_file_path:
                    shutil.copy2(src, icon_file_path)
                method = "jetson_local"
        except Exception:
            pass

    # 2) Cloud generators (Sprite Fusion / Gemini / Serp fallback chain)
    if method == "none":
        try:
            res = generate_image_ai(
                prompt=prompt,
                category="items",
                filename=f"{item_id}.png",
                auto_remove_bg=True,
            )
            if "error" not in res and res.get("file_url"):
                src = _resolve_asset(res["file_url"])
                if src.exists() and src != icon_file_path:
                    shutil.copy2(src, icon_file_path)
                method = res.get("method", "cloud")
        except Exception:
            pass

    # 3) Pixelise for a consistent retro look
    if icon_file_path.exists():
        try:
            pixelize_asset(icon_rel_path, pixel_size=32, num_colors=16)
        except Exception:
            pass
    else:
        # 4) Last resort: letter badge so the item is never iconless
        try:
            _fallback_badge_icon(name, icon_file_path)
            method = "fallback_badge"
        except Exception:
            return "", method

    return icon_rel_path, method


def create_coordinate_grid_overlay(image: Image.Image, step_x: int = 64, step_y: int = 48) -> Image.Image:
    """Stamp a crisp coordinate grid overlay on an image so a VLM can accurately read pixel coordinates."""
    overlay = image.copy().convert("RGB")
    draw = ImageDraw.Draw(overlay, "RGBA")
    w, h = overlay.size

    for col, x in enumerate(range(0, w, step_x)):
        draw.line([(x, 0), (x, h)], fill=(255, 255, 255, 45), width=1)
        col_label = chr(65 + col) if col < 26 else f"A{col-26}"
        draw.text((x + 4, 4), f"{col_label}({x})", fill=(255, 230, 80, 230))

    for row, y in enumerate(range(0, h, step_y)):
        draw.line([(0, y), (w, y)], fill=(255, 255, 255, 45), width=1)
        draw.text((4, y + 4), f"R{row+1}({y})", fill=(255, 230, 80, 230))

    for x in range(step_x * 2, w, step_x * 2):
        for y in range(step_y * 2, h, step_y * 2):
            draw.text((x + 2, y + 2), f"{x},{y}", fill=(100, 240, 255, 140))

    return overlay


def vlm_auto_detect_and_place_props(room_id: str, count: int = 3, hint: str = "") -> dict[str, Any]:
    """Use Gemini VLM with a coordinate grid overlay to visually inspect a room's background image, detect background objects/props with pixel coordinates, write witty Look At & Use lines, and add them to the room."""
    proj = _load_proj()
    room = next((r for r in proj["rooms"] if r["id"] == room_id), None)
    if not room:
        return {"error": f"Room '{room_id}' not found."}
    bg_url = room.get("background", "")
    if not bg_url:
        return {"error": f"Room '{room_id}' has no background image."}

    bg_path = _resolve_asset(bg_url)
    if not bg_path.exists():
        return {"error": f"Background file not found: {bg_url}"}

    load_env()
    client = genai.Client()
    bg_img = Image.open(bg_path).convert("RGB").resize((1280, 720))
    gridded_img = create_coordinate_grid_overlay(bg_img, step_x=64, step_y=48)

    existing_names = [h.get("name", "") for h in room.get("hotspots", [])]
    prompt = f"""You are a LucasArts adventure game designer and vision model inspecting the 1280x720 background image for room "{room.get('name', room_id)}".
An explicit coordinate grid is stamped across the image with pixel X and Y coordinates. Use these grid lines and coordinate numbers to locate props with high pixel precision.
Existing hotspots already in the room: {", ".join(existing_names) or "none"}.
{f"Designer hint: {hint}" if hint else ""}

Visually identify {max(1, min(6, int(count)))} distinct, interesting props/objects visible in the room background image.
For each object, return its pixel bounding box in 1280x720 coordinates (x, y, w, h) and witty Sam & Max style "look_text" and "use_text".

Return ONLY valid JSON matching:
{{
  "props": [
    {{
      "id": "snake_case_id",
      "name": "Short Display Name",
      "x": 200,
      "y": 300,
      "w": 110,
      "h": 120,
      "look_text": "Witty 1-2 sentence LucasArts observation.",
      "use_text": "Witty 1 sentence response when used."
    }}
  ]
}}"""

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=[gridded_img, prompt],
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    res_data = json.loads(response.text)
    props_list = res_data.get("props", []) if isinstance(res_data, dict) else []

    added = []
    for p in props_list:
        hid = "".join(c for c in p.get("id", "prop") if c.isalnum() or c == "_").lower() or "prop_vlm"
        if any(h.get("id") == hid for h in room.get("hotspots", [])):
            hid = f"{hid}_{len(room.get('hotspots', [])) + 1}"
        x = max(0, min(1200, int(p.get("x", 300))))
        y = max(0, min(650, int(p.get("y", 300))))
        w = max(32, min(400, int(p.get("w", 90))))
        h = max(32, min(400, int(p.get("h", 90))))
        new_hs = {
            "id": hid,
            "name": p.get("name", hid),
            "type": "prop",
            "rect": {"x": x, "y": y, "w": w, "h": h},
            "walk_to": {"x": int(x + w // 2), "y": min(685, int(y + h + 25))},
            "look_text": p.get("look_text", "It looks interesting."),
            "use_text": p.get("use_text", ""),
            "talk_text": ""
        }
        room.setdefault("hotspots", []).append(new_hs)
        added.append(new_hs)

    _save_proj(proj)
    return {"status": "ok", "added_count": len(added), "props": added}


def vlm_generate_and_place_items(
    room_id: str,
    count: int = 3,
    generate_sprites: bool = True,
    hint: str = ""
) -> dict[str, Any]:
    """Use Gemini VLM with a coordinate grid overlay to inspect a room's physical surfaces (desks, shelves, floors), propose context-appropriate adventure game items with pixel-accurate positions, generate their pixel art sprites, and register them as inventory items and room pickup hotspots."""
    proj = _load_proj()
    room = next((r for r in proj["rooms"] if r["id"] == room_id), None)
    if not room:
        return {"error": f"Room '{room_id}' not found."}
    bg_url = room.get("background", "")
    if not bg_url:
        return {"error": f"Room '{room_id}' has no background image."}

    bg_path = _resolve_asset(bg_url)
    if not bg_path.exists():
        return {"error": f"Background file not found: {bg_url}"}

    load_env()
    client = genai.Client()
    bg_img = Image.open(bg_path).convert("RGB").resize((1280, 720))
    gridded_img = create_coordinate_grid_overlay(bg_img, step_x=64, step_y=48)

    existing_names = [h.get("name", "") for h in room.get("hotspots", [])]
    existing_items = [it.get("name", "") for it in proj.get("items", [])]

    prompt = f"""You are a master LucasArts point-and-click adventure game designer (Sam & Max / Day of the Tentacle style).
Inspect this 1280x720 background image with an explicit coordinate grid overlay for room "{room.get('name', room_id)}".

Notice the coordinate numbers stamped across the grid:
- Horizontal columns with pixel X values (e.g. 64, 128, 192, 256, 320, 384, ...)
- Vertical rows with pixel Y values (e.g. 48, 96, 144, 192, 240, 288, ...)

Existing hotspots already in the room: {", ".join(existing_names) or "none"}.
Existing inventory items in game: {", ".join(existing_items) or "none"}.
{f"Designer hint: {hint}" if hint else ""}

Identify {max(1, min(6, int(count)))} distinct, physical surfaces (such as a desk, a table, a shelf, the floor, the mantelpiece, or a counter) where interactive pickup items should be placed.
For each item:
1. 'name': Concise display name (e.g. 'Stale Donut', 'Rusty Skeleton Key', 'Magnifying Glass')
2. 'surface_description': What real surface in the image you are placing it on
3. 'rect': Exact pixel bounding box {{x, y, w, h}} where the item should sit based on the grid labels
4. 'walk_to': Natural pixel coordinates {{x, y}} for the character to walk up and interact with it
5. 'look_text': Witty 1-2 sentence LucasArts observation
6. 'pickup_text': Witty reaction when picked up
7. 'sprite_prompt': Visual description to generate a 16-bit pixel art sprite for this item

Return ONLY valid JSON matching:
{{
  "items": [
    {{
      "name": "Short Name",
      "surface_description": "On the wooden desk next to the lamp",
      "rect": {{"x": 200, "y": 300, "w": 48, "h": 48}},
      "walk_to": {{"x": 240, "y": 420}},
      "look_text": "Witty observation.",
      "pickup_text": "Picked up!",
      "sprite_prompt": "16-bit pixel art brass skeleton key, isolated on white background, retro adventure game sprite"
    }}
  ]
}}"""

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=[gridded_img, prompt],
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    res_data = json.loads(response.text)
    items_list = res_data.get("items", []) if isinstance(res_data, dict) else []

    taken_ids = {it.get("id", "") for it in proj.get("items", [])}
    taken_hs_ids = {h.get("id", "") for h in room.get("hotspots", [])}

    created = []
    for raw in items_list:
        name = raw.get("name", "Mystery Item")
        base_id = re.sub(r"[^a-zA-Z0-9_]", "", str(name).lower().replace(" ", "_")) or "item_vlm"
        item_id = _unique_id(base_id, taken_ids)
        taken_ids.add(item_id)

        # Accept both payload shapes: legacy {"rect": {...}} and flat x/y/w/h.
        r = raw.get("rect") or {}
        x = max(0, min(1200, int(r.get("x", raw.get("x", 300)))))
        y = max(0, min(650, int(r.get("y", raw.get("y", 300)))))
        w = max(24, min(256, int(r.get("w", raw.get("w", 48)))))
        h = max(24, min(256, int(r.get("h", raw.get("h", 48)))))

        wto = raw.get("walk_to") or {}
        walk_x = max(0, min(1279, int(wto.get("x", x + w // 2))))
        walk_y = max(0, min(719, int(wto.get("y", min(685, y + h + 25)))))

        icon_url = ""
        icon_method = "none"
        if generate_sprites:
            icon_url, icon_method = _generate_item_icon(item_id, name, raw.get("sprite_prompt", ""))

        item_entry = {
            "id": item_id,
            "name": name,
            "description": raw.get("look_text", "An intriguing object."),
            "icon": icon_url,
        }
        proj.setdefault("items", []).append(item_entry)

        hs_id = _unique_id(f"pickup_{item_id}", taken_hs_ids)
        taken_hs_ids.add(hs_id)
        hs_entry = {
            "id": hs_id,
            "name": name,
            "type": "pickup",
            "item_id": item_id,
            "rect": {"x": x, "y": y, "w": w, "h": h},
            "walk_to": {"x": walk_x, "y": walk_y},
            "look_text": raw.get("look_text", f"It's {name}."),
            "use_text": raw.get("use_text", ""),
            "pickup_text": raw.get("pickup_text", f"Picked up {name}!"),
            "talk_text": "",
            "icon": icon_url,
        }
        room.setdefault("hotspots", []).append(hs_entry)

        created.append({
            "item": item_entry,
            "hotspot": hs_entry,
            "surface": raw.get("surface_description", ""),
            "icon_method": icon_method,
        })

    _save_proj(proj)
    return {
        "status": "ok",
        "room_id": room_id,
        "created_count": len(created),
        "items": created,
    }


def vlm_describe_hotspot(room_id: str, hotspot_id: str, style: str = "") -> dict[str, Any]:
    """Use Gemini VLM to visually inspect a specific hotspot's bounding box on the room background (and/or its icon) and auto-fill its name, look_text, and use_text."""
    proj = _load_proj()
    room = next((r for r in proj["rooms"] if r["id"] == room_id), None)
    if not room:
        return {"error": f"Room '{room_id}' not found."}
    hs = next((h for h in room.get("hotspots", []) if h.get("id") == hotspot_id), None)
    if not hs:
        return {"error": f"Hotspot '{hotspot_id}' not found in room '{room_id}'."}

    load_env()
    client = genai.Client()
    contents: list[Any] = []

    if hs.get("icon"):
        try:
            p = _resolve_asset(hs["icon"])
            if p.exists():
                contents.append(Image.open(p).convert("RGB"))
        except Exception:
            pass

    if room.get("background"):
        try:
            bg_path = _resolve_asset(room["background"])
            if bg_path.exists():
                bg_img = Image.open(bg_path).convert("RGB").resize((1280, 720))
                r = hs.get("rect") or {"x": 100, "y": 100, "w": 100, "h": 100}
                rx, ry, rw, rh = int(r["x"]), int(r["y"]), int(r["w"]), int(r["h"])
                crop = bg_img.crop((max(0, rx - 15), max(0, ry - 15), min(1280, rx + rw + 15), min(720, ry + rh + 15)))
                contents.append(crop)
                ov = bg_img.copy()
                ImageDraw.Draw(ov).rectangle([rx, ry, rx + rw, ry + rh], outline=(255, 40, 40), width=4)
                contents.append(ov)
        except Exception:
            pass

    style_hint = f" Match this writing style: {style}." if style else ""
    prompt = f"""You are a classic LucasArts adventure writer. Inspect the highlighted object "{hs.get('name', hotspot_id)}" in room "{room.get('name', room_id)}".{style_hint}
Return JSON with:
{{
  "suggested_name": "2-4 word object name",
  "look_text": "Witty 1-2 sentence Look At line",
  "use_text": "Short 1 sentence Use line"
}}"""
    contents.append(prompt)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    data = json.loads(response.text)
    if isinstance(data, list) and data:
        data = data[0]
    if data.get("suggested_name"):
        hs["name"] = data["suggested_name"]
    if data.get("look_text"):
        hs["look_text"] = data["look_text"]
    if data.get("use_text"):
        hs["use_text"] = data["use_text"]
    _save_proj(proj)
    return {"status": "ok", "hotspot": hs}


def vlm_inspect_room_scene(room_id: str, query_question: str) -> dict[str, Any]:
    """Ask Gemini VLM any question about a room's background image (e.g. 'What clues or exits would fit here?', 'Describe the aesthetic and tone')."""
    proj = _load_proj()
    room = next((r for r in proj["rooms"] if r["id"] == room_id), None)
    if not room:
        return {"error": f"Room '{room_id}' not found."}
    bg_url = room.get("background", "")
    if not bg_url:
        return {"error": f"Room '{room_id}' has no background image."}
    bg_path = _resolve_asset(bg_url)
    if not bg_path.exists():
        return {"error": f"Background file not found: {bg_url}"}

    load_env()
    client = genai.Client()
    bg_img = Image.open(bg_path).convert("RGB").resize((1280, 720))

    prompt = f"""You are a veteran adventure game vision architect analyzing the background scene of room "{room.get('name', room_id)}".
User question: {query_question}
Provide a detailed, highly observant game-design assessment."""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[bg_img, prompt]
    )
    return {"room_id": room_id, "analysis": response.text}

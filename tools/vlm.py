"""
AdventureForge — Gemini VLM Vision Intelligence MCP Tools
"""
import json
import re
from typing import Any
from config import config
from agent_tools import (
    _load_proj,
    _save_proj,
    _resolve_asset,
    load_env,
    ASSETS_DIR,
    DATA_DIR,
    BASE_DIR,
)
from PIL import Image, ImageDraw
from google import genai
from google.genai import types


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

Identify {max(1, min(5, int(count)))} physical surfaces or logical locations where an adventure game item would naturally sit (desk, shelf, floor, cabinet, barrel, windowsill, etc.).
For each, propose a thematically appropriate item with:
1. Pixel-accurate position on that surface (x, y, w, h in 1280x720 coords)
2. Item name, description, and witty "look_text" / "pickup_text"
3. Whether it should be a pickup (inventory item) or prop (scenery)

Return ONLY valid JSON matching:
{{
  "items": [
    {{
      "id": "snake_case_id",
      "name": "Item Display Name",
      "description": "Inventory description / Look At text",
      "x": 450,
      "y": 520,
      "w": 48,
      "h": 48,
      "surface": "desk",
      "is_pickup": true,
      "pickup_text": "Picked up the whatever!",
      "look_text": "It's a whatever. Looks useful.",
      "sprite_prompt": "pixel art whatever, 32x32, transparent background"
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

    added_items = []
    added_hotspots = []

    for item_data in items_list:
        item_id = "".join(c for c in item_data.get("id", "item") if c.isalnum() or c == "_").lower() or "item_vlm"
        if any(it.get("id") == item_id for it in proj.get("items", [])):
            item_id = f"{item_id}_{len(proj.get('items', [])) + 1}"

        # Create inventory item
        new_item = {
            "id": item_id,
            "name": item_data.get("name", item_id),
            "description": item_data.get("description", "A curious object."),
            "icon": ""  # Will be filled if sprite generated
        }
        proj.setdefault("items", []).append(new_item)
        added_items.append(new_item)

        # Create pickup hotspot
        x = max(0, min(1200, int(item_data.get("x", 300))))
        y = max(0, min(650, int(item_data.get("y", 300))))
        w = max(16, min(120, int(item_data.get("w", 48))))
        h = max(16, min(120, int(item_data.get("h", 48))))
        hs_id = f"pickup_{item_id}"
        if any(h.get("id") == hs_id for h in room.get("hotspots", [])):
            hs_id = f"{hs_id}_{len(room.get('hotspots', [])) + 1}"

        new_hs = {
            "id": hs_id,
            "name": item_data.get("name", item_id),
            "type": "pickup" if item_data.get("is_pickup", True) else "prop",
            "item_id": item_id if item_data.get("is_pickup", True) else "",
            "rect": {"x": x, "y": y, "w": w, "h": h},
            "walk_to": {"x": int(x + w // 2), "y": min(685, int(y + h + 25))},
            "look_text": item_data.get("look_text", "It looks interesting."),
            "pickup_text": item_data.get("pickup_text", f"Picked up {item_data.get('name', item_id)}!"),
            "talk_text": ""
        }
        room.setdefault("hotspots", []).append(new_hs)
        added_hotspots.append(new_hs)

        # Generate sprite if requested
        if generate_sprites and item_data.get("sprite_prompt"):
            try:
                from tools.media import generate_image_ai
                sprite_result = generate_image_ai(
                    prompt=item_data["sprite_prompt"],
                    category="items",
                    filename=f"{item_id}.png",
                    auto_remove_bg=True,
                    link_to_item_id=item_id
                )
                if "error" not in sprite_result:
                    new_item["icon"] = sprite_result["file_url"]
                    new_hs["icon"] = sprite_result["file_url"]
            except Exception:
                pass

    _save_proj(proj)
    return {"status": "ok", "added_items": added_items, "added_hotspots": added_hotspots}
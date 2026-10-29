#!/usr/bin/env python3
"""
AdventureForge — Sprite sheet segmentation + Gemini VLM animation mapping.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import find_objects, label


def _load_env() -> None:
    """Load .env credentials (AdventureForge's config when available)."""
    try:
        from config import config
        config.load_env()
        return
    except Exception:
        pass
    # Standalone fallback: read a .env next to this file or in the cwd.
    for candidate in (Path(__file__).resolve().parent.parent / ".env", Path.cwd() / ".env"):
        if not candidate.exists():
            continue
        try:
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if key and key not in os.environ:
                    os.environ[key] = value.strip().strip('"').strip("'")
        except OSError:
            continue


# ============================================================================
# Segmentation
# ============================================================================

def detect_background_color(arr: "np.ndarray") -> "np.ndarray":
    """Sample the image border and return the most common border colour.

    Returned as an int ndarray so callers can use it directly in numpy
    arithmetic (`bg_color.astype(int)`).
    """
    borders = np.concatenate([
        arr[0, :, :3],
        arr[-1, :, :3],
        arr[:, 0, :3],
        arr[:, -1, :3]
    ], axis=0)
    colors, counts = np.unique(borders, axis=0, return_counts=True)
    return colors[np.argmax(counts)].astype(int)


def segment_sprites(img_path, min_w: int = 8, min_h: int = 12, pad: int = 2):
    """Split a sprite sheet into individual frames.

    Returns (image, boxes, background_color) where `boxes` is a list of
    {"x", "y", "w", "h"} dicts ordered top-to-bottom, left-to-right.
    `background_color` is None when the sheet already carries an alpha mask.
    """
    orig_img = Image.open(img_path)
    has_alpha = orig_img.mode == "RGBA"
    arr = np.array(orig_img)

    if has_alpha:
        alpha = arr[:, :, 3]
        if np.any(alpha < 250):
            fg = alpha > 15
            bg_color = None
        else:
            bg_color = detect_background_color(arr)
            fg = np.sum(np.abs(arr[:, :, :3].astype(int) - bg_color.astype(int)), axis=2) > 20
    else:
        bg_color = detect_background_color(arr)
        fg = np.sum(np.abs(arr[:, :, :3].astype(int) - bg_color.astype(int)), axis=2) > 20

    labels, _num_features = label(fg)
    slices = find_objects(labels)

    raw_boxes = []
    img_w, img_h = orig_img.size
    for sl in slices:
        if sl is None:
            continue
        y_sl, x_sl = sl
        w = x_sl.stop - x_sl.start
        h = y_sl.stop - y_sl.start
        if w >= min_w and h >= min_h:
            x1 = max(0, x_sl.start - pad)
            y1 = max(0, y_sl.start - pad)
            x2 = min(img_w, x_sl.stop + pad)
            y2 = min(img_h, y_sl.stop + pad)
            raw_boxes.append({
                "x": int(x1),
                "y": int(y1),
                "w": int(x2 - x1),
                "h": int(y2 - y1)
            })

    # Sort top-to-bottom, left-to-right so frame indices read naturally.
    sorted_boxes = sorted(raw_boxes, key=lambda b: (b["y"] // 40, b["x"]))
    return orig_img, sorted_boxes, bg_color


# ============================================================================
# Frame export
# ============================================================================

def export_frames(
    orig_img: Image.Image,
    boxes: list[dict[str, int]],
    bg_color: "tuple[int, int, int] | None",
    out_dir,
    prefix: str = "frame",
) -> list[str]:
    """Write every detected frame to `out_dir` as a transparent PNG.

    Returns the list of file names written.
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    frame_files = []
    for idx, b in enumerate(boxes):
        crop = orig_img.crop((b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"])).convert("RGBA")
        if bg_color is not None:
            arr = np.array(crop)
            diff = np.sum(np.abs(arr[:, :, :3].astype(int) - bg_color.astype(int)), axis=2)
            arr[diff < 20, 3] = 0
            crop = Image.fromarray(arr, "RGBA")
        fname = f"{prefix}_{idx:03d}.png"
        crop.save(out_path / fname)
        frame_files.append(fname)
    return frame_files


# ============================================================================
# VLM analysis
# ============================================================================

def create_annotated_image(orig_img: Image.Image, boxes: list[dict[str, int]]) -> Image.Image:
    """Draw numbered red badges over each detected frame for VLM grounding."""
    annotated = orig_img.convert("RGB").copy()
    draw = ImageDraw.Draw(annotated)

    for idx, b in enumerate(boxes):
        x, y, w, h = b["x"], b["y"], b["w"], b["h"]
        draw.rectangle([x, y, x + w, y + h], outline=(255, 30, 30), width=2)
        badge_w, badge_h = 18, 13
        draw.rectangle([x, y, x + badge_w, y + badge_h], fill=(255, 30, 30))
        draw.text((x + 2, y + 1), str(idx), fill=(255, 255, 255))

    return annotated


def call_vlm_analyzer(
    annotated_img: Image.Image,
    boxes: list[dict[str, int]],
    prompt_hint: str | None = None,
) -> dict[str, Any]:
    """Ask Gemini to group frame indices into named animation sequences."""
    _load_env()
    from google import genai
    from google.genai import types

    client = genai.Client()

    prompt = f"""You are an expert game animator assistant.
Analyze this character sprite sheet with {len(boxes)} segmented frames, labeled with red index badges (0 to {len(boxes)-1}).
List of boxes:
{json.dumps(boxes, indent=1)}

{f"Additional user guidance: {prompt_hint}" if prompt_hint else ""}

Identify:
1. Character or object name.
2. Group the numbered frame indices into smooth animation sequences:
   - Identify directions: down, up, left, right, upright, downleft, etc.
   - Identify actions: walk, idle, run, talk, attack, jump, etc.
   - For point-and-click / adventure games, look especially for:
     "walk_down", "walk_up", "walk_right", "walk_left", "idle_down", "talk_down", etc.
   - Specify appropriate fps (default 8 or 10) and whether it should loop.
   - Order the indices in proper chronological playback order.

Return ONLY a valid JSON object with schema:
{{
  "character_name": "string",
  "animations": [
    {{
      "name": "string",
      "fps": 8.0,
      "loop": true,
      "indices": [0, 1, 2]
    }}
  ]
}}
"""
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[annotated_img, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )
    return json.loads(response.text)


# ============================================================================
# One-shot helper
# ============================================================================

def slice_spritesheet(
    sheet_path,
    out_dir,
    use_vlm: bool = True,
    prompt_hint: str | None = None,
    prefix: str = "frame",
) -> dict[str, Any]:
    """Segment a sheet, export frames and (optionally) map animations.

    Returns a dict with the detected boxes, exported frame file names and the
    VLM animation metadata.
    """
    orig_img, boxes, bg_color = segment_sprites(sheet_path)
    frame_files = export_frames(orig_img, boxes, bg_color, out_dir, prefix=prefix)

    vlm_meta: dict[str, Any] = {}
    if use_vlm and boxes:
        annotated = create_annotated_image(orig_img, boxes)
        vlm_meta = call_vlm_analyzer(annotated, boxes, prompt_hint=prompt_hint)

    return {
        "boxes": boxes,
        "frame_files": frame_files,
        "background_color": bg_color,
        "vlm": vlm_meta,
    }

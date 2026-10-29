"""
AdventureForge — Asset Library & Background Remover MCP Tools
"""
import shutil
import numpy as np
from typing import Any
from config import config
from ._core import (
    _resolve_asset,
)
from PIL import Image


def list_assets(category: str = "all") -> dict[str, Any]:
    """List uploaded image assets on disk. category can be 'all', 'items', 'backgrounds', 'sprites', or 'frames'."""
    assets = []
    if config.ASSETS_DIR.exists():
        for path in sorted(config.ASSETS_DIR.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp") or ".orig." in path.name:
                continue
            rel = "/" + str(path.relative_to(config.DATA_DIR)).replace("\\", "/")
            parts = path.relative_to(config.ASSETS_DIR).parts
            top_cat = parts[0] if parts else "other"
            cat = "frames" if (top_cat == "sprites" and len(parts) > 1 and parts[1].endswith("_frames")) else top_cat
            if category != "all" and cat != category:
                continue
            assets.append({"url": rel, "name": path.name, "category": cat})
    return {"count": len(assets), "assets": assets}


def remove_asset_background(
    asset_url: str,
    mode: str = "corners",
    tolerance: int = 30,
    trim: bool = False
) -> dict[str, Any]:
    """Remove the background from an uploaded image asset (e.g. '/assets/items/pizzaslice.png'), saving a .orig backup and updating it retroactively everywhere."""
    target = _resolve_asset(asset_url)
    if not target.exists():
        return {"error": f"Asset not found: {asset_url}"}

    orig_backup = target.with_name(f"{target.stem}.orig{target.suffix}")
    if not orig_backup.exists():
        shutil.copy2(target, orig_backup)

    img = Image.open(target).convert("RGBA")
    arr = np.array(img)
    h, w, _ = arr.shape
    tol = max(1, int(tolerance)) * 3

    corners = [arr[0, 0, :3], arr[0, w - 1, :3], arr[h - 1, 0, :3], arr[h - 1, w - 1, :3]]

    if mode == "global":
        bg_rgb = corners[0].astype(int)
        diff = np.sum(np.abs(arr[:, :, :3].astype(int) - bg_rgb), axis=2)
        arr[diff <= tol, 3] = 0
    else:
        visited = np.zeros((h, w), dtype=bool)
        stack = [(0, 0, corners[0].astype(int)), (w - 1, 0, corners[1].astype(int)), (0, h - 1, corners[2].astype(int)), (w - 1, h - 1, corners[3].astype(int))]
        for sx, sy, c_rgb in stack:
            q = [(sx, sy)]
            while q:
                cx, cy = q.pop()
                if cx < 0 or cx >= w or cy < 0 or cy >= h or visited[cy, cx]:
                    continue
                visited[cy, cx] = True
                px_rgb = arr[cy, cx, :3].astype(int)
                if int(np.sum(np.abs(px_rgb - c_rgb))) <= tol:
                    arr[cy, cx, 3] = 0
                    q.extend([(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)])

    out_img = Image.fromarray(arr, "RGBA")
    if trim:
        bbox = out_img.getbbox()
        if bbox:
            out_img = out_img.crop(bbox)
    out_img.save(target, format="PNG")

    return {
        "status": "ok",
        "asset_url": asset_url,
        "width": out_img.width,
        "height": out_img.height,
        "backup_created": True
    }


def restore_asset_original(asset_url: str) -> dict[str, Any]:
    """Revert an edited asset image back to its original pre-modified disk backup."""
    target = _resolve_asset(asset_url)
    orig_candidates = [
        target.with_name(f"{target.stem}.orig{target.suffix}"),
        target.with_name(f"{target.stem}.orig.png"),
        target.with_name(f"{target.stem}.orig.jpg"),
        target.with_name(f"{target.stem}.orig.jpeg"),
    ]
    orig_file = next((f for f in orig_candidates if f.exists()), None)
    if not orig_file:
        return {"error": f"No original backup found for {asset_url}"}
    shutil.copy2(orig_file, target)
    return {"status": "ok", "restored": asset_url, "source_backup": orig_file.name}


def delete_asset_file(asset_url: str) -> dict[str, Any]:
    """Delete an image asset and its backup from the project's data/assets directory."""
    target = _resolve_asset(asset_url)
    if not target.exists():
        return {"error": f"Asset file not found: {asset_url}"}
    target.unlink()
    for orig in target.parent.glob(f"{target.stem}.orig.*"):
        try:
            orig.unlink()
        except Exception:
            pass
    return {"status": "ok", "deleted": asset_url}


def pixelize_asset(
    asset_url: str,
    pixel_size: int = 32,
    num_colors: int = 16,
    auto_remove_bg: bool = False
) -> dict[str, Any]:
    """Convert any image asset into authentic 16-bit/32-bit pixel art by downsampling, palette-quantizing, and upscaling with nearest-neighbor interpolation."""
    target = _resolve_asset(asset_url)
    if not target.exists():
        return {"error": f"Asset not found: {asset_url}"}

    orig_backup = target.with_name(f"{target.stem}.orig{target.suffix}")
    if not orig_backup.exists():
        shutil.copy2(target, orig_backup)

    try:
        pixel_size = int(pixel_size)
    except (ValueError, TypeError):
        pixel_size = 32

    try:
        img = Image.open(target).convert("RGBA")
        w, h = img.size
        aspect = w / h

        # If it's a full background or high-res scene (w >= 384) and pixel_size wasn't explicitly set large,
        # use authentic SCUMM VGA resolution (320px wide) rather than 32px item thumbnail resolution!
        is_background = ("background" in asset_url.lower()) or (w >= 384 and pixel_size <= 64)
        if is_background:
            target_res = 320
            dw = target_res
            dh = max(160, int(target_res / aspect))
            colors = max(32, min(256, int(num_colors) if num_colors > 16 else 128))
        else:
            dw = max(16, min(128, pixel_size))
            dh = max(8, int(dw / aspect)) if aspect >= 1.0 else max(8, int(dw * aspect))
            colors = max(4, min(64, int(num_colors)))

        # Use NEAREST resampling to preserve razor-sharp pixel edges (no bilinear blur!)
        small = img.resize((dw, dh), Image.Resampling.NEAREST)
        r, g, b, a = small.split()
        rgb = Image.merge("RGB", (r, g, b))
        quantized = rgb.quantize(colors=colors, dither=Image.Dither.FLOYDSTEINBERG).convert("RGB")
        qr, qg, qb = quantized.split()
        a_crisp = a.point(lambda p: 255 if p > 64 else 0)
        pixel_art = Image.merge("RGBA", (qr, qg, qb, a_crisp))

        # Scale back up to original display size with NEAREST for chunky pixels
        final_img = pixel_art.resize((w, h), Image.Resampling.NEAREST)
        final_img.save(target, format="PNG")

        if auto_remove_bg:
            try:
                remove_asset_background(asset_url, mode="corners", tolerance=35, trim=True)
            except Exception:
                pass

        return {
            "status": "ok",
            "asset_url": asset_url,
            "pixel_size": pixel_size,
            "num_colors": num_colors,
            "display_size": [w, h],
            "backed_up_to": orig_backup.name
        }
    except Exception as e:
        return {"error": f"Failed to pixelize image: {e}"}
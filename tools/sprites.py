"""
AdventureForge — Sprites & Animation Studio MCP Tools
"""
import json
from typing import Any
from config import config
from ._core import (
    _load_proj,
    _save_proj,
    _normalize_vlm_meta,
)


def list_sprites() -> dict[str, Any]:
    """List all character sprites registered in AdventureForge with their scales and role assignments."""
    proj = _load_proj()
    sprites_dict = proj.get("sprites", {})
    results = []
    for sid, sdata in sprites_dict.items():
        results.append({
            "id": sid,
            "name": sdata.get("name", sid),
            "scale": sdata.get("scale", 3.0),
            "sheet": sdata.get("sheet", ""),
            "anim_roles": sdata.get("anim_roles", {}),
            "is_player": (sid == proj.get("player_sprite")),
            "is_partner": (sid == proj.get("partner_sprite"))
        })
    return {"count": len(results), "sprites": results}


def get_sprite(sprite_id: str) -> dict[str, Any]:
    """Get full details of a sprite including all sliced frames and animation sequences."""
    proj = _load_proj()
    sp = proj.get("sprites", {}).get(sprite_id)
    if not sp:
        return {"error": f"Sprite '{sprite_id}' not found."}
    meta_rel = sp.get("metadata_file", f"/assets/sprites/{sprite_id}_slicer.json").lstrip("/")
    meta_path = config.DATA_DIR / meta_rel
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    _normalize_vlm_meta(meta, fallback_name=sprite_id)
    return {"sprite": sp, "metadata": meta}


def add_or_update_sprite_animation(
    sprite_id: str,
    anim_name: str,
    fps: float = 8.0,
    loop: bool = True,
    frame_indices: str = "0,1,2"
) -> dict[str, Any]:
    """Create or update an animation sequence for a character sprite. frame_indices is a comma-separated list of frame indices e.g. '0,1,2,3'."""
    proj = _load_proj()
    sp = proj.get("sprites", {}).get(sprite_id)
    if not sp:
        return {"error": f"Sprite '{sprite_id}' not found."}

    meta_rel = sp.get("metadata_file", f"/assets/sprites/{sprite_id}_slicer.json").lstrip("/")
    meta_path = config.DATA_DIR / meta_rel
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {"vlm": {"animations": []}}
    _normalize_vlm_meta(meta, fallback_name=sprite_id)

    indices = [int(s.strip()) for s in frame_indices.split(",") if s.strip().isdigit()]
    anims = meta["vlm"].get("animations", [])
    cur = next((a for a in anims if a.get("name") == anim_name), None)
    if cur is None:
        cur = {"name": anim_name, "fps": float(fps), "loop": bool(loop), "indices": indices}
        anims.append(cur)
    else:
        cur["fps"] = float(fps)
        cur["loop"] = bool(loop)
        cur["indices"] = indices

    meta["vlm"]["animations"] = anims
    meta_path.write_text(json.dumps(meta, indent=2))
    return {"status": "ok", "animation": cur, "total_animations": len(anims)}


def delete_sprite_animation(sprite_id: str, anim_name: str) -> dict[str, Any]:
    """Delete an animation sequence from a sprite."""
    proj = _load_proj()
    sp = proj.get("sprites", {}).get(sprite_id)
    if not sp:
        return {"error": f"Sprite '{sprite_id}' not found."}
    meta_rel = sp.get("metadata_file", f"/assets/sprites/{sprite_id}_slicer.json").lstrip("/")
    meta_path = config.DATA_DIR / meta_rel
    if not meta_path.exists():
        return {"error": f"Metadata file for '{sprite_id}' not found."}
    meta = json.loads(meta_path.read_text())
    _normalize_vlm_meta(meta, fallback_name=sprite_id)
    anims = meta["vlm"].get("animations", [])
    before = len(anims)
    meta["vlm"]["animations"] = [a for a in anims if a.get("name") != anim_name]
    meta_path.write_text(json.dumps(meta, indent=2))
    return {"status": "ok", "deleted": before - len(meta["vlm"]["animations"])}


def assign_sprite_direction_role(sprite_id: str, role: str, anim_name: str) -> dict[str, Any]:
    """Assign an animation to a movement role ('walk', 'up', 'down', or 'idle')."""
    proj = _load_proj()
    sp = proj.get("sprites", {}).get(sprite_id)
    if not sp:
        return {"error": f"Sprite '{sprite_id}' not found."}
    roles = sp.setdefault("anim_roles", {})
    roles[role] = anim_name

    meta_rel = sp.get("metadata_file", f"/assets/sprites/{sprite_id}_slicer.json").lstrip("/")
    meta_path = config.DATA_DIR / meta_rel
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        meta["anim_roles"] = roles
        meta_path.write_text(json.dumps(meta, indent=2))

    _save_proj(proj)
    return {"status": "ok", "sprite_id": sprite_id, "role": role, "animation": anim_name}


def set_sprite_scale(sprite_id: str, scale: float = 3.0) -> dict[str, Any]:
    """Change the visual rendering scale multiplier for a character sprite (e.g. 2.5 or 3.2)."""
    proj = _load_proj()
    sp = proj.get("sprites", {}).get(sprite_id)
    if not sp:
        return {"error": f"Sprite '{sprite_id}' not found."}
    sp["scale"] = max(0.5, min(10.0, float(scale)))
    _save_proj(proj)
    return {"status": "ok", "sprite_id": sprite_id, "scale": sp["scale"]}
"""
AdventureForge — Sprite Slicer

Computer-vision sprite sheet segmentation plus Gemini VLM animation mapping.

This started life as a standalone CLI tool and is now a first-class part of
AdventureForge: the web editor calls it through `POST /api/sprites/slice`, and
the MCP tool `vlm_auto_detect_and_place_props` shares the same coordinate
conventions.

Pipeline
--------
1. `segment_sprites`      — connected-component segmentation of a sprite sheet
2. `export_frames`        — transparent PNG frames written to disk
3. `create_annotated_image` — numbered overlay used for VLM grounding
4. `call_vlm_analyzer`    — Gemini maps frame indices to animation sequences
"""
from .slicer import (
    detect_background_color,
    segment_sprites,
    create_annotated_image,
    call_vlm_analyzer,
    export_frames,
    slice_spritesheet,
)

__all__ = [
    "detect_background_color",
    "segment_sprites",
    "create_annotated_image",
    "call_vlm_analyzer",
    "export_frames",
    "slice_spritesheet",
]

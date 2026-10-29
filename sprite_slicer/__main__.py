#!/usr/bin/env python3
"""
AdventureForge — sprite slicer CLI.

Usage:
    python3 -m sprite_slicer <spritesheet.png> [--out DIR] [--preview] [--hint TEXT]
"""
import argparse
import sys
from pathlib import Path

from .slicer import create_annotated_image, export_frames, segment_sprites


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Slice a sprite sheet into transparent frames with AdventureForge."
    )
    parser.add_argument("spritesheet", help="Path to the sprite sheet image (png/jpg)")
    parser.add_argument("--out", "-o", default="sprite_frames", help="Output directory for frames")
    parser.add_argument("--preview", action="store_true", help="Only save an annotated preview image")
    parser.add_argument("--hint", default="", help="Optional guidance for the VLM, e.g. '8-directional walk'")
    args = parser.parse_args()

    input_path = Path(args.spritesheet).resolve()
    if not input_path.exists():
        print(f"Error: {input_path} not found.")
        return 1

    print(f"[*] Processing sprite sheet: {input_path.name}")
    orig_img, boxes, bg_color = segment_sprites(input_path)
    print(f"[*] Detected {len(boxes)} sprite frames via CV segmentation.")

    if args.preview:
        preview_path = input_path.parent / f"{input_path.stem}_boxes_preview.png"
        create_annotated_image(orig_img, boxes).save(preview_path)
        print(f"[+] Preview saved to: {preview_path}")
        return 0

    out_dir = Path(args.out)
    frame_files = export_frames(orig_img, boxes, bg_color, out_dir)
    print(f"[+] Exported {len(frame_files)} frames to: {out_dir}")

    if args.hint:
        from .slicer import call_vlm_analyzer
        annotated = create_annotated_image(orig_img, boxes)
        vlm_result = call_vlm_analyzer(annotated, boxes, prompt_hint=args.hint)
        print(f"[+] VLM identified character '{vlm_result.get('character_name')}' "
              f"with {len(vlm_result.get('animations', []))} animations:")
        for a in vlm_result.get("animations", []):
            print(f"    - {a['name']}: {len(a['indices'])} frames @ {a['fps']} FPS (loop={a['loop']})")

    return 0


if __name__ == "__main__":
    sys.exit(main())

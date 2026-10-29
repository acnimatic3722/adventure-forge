#!/usr/bin/env python3
"""
AdventureForge — Pygame Point-and-Click Runtime Engine
Reads data/project.json and launches a playable LucasArts-style adventure window
with full support for Branching Dialog Trees and Choreographed Cutscenes.
"""

import os
import sys
import json
import math
import random
from pathlib import Path
from typing import Any

# Import config first
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import config

# Set DISPLAY if launched from web backend without display env
if "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = config.DISPLAY
if "XAUTHORITY" not in os.environ and config.XAUTHORITY:
    os.environ["XAUTHORITY"] = config.XAUTHORITY

import pygame

BASE_DIR = config.BASE_DIR
DATA_DIR = config.DATA_DIR
PROJECT_FILE = config.PROJECT_FILE

SCREEN_W = 1280
SCREEN_H = 860
VIEW_H = 720
UI_H = SCREEN_H - VIEW_H

VERBS = ["Walk to", "Look at", "Pick up", "Use", "Open", "Talk to"]


def resolve_asset_path(web_path: str) -> Path:
    if not web_path:
        return Path()
    clean = web_path.split("?")[0].strip()
    p = Path(clean)
    if p.is_absolute() and p.exists():
        return p
    clean = clean.lstrip("/")
    if clean.startswith("assets/"):
        return DATA_DIR / clean
    return DATA_DIR / "assets" / clean


def point_in_poly(x: float, y: float, poly: list[dict]) -> bool:
    if not poly or len(poly) < 3:
        return True
    inside = False
    n = len(poly)
    p1x, p1y = poly[0]["x"], poly[0]["y"]
    for i in range(1, n + 1):
        p2x, p2y = poly[i % n]["x"], poly[i % n]["y"]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


def clamp_to_poly_bounds(x: float, y: float, poly: list[dict]) -> tuple[float, float]:
    if not poly:
        return x, max(440, min(VIEW_H - 20, y))
    if point_in_poly(x, y, poly):
        return x, y
    xs = [p["x"] for p in poly]
    ys = [p["y"] for p in poly]
    cx = max(min(xs), min(max(xs), x))
    cy = max(min(ys), min(max(ys), y))
    return cx, cy


def wrap_text_lines(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
    words = (text or "").split(" ")
    lines: list[str] = []
    current = ""
    for w in words:
        test = f"{current} {w}".strip()
        if font.size(test)[0] <= max_width or not current:
            current = test
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines or [""]


class CharacterAnim:
    def __init__(self, sprite_cfg: dict):
        self.scale = float(sprite_cfg.get("scale", 3.0))
        self.animations: dict[str, list[pygame.Surface]] = {}
        self.fps_map: dict[str, float] = {}
        self.anim_roles: dict[str, Any] = dict(sprite_cfg.get("anim_roles") or {})
        self.load_frames(sprite_cfg)

    def load_frames(self, sprite_cfg: dict):
        frames_dir = resolve_asset_path(sprite_cfg.get("frames_dir", ""))
        meta_file = resolve_asset_path(sprite_cfg.get("metadata_file", ""))

        frame_surfaces = []
        if frames_dir.exists() and frames_dir.is_dir():
            pngs = sorted(p for p in frames_dir.glob("*.png") if ".orig." not in p.name)
            for p in pngs:
                try:
                    surf = pygame.image.load(str(p)).convert_alpha()
                    w = int(surf.get_width() * self.scale)
                    h = int(surf.get_height() * self.scale)
                    surf = pygame.transform.scale(surf, (w, h))
                    frame_surfaces.append(surf)
                except Exception:
                    pass

        if meta_file.exists() and frame_surfaces:
            try:
                meta = json.loads(meta_file.read_text())
                if isinstance(meta.get("anim_roles"), dict):
                    self.anim_roles.update(meta["anim_roles"])
                vlm_raw = meta.get("vlm", {})
                if isinstance(vlm_raw, list):
                    anims = []
                    for item in vlm_raw:
                        if isinstance(item, dict):
                            anims.extend(item.get("animations", []))
                elif isinstance(vlm_raw, dict):
                    anims = vlm_raw.get("animations", [])
                else:
                    anims = []
                for a in anims:
                    name = a.get("name", "idle_down")
                    indices = a.get("indices", [0])
                    role = a.get("role", "")
                    if role in ("walk", "up", "down", "idle") and not self.anim_roles.get(role):
                        self.anim_roles[role] = name
                    seq = [frame_surfaces[idx] for idx in indices if 0 <= idx < len(frame_surfaces)]
                    if seq:
                        self.animations[name] = seq
                        self.fps_map[name] = float(a.get("fps", 8.0))
            except Exception:
                pass

        if not self.animations and frame_surfaces:
            self.animations["idle_down"] = [frame_surfaces[0]]
            self.animations["walk_right"] = frame_surfaces[:min(6, len(frame_surfaces))]
            self.animations["talk_down"] = frame_surfaces[:min(4, len(frame_surfaces))]

    def resolve_role_anim(self, role: str) -> str:
        if not self.animations:
            return ""
        mapped = self.anim_roles.get(role, "")
        if mapped and mapped in self.animations:
            return mapped
        keys = list(self.animations.keys())
        if role == "walk":
            for cand in ["walk", "walk_side", "walk_right", "walk_left", "walk_right_casual"]:
                if cand in self.animations:
                    return cand
            for k in keys:
                kl = k.lower()
                if "walk" in kl and "up" not in kl and "down" not in kl:
                    return k
        elif role == "up":
            for cand in ["up", "walk_up", "idle_up"]:
                if cand in self.animations:
                    return cand
            for k in keys:
                if "up" in k.lower() or "back" in k.lower():
                    return k
        elif role == "down":
            for cand in ["down", "walk_down", "idle_down"]:
                if cand in self.animations:
                    return cand
            for k in keys:
                if "down" in k.lower() or "front" in k.lower():
                    return k
        elif role == "idle":
            if mapped == "__auto__":
                return ""
            if mapped and mapped in self.animations:
                return mapped
            for cand in ["idle", "idle_down", "stand"]:
                if cand in self.animations:
                    return cand
            for k in keys:
                if "idle" in k.lower():
                    return k
            return ""
        return keys[0]

    def get_directional_frame(self, direction: str, is_moving: bool, timer: float) -> pygame.Surface | None:
        if not self.animations:
            return None
        flip_when_left = self.anim_roles.get("flip_when_left", True)
        if direction in ("left", "right"):
            anim_name = self.resolve_role_anim("walk")
            flip_x = (direction == "left") if flip_when_left else (direction == "right")
        elif direction == "up":
            anim_name = self.resolve_role_anim("up")
            flip_x = False
        else:
            anim_name = self.resolve_role_anim("down")
            flip_x = False

        if not is_moving:
            idle_anim = self.resolve_role_anim("idle")
            if idle_anim:
                return self.get_frame(idle_anim, timer, flip_x=(direction == "left" and flip_when_left))
            return self.get_frame(anim_name, 0.0, flip_x=flip_x)

        return self.get_frame(anim_name, timer, flip_x=flip_x)

    def get_frame(self, anim_name: str, timer: float, flip_x: bool = False) -> pygame.Surface | None:
        if not self.animations:
            return None
        if anim_name not in self.animations:
            for cand in [anim_name, "walk", "walk_right_casual", "walk_right", "walk_down", "idle_down", next(iter(self.animations))]:
                if cand in self.animations:
                    anim_name = cand
                    break
        seq = self.animations[anim_name]
        fps = self.fps_map.get(anim_name, 8.0)
        idx = int(timer * fps) % len(seq)
        surf = seq[idx]
        if flip_x:
            return pygame.transform.flip(surf, True, False)
        return surf


class AdventureRuntime:
    def __init__(
        self,
        start_room_override: str | None = None,
        start_cutscene_override: str | None = None,
        start_dialog_override: str | None = None
    ):
        pygame.init()
        pygame.font.init()
        try:
            pygame.mixer.init()
        except Exception as e:
            print(f"Mixer init warning: {e}")
        self.sound_cache: dict[str, pygame.mixer.Sound] = {}
        self.current_music_file: str = ""
        self.project = json.loads(PROJECT_FILE.read_text())
        self.title = self.project.get("title", "AdventureForge Game")
        pygame.display.set_caption(f"{self.title} — Pygame Engine")
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        self.clock = pygame.time.Clock()

        self.font_main = pygame.font.SysFont("DejaVu Sans", 20, bold=True)
        self.font_dialog = pygame.font.SysFont("DejaVu Sans", 21, bold=True)
        self.font_choice = pygame.font.SysFont("DejaVu Sans", 17, bold=True)
        self.font_small = pygame.font.SysFont("DejaVu Sans", 15)

        # Game state
        self.flags: set[str] = set()
        self.picked_up_hotspots: set[str] = set()
        self.inventory: list[dict] = []
        self.items_by_id = {it["id"]: it for it in self.project.get("items", [])}
        self.dialogs_by_id = {d["id"]: d for d in self.project.get("dialogs", []) if "id" in d}
        self.cutscenes_by_id = {c["id"]: c for c in self.project.get("cutscenes", []) if "id" in c}
        self.played_cutscenes: set[str] = set()
        self.used_dialog_options: set[str] = set()

        self.item_icons: dict[str, pygame.Surface] = {}
        for it_id, it in self.items_by_id.items():
            p = resolve_asset_path(it.get("icon", ""))
            if p.exists():
                try:
                    s = pygame.image.load(str(p)).convert_alpha()
                    self.item_icons[it_id] = pygame.transform.smoothscale(s, (52, 52))
                except Exception:
                    pass

        # Load all character sprites (for player + partner + NPCs)
        self.sprite_anims: dict[str, CharacterAnim] = {}
        for sp_id, sp_cfg in self.project.get("sprites", {}).items():
            self.sprite_anims[sp_id] = CharacterAnim(sp_cfg)

        sprite_key = self.project.get("player_sprite", "sam")
        self.player_anim = self.sprite_anims.get(
            sprite_key,
            CharacterAnim(self.project.get("sprites", {}).get(sprite_key, {}))
        )
        self.player_name = self.project.get("sprites", {}).get(sprite_key, {}).get("name", "Sam").split("(")[0].strip() or "Sam"

        partner_key = self.project.get("partner_sprite", "")
        self.partner_anim: CharacterAnim | None = None
        self.partner_name = "Partner"
        if partner_key and partner_key in self.sprite_anims:
            self.partner_anim = self.sprite_anims[partner_key]
            self.partner_name = self.project.get("sprites", {}).get(partner_key, {}).get("name", "Max").split("(")[0].strip() or "Max"

        self.player_x = 300.0
        self.player_y = 560.0
        self.target_x = 300.0
        self.target_y = 560.0
        self.player_speed = 260.0
        self.facing_left = False
        self.move_dir = "down"
        self.player_override_anim: str = ""

        self.partner_x = 220.0
        self.partner_y = 570.0
        self.partner_target_x: float | None = None
        self.partner_target_y: float | None = None
        self.partner_speed = 245.0
        self.partner_move_dir = "down"
        self.partner_is_moving = False
        self.partner_override_anim: str = ""

        self.anim_timer = 0.0

        self.current_verb = "Walk to"
        self.selected_item: dict | None = None
        self.pending_action: dict | None = None

        self.speech_text: str = ""
        self.speech_speaker: str = ""
        self.speech_color: tuple[int, int, int] = (255, 245, 150)
        self.speech_timer: float = 0.0

        # Active Cutscene State
        self.active_cutscene: dict | None = None
        self.cutscene_step_idx: int = 0
        self.cutscene_step_timer: float = 0.0
        self.cutscene_step_duration: float = 0.0
        self.fade_effect: str = ""
        self.fade_duration: float = 1.0
        self.fade_timer: float = 0.0

        # Active Dialog Tree State
        self.active_dialog: dict | None = None
        self.active_dialog_node: dict | None = None
        self.dialog_phase: str = ""  # "npc_speaking" | "choose_option" | "player_speaking" | "reply_speaking"
        self.pending_dialog_option: dict | None = None
        self.dialog_scroll: int = 0

        self.rooms_by_id = {r["id"]: r for r in self.project.get("rooms", [])}
        start_id = start_room_override or self.project.get("start_room") or next(iter(self.rooms_by_id), "")
        self.current_room: dict = {}
        self.bg_surface: pygame.Surface | None = None
        self.hotspot_icons: dict[str, pygame.Surface] = {}
        self.change_room(start_id, suppress_cutscene=bool(start_cutscene_override or start_dialog_override))

        if start_cutscene_override and start_cutscene_override in self.cutscenes_by_id:
            self.start_cutscene(start_cutscene_override, force=True)
        elif start_dialog_override and start_dialog_override in self.dialogs_by_id:
            self.start_dialog(start_dialog_override)

    def say(
        self,
        text: str,
        duration: float = 4.0,
        speaker: str = "",
        color: tuple[int, int, int] = (255, 245, 150)
    ):
        self.speech_text = text
        self.speech_speaker = speaker
        self.speech_color = color
        self.speech_timer = duration

    def play_sound(self, sound_path_or_url: str):
        if not sound_path_or_url or not pygame.mixer.get_init():
            return
        p = resolve_asset_path(sound_path_or_url)
        if not p.exists() or not p.is_file():
            return
        str_p = str(p)
        try:
            if str_p not in self.sound_cache:
                self.sound_cache[str_p] = pygame.mixer.Sound(str_p)
            self.sound_cache[str_p].play()
        except Exception as e:
            print(f"Error playing sound {str_p}: {e}")

    def play_music(self, music_path_or_url: str, loop: bool = True):
        if not pygame.mixer.get_init():
            return
        if not music_path_or_url:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
            self.current_music_file = ""
            return
        if music_path_or_url == self.current_music_file:
            return
        p = resolve_asset_path(music_path_or_url)
        if not p.exists() or not p.is_file():
            return
        str_p = str(p)
        try:
            pygame.mixer.music.load(str_p)
            pygame.mixer.music.play(-1 if loop else 0)
            self.current_music_file = music_path_or_url
        except Exception as e:
            print(f"Error playing music {str_p}: {e}")

    def give_inventory_item(self, item_id: str):
        if not item_id:
            return
        if any(i.get("id") == item_id for i in self.inventory):
            return
        if item_id in self.items_by_id:
            self.inventory.append(self.items_by_id[item_id])
        else:
            self.inventory.append({"id": item_id, "name": item_id, "icon": ""})

    def set_story_flag(self, flag_name: str, allow_cutscene_trigger: bool = True):
        if not flag_name:
            return
        self.flags.add(flag_name)
        if allow_cutscene_trigger and not self.active_cutscene:
            for cs in self.project.get("cutscenes", []):
                if cs.get("trigger_type") == "on_flag_set" and cs.get("trigger_target") == flag_name:
                    self.start_cutscene(cs["id"])
                    break

    def change_room(self, room_id: str, spawn: dict | None = None, suppress_cutscene: bool = False):
        room = self.rooms_by_id.get(room_id)
        if not room:
            return
        self.current_room = room
        bg_path = resolve_asset_path(room.get("background", ""))
        if bg_path.exists():
            try:
                surf = pygame.image.load(str(bg_path)).convert()
                self.bg_surface = pygame.transform.smoothscale(surf, (SCREEN_W, VIEW_H))
            except Exception:
                self.bg_surface = None
        else:
            self.bg_surface = None

        self.hotspot_icons.clear()
        for hs in room.get("hotspots", []):
            icon_url = hs.get("icon") or ""
            if not icon_url and hs.get("type") == "pickup" and hs.get("item_id") in self.items_by_id:
                icon_url = self.items_by_id[hs["item_id"]].get("icon", "")
            icon_p = resolve_asset_path(icon_url)
            if icon_p.exists():
                try:
                    s = pygame.image.load(str(icon_p)).convert_alpha()
                    r = hs.get("rect", {"w": 64, "h": 64})
                    self.hotspot_icons[hs["id"]] = pygame.transform.smoothscale(
                        s, (max(24, int(r["w"])), max(24, int(r["h"])))
                    )
                except Exception:
                    pass

        sp = spawn or room.get("player_start") or {"x": 300, "y": 560}
        self.player_x = float(sp["x"])
        self.player_y = float(sp["y"])
        self.target_x = self.player_x
        self.target_y = self.player_y
        px, py = clamp_to_poly_bounds(self.player_x - 125.0, self.player_y + 10.0, room.get("walkable_polygon", []))
        self.partner_x, self.partner_y = px, py
        self.partner_target_x = None
        self.partner_target_y = None
        self.partner_is_moving = False
        self.pending_action = None

        room_music = room.get("music") or room.get("ambient_sound") or ""
        if room_music or "music" in room:
            self.play_music(room_music)

        if not suppress_cutscene and not self.active_cutscene:
            for cs in self.project.get("cutscenes", []):
                if cs.get("trigger_type") == "on_enter_room" and cs.get("trigger_target") == room_id:
                    if self.start_cutscene(cs["id"]):
                        break

    # ==================== CUTSCENE ENGINE ====================
    def start_cutscene(self, cutscene_id: str, force: bool = False) -> bool:
        cs = self.cutscenes_by_id.get(cutscene_id)
        if not cs:
            return False
        if not force:
            if cs.get("once", True) and cutscene_id in self.played_cutscenes:
                return False
            req = cs.get("requires_flag", "")
            if req and req not in self.flags:
                return False

        self.played_cutscenes.add(cutscene_id)
        self.active_dialog = None
        self.active_cutscene = cs
        self.cutscene_step_idx = -1
        self.pending_action = None
        self.advance_cutscene_step()
        return True

    def advance_cutscene_step(self):
        if not self.active_cutscene:
            return
        self.player_override_anim = ""
        self.partner_override_anim = ""
        self.partner_target_x = None
        self.partner_target_y = None
        self.speech_text = ""
        self.speech_timer = 0.0

        steps = self.active_cutscene.get("steps", [])
        self.cutscene_step_idx += 1
        if self.cutscene_step_idx >= len(steps):
            self.finish_cutscene()
            return

        step = steps[self.cutscene_step_idx]
        stype = step.get("type", "say")
        dur = float(step.get("duration") or 0.0)
        self.cutscene_step_timer = 0.0

        if stype == "say":
            actor = step.get("actor", "player")
            text = step.get("text", "...")
            if dur <= 0:
                dur = max(2.5, min(7.0, len(text) * 0.065))
            self.cutscene_step_duration = dur
            speaker_label, col = self.resolve_actor_style(actor)
            self.say(text, duration=dur + 0.5, speaker=speaker_label, color=col)

        elif stype == "walk":
            actor = step.get("actor", "player")
            tx = float(step.get("x", self.player_x))
            ty = float(step.get("y", self.player_y))
            if actor == "partner" and self.partner_anim is not None:
                self.partner_target_x = tx
                self.partner_target_y = ty
            else:
                self.target_x = tx
                self.target_y = ty
            self.cutscene_step_duration = 15.0  # timeout guard

        elif stype == "wait":
            self.cutscene_step_duration = max(0.2, dur or 1.0)

        elif stype == "change_room":
            target_r = step.get("room_id", "")
            spawn = None
            if step.get("x") is not None and step.get("y") is not None:
                spawn = {"x": float(step["x"]), "y": float(step["y"])}
            if target_r:
                self.change_room(target_r, spawn=spawn, suppress_cutscene=True)
            self.advance_cutscene_step()

        elif stype == "fade":
            self.fade_effect = step.get("effect", "fade_in")
            self.fade_duration = max(0.2, dur or 1.0)
            self.fade_timer = 0.0
            self.cutscene_step_duration = self.fade_duration

        elif stype == "play_anim":
            actor = step.get("actor", "player")
            anim_name = step.get("anim", "idle_down")
            self.cutscene_step_duration = max(0.4, dur or 1.5)
            if actor == "partner":
                self.partner_override_anim = anim_name
            elif actor == "player":
                self.player_override_anim = anim_name
            else:
                for hs in self.current_room.get("hotspots", []):
                    if hs.get("id") == actor:
                        hs["npc_anim"] = anim_name

        elif stype in ("play_sound", "sound"):
            sfx = step.get("sound_effect") or step.get("sound") or step.get("file", "")
            if sfx:
                self.play_sound(sfx)
            self.cutscene_step_duration = max(0.1, dur or 0.1)
            if dur <= 0:
                self.advance_cutscene_step()

        elif stype in ("play_music", "music"):
            bgm = step.get("music") or step.get("file", "")
            if bgm is not None:
                self.play_music(bgm)
            self.cutscene_step_duration = max(0.1, dur or 0.1)
            if dur <= 0:
                self.advance_cutscene_step()

        elif stype == "give_item":
            self.give_inventory_item(step.get("item_id", ""))
            self.advance_cutscene_step()

        elif stype == "set_flag":
            self.set_story_flag(step.get("flag", ""), allow_cutscene_trigger=False)
            self.advance_cutscene_step()

        elif stype == "start_dialog":
            dlg_id = step.get("dialog_id", "")
            self.finish_cutscene()
            if dlg_id:
                self.start_dialog(dlg_id)

        else:
            self.advance_cutscene_step()

    def finish_cutscene(self):
        if not self.active_cutscene:
            return
        cs = self.active_cutscene
        self.active_cutscene = None
        self.player_override_anim = ""
        self.partner_override_anim = ""
        self.partner_target_x = None
        self.partner_target_y = None
        self.fade_effect = ""
        self.speech_text = ""
        self.speech_timer = 0.0
        if cs.get("sets_flag"):
            self.set_story_flag(cs["sets_flag"])

    def resolve_actor_style(self, actor: str) -> tuple[str, tuple[int, int, int]]:
        if actor == "player":
            return self.player_name, (255, 235, 130)
        if actor == "partner":
            return self.partner_name, (140, 230, 255)
        if actor == "narrator":
            return "Narrator", (210, 215, 235)
        for hs in self.current_room.get("hotspots", []):
            if hs.get("id") == actor:
                return hs.get("name", actor), (160, 250, 175)
        return actor.capitalize(), (160, 250, 175)

    # ==================== DIALOG TREE ENGINE ====================
    def start_dialog(self, dialog_id: str) -> bool:
        dlg = self.dialogs_by_id.get(dialog_id)
        if not dlg:
            return False
        nodes = dlg.get("nodes", [])
        if not nodes:
            return False
        root_id = dlg.get("root_node") or nodes[0].get("id")
        root_node = next((n for n in nodes if n.get("id") == root_id), nodes[0])

        self.active_cutscene = None
        self.active_dialog = dlg
        self.enter_dialog_node(root_node)
        return True

    def enter_dialog_node(self, node: dict):
        self.active_dialog_node = node
        self.dialog_scroll = 0
        npc_text = (node.get("npc_text") or "").strip()
        speaker = node.get("speaker", "npc")
        if speaker == "player":
            spk_name, col = self.player_name, (255, 235, 130)
        elif speaker == "partner":
            spk_name, col = self.partner_name, (140, 230, 255)
        else:
            spk_name = (self.active_dialog or {}).get("npc_name") or "NPC"
            col = (165, 250, 180)

        if npc_text:
            self.dialog_phase = "npc_speaking"
            dur = max(2.2, min(6.0, len(npc_text) * 0.06))
            self.say(npc_text, duration=dur, speaker=spk_name, color=col)
        else:
            self.dialog_phase = "choose_option"
            self.speech_text = ""
            self.speech_timer = 0.0

    def get_available_dialog_options(self) -> list[tuple[int, dict]]:
        if not self.active_dialog_node or not self.active_dialog:
            return []
        dlg_id = self.active_dialog.get("id", "dlg")
        node_id = self.active_dialog_node.get("id", "node")
        avail: list[tuple[int, dict]] = []
        for idx, opt in enumerate(self.active_dialog_node.get("options", [])):
            opt_key = f"{dlg_id}:{node_id}:{idx}"
            if opt.get("once") and opt_key in self.used_dialog_options:
                continue
            req = opt.get("requires_flag", "")
            if req and req not in self.flags:
                continue
            hide_f = opt.get("hide_if_flag", "")
            if hide_f and hide_f in self.flags:
                continue
            avail.append((idx, opt))
        return avail

    def select_dialog_option(self, orig_idx: int, opt: dict):
        if not self.active_dialog or not self.active_dialog_node:
            return
        dlg_id = self.active_dialog.get("id", "dlg")
        node_id = self.active_dialog_node.get("id", "node")
        opt_key = f"{dlg_id}:{node_id}:{orig_idx}"
        if opt.get("once"):
            self.used_dialog_options.add(opt_key)

        if opt.get("sets_flag"):
            self.set_story_flag(opt["sets_flag"], allow_cutscene_trigger=False)
        if opt.get("gives_item"):
            self.give_inventory_item(opt["gives_item"])

        self.pending_dialog_option = opt
        p_text = (opt.get("text") or "").strip()
        if p_text:
            self.dialog_phase = "player_speaking"
            dur = max(1.8, min(5.0, len(p_text) * 0.055))
            self.say(p_text, duration=dur, speaker=self.player_name, color=(255, 235, 130))
        else:
            self.advance_dialog_after_player_line()

    def advance_dialog_after_player_line(self):
        opt = self.pending_dialog_option or {}
        reply = (opt.get("reply_text") or "").strip()
        if reply:
            self.dialog_phase = "reply_speaking"
            spk_name = (self.active_dialog or {}).get("npc_name") or self.partner_name
            dur = max(2.2, min(6.0, len(reply) * 0.06))
            self.say(reply, duration=dur, speaker=spk_name, color=(165, 250, 180))
        else:
            self.finish_dialog_option_transition()

    def finish_dialog_option_transition(self):
        opt = self.pending_dialog_option or {}
        self.pending_dialog_option = None

        # Check if option triggers a cutscene
        cs_id = opt.get("triggers_cutscene", "")
        if cs_id and cs_id in self.cutscenes_by_id:
            self.active_dialog = None
            self.active_dialog_node = None
            self.dialog_phase = ""
            self.start_cutscene(cs_id, force=True)
            return

        next_id = opt.get("next_node", "__exit__")
        if not next_id or next_id == "__exit__":
            self.active_dialog = None
            self.active_dialog_node = None
            self.dialog_phase = ""
            self.speech_text = ""
            self.speech_timer = 0.0
            return

        if next_id == "__stay__" and self.active_dialog_node:
            self.dialog_phase = "choose_option"
            return

        nodes = (self.active_dialog or {}).get("nodes", [])
        target_node = next((n for n in nodes if n.get("id") == next_id), None)
        if target_node:
            self.enter_dialog_node(target_node)
        else:
            self.active_dialog = None
            self.active_dialog_node = None
            self.dialog_phase = ""

    # ==================== HOTSPOTS & INTERACTION ====================
    def get_hovered_hotspot(self, mx: int, my: int) -> dict | None:
        if my >= VIEW_H:
            return None
        for hs in reversed(self.current_room.get("hotspots", [])):
            if hs["id"] in self.picked_up_hotspots:
                continue
            r = hs.get("rect", {"x": 0, "y": 0, "w": 50, "h": 50})
            rect = pygame.Rect(r["x"], r["y"], r["w"], r["h"])
            if rect.collidepoint(mx, my):
                return hs
        return None

    def is_hovering_partner(self, mx: int, my: int) -> bool:
        if self.partner_anim is None or my >= VIEW_H:
            return False
        rect = pygame.Rect(int(self.partner_x - 42), int(self.partner_y - 120), 84, 125)
        return rect.collidepoint(mx, my)

    def execute_hotspot_interaction(self, hs: dict, verb: str, item: dict | None):
        # 1. Check puzzles first if using an item on hotspot
        if item is not None:
            for puz in self.project.get("puzzles", []):
                if puz.get("trigger") == "use_item_on_hotspot":
                    if puz.get("item_id") == item["id"] and puz.get("target_id") == hs["id"]:
                        req = puz.get("requires_flag", "")
                        if req and req not in self.flags:
                            self.say("I can't do that yet.", speaker=self.player_name)
                            return
                        if puz.get("consume_item", False):
                            self.inventory = [i for i in self.inventory if i["id"] != item["id"]]
                        self.selected_item = None
                        self.current_verb = "Walk to"
                        if hs.get("type") == "exit":
                            hs["locked"] = False
                        if puz.get("sound_effect"):
                            self.play_sound(puz["sound_effect"])
                        elif puz.get("sound"):
                            self.play_sound(puz["sound"])
                        if puz.get("gives_item"):
                            self.give_inventory_item(puz["gives_item"])
                        set_f = puz.get("sets_flag", "")
                        if set_f:
                            self.set_story_flag(set_f)
                        if puz.get("cutscene_id") and puz["cutscene_id"] in self.cutscenes_by_id:
                            self.start_cutscene(puz["cutscene_id"], force=True)
                            return
                        self.say(puz.get("success_text", "That worked!"), speaker=self.player_name)
                        return
            self.say("That doesn't seem to work together.", speaker=self.player_name)
            self.selected_item = None
            return

        # 2. Check standard verbs
        hs_type = hs.get("type", "prop")
        if verb == "Look at":
            self.say(hs.get("look_text") or f"It's {hs.get('name', 'something interesting')}.", speaker=self.player_name)
        elif verb == "Pick up":
            if hs_type == "pickup":
                item_id = hs.get("item_id")
                self.picked_up_hotspots.add(hs["id"])
                if item_id and item_id in self.items_by_id:
                    self.inventory.append(self.items_by_id[item_id])
                else:
                    self.inventory.append({
                        "id": item_id or hs["id"],
                        "name": hs.get("name", "Item"),
                        "icon": hs.get("icon", "")
                    })
                if hs.get("cutscene_id") and hs["cutscene_id"] in self.cutscenes_by_id:
                    self.start_cutscene(hs["cutscene_id"], force=True)
                else:
                    if hs.get("sound_effect"):
                        self.play_sound(hs["sound_effect"])
                    elif hs.get("pickup_sound"):
                        self.play_sound(hs["pickup_sound"])
                    self.say(hs.get("pickup_text") or f"Picked up {hs.get('name')}.", speaker=self.player_name)
            else:
                self.say("I don't need to carry that around.", speaker=self.player_name)
        elif verb in ("Open", "Walk to", "Use") and hs_type == "exit":
            req_flag = hs.get("required_flag", "")
            is_locked = hs.get("locked", False) and (not req_flag or req_flag not in self.flags)
            if is_locked:
                self.say(hs.get("locked_text") or "It's locked.", speaker=self.player_name)
            else:
                if hs.get("sound_effect"):
                    self.play_sound(hs["sound_effect"])
                elif hs.get("door_sound"):
                    self.play_sound(hs["door_sound"])
                if hs.get("cutscene_id") and hs["cutscene_id"] in self.cutscenes_by_id:
                    self.start_cutscene(hs["cutscene_id"])
                    return
                target_room = hs.get("target_room")
                if target_room:
                    self.change_room(target_room, hs.get("target_spawn"))
                else:
                    self.say("This exit leads nowhere yet.", speaker=self.player_name)
        elif verb == "Talk to":
            if hs.get("dialog_id") and hs["dialog_id"] in self.dialogs_by_id:
                self.start_dialog(hs["dialog_id"])
                return
            if hs.get("cutscene_id") and hs["cutscene_id"] in self.cutscenes_by_id:
                self.start_cutscene(hs["cutscene_id"], force=True)
                return
            spk = hs.get("name", "NPC") if hs_type == "npc" else self.player_name
            col = (165, 250, 180) if hs_type == "npc" else (255, 235, 130)
            self.say(hs.get("talk_text") or "No response.", speaker=spk, color=col)
        elif verb == "Use":
            if hs.get("cutscene_id") and hs["cutscene_id"] in self.cutscenes_by_id:
                self.start_cutscene(hs["cutscene_id"], force=True)
                return
            if hs.get("dialog_id") and hs["dialog_id"] in self.dialogs_by_id:
                self.start_dialog(hs["dialog_id"])
                return
            for puz in self.project.get("puzzles", []):
                if puz.get("trigger") == "interact_hotspot" and puz.get("target_id") == hs["id"]:
                    req = puz.get("requires_flag", "")
                    if not req or req in self.flags:
                        if puz.get("sound_effect"):
                            self.play_sound(puz["sound_effect"])
                        elif puz.get("sound"):
                            self.play_sound(puz["sound"])
                        if puz.get("sets_flag"):
                            self.set_story_flag(puz["sets_flag"])
                        if puz.get("cutscene_id") and puz["cutscene_id"] in self.cutscenes_by_id:
                            self.start_cutscene(puz["cutscene_id"], force=True)
                            return
                        self.say(puz.get("success_text", "Activated!"), speaker=self.player_name)
                        return
            self.say(hs.get("use_text") or "Nothing happens.", speaker=self.player_name)
        else:
            self.say(hs.get("look_text") or "Hmm.", speaker=self.player_name)

    def handle_click(self, mx: int, my: int, right_click: bool = False):
        # 1. If a Cutscene is active, clicking advances the current step
        if self.active_cutscene:
            steps = self.active_cutscene.get("steps", [])
            if 0 <= self.cutscene_step_idx < len(steps):
                cur_step = steps[self.cutscene_step_idx]
                if cur_step.get("type") == "walk":
                    actor = cur_step.get("actor", "player")
                    if actor == "partner" and self.partner_target_x is not None:
                        self.partner_x, self.partner_y = self.partner_target_x, self.partner_target_y
                    else:
                        self.player_x, self.player_y = self.target_x, self.target_y
            self.advance_cutscene_step()
            return

        # 2. If a Dialog Tree is active, handle clicks on dialog lines or options
        if self.active_dialog:
            if self.dialog_phase == "npc_speaking":
                self.speech_timer = 0.0
                self.speech_text = ""
                self.dialog_phase = "choose_option"
                return
            elif self.dialog_phase == "player_speaking":
                self.speech_timer = 0.0
                self.speech_text = ""
                self.advance_dialog_after_player_line()
                return
            elif self.dialog_phase == "reply_speaking":
                self.speech_timer = 0.0
                self.speech_text = ""
                self.finish_dialog_option_transition()
                return
            elif self.dialog_phase == "choose_option":
                avail = self.get_available_dialog_options()
                if not avail:
                    self.active_dialog = None
                    return
                if my >= VIEW_H:
                    for disp_i, (orig_idx, opt) in enumerate(avail[self.dialog_scroll:self.dialog_scroll + 4]):
                        ry = VIEW_H + 34 + disp_i * 25
                        rect = pygame.Rect(24, ry, SCREEN_W - 120, 24)
                        if rect.collidepoint(mx, my):
                            self.select_dialog_option(orig_idx, opt)
                            return
                return

        # 3. Normal Gameplay UI bar click
        if my >= VIEW_H:
            for idx, v in enumerate(VERBS):
                col = idx % 3
                row = idx // 3
                bx = 20 + col * 145
                by = VIEW_H + 42 + row * 44
                rect = pygame.Rect(bx, by, 135, 38)
                if rect.collidepoint(mx, my):
                    self.current_verb = v
                    self.selected_item = None
                    return

            for idx, item in enumerate(self.inventory):
                ix = 520 + idx * 72
                iy = VIEW_H + 45
                rect = pygame.Rect(ix, iy, 64, 64)
                if rect.collidepoint(mx, my):
                    if right_click or self.current_verb == "Look at":
                        self.say(item.get("description") or f"It's my {item.get('name')}.", speaker=self.player_name)
                    elif self.selected_item and self.selected_item["id"] != item["id"]:
                        for puz in self.project.get("puzzles", []):
                            if puz.get("trigger") == "combine_items":
                                pair = {puz.get("item_id"), puz.get("target_id")}
                                if pair == {self.selected_item["id"], item["id"]}:
                                    if puz.get("consume_item", False):
                                        self.inventory = [i for i in self.inventory if i["id"] not in pair]
                                    if puz.get("sound_effect"):
                                        self.play_sound(puz["sound_effect"])
                                    elif puz.get("sound"):
                                        self.play_sound(puz["sound"])
                                    if puz.get("gives_item"):
                                        self.give_inventory_item(puz["gives_item"])
                                    if puz.get("sets_flag"):
                                        self.set_story_flag(puz["sets_flag"])
                                    self.say(puz.get("success_text", "Combined!"), speaker=self.player_name)
                                    self.selected_item = None
                                    return
                        self.say("Those two don't fit together.", speaker=self.player_name)
                        self.selected_item = None
                    else:
                        self.selected_item = item
                        self.current_verb = "Use"
                    return
            return

        # 4. Viewport click
        hs = self.get_hovered_hotspot(mx, my)
        if right_click and hs:
            self.execute_hotspot_interaction(hs, "Look at", None)
            return

        if hs:
            walk_pt = hs.get("walk_to")
            if walk_pt:
                wx, wy = float(walk_pt["x"]), float(walk_pt["y"])
            else:
                r = hs.get("rect", {"x": mx, "y": my, "w": 0, "h": 0})
                wx, wy = float(r["x"] + r["w"] / 2), float(r["y"] + r["h"])
            wx, wy = clamp_to_poly_bounds(wx, wy, self.current_room.get("walkable_polygon", []))
            self.target_x, self.target_y = wx, wy

            verb_to_run = self.current_verb
            if verb_to_run == "Walk to" and self.selected_item is None:
                t = hs.get("type", "prop")
                if t == "pickup":
                    verb_to_run = "Pick up"
                elif t == "exit":
                    verb_to_run = "Open"
                elif t == "npc" or hs.get("dialog_id"):
                    verb_to_run = "Talk to"
                else:
                    verb_to_run = "Look at"

            self.pending_action = {
                "hotspot": hs,
                "verb": verb_to_run,
                "item": self.selected_item
            }
        elif self.is_hovering_partner(mx, my) and self.current_verb in ("Talk to", "Look at"):
            if self.current_verb == "Look at":
                self.say(f"It's my freelance partner, {self.partner_name}.", speaker=self.player_name)
            else:
                partner_dlg = self.project.get("partner_dialog_id") or next(
                    (d["id"] for d in self.project.get("dialogs", []) if self.partner_name.lower() in d.get("npc_name", "").lower()),
                    ""
                )
                if partner_dlg and partner_dlg in self.dialogs_by_id:
                    self.start_dialog(partner_dlg)
                else:
                    self.say("You crack me up, little buddy.", speaker=self.partner_name, color=(140, 230, 255))
        else:
            poly = self.current_room.get("walkable_polygon", [])
            wx, wy = clamp_to_poly_bounds(float(mx), float(my), poly)
            self.target_x, self.target_y = wx, wy
            self.pending_action = None

    def update(self, dt: float):
        self.anim_timer += dt
        if self.speech_timer > 0:
            self.speech_timer -= dt
            if self.speech_timer <= 0:
                self.speech_text = ""
                if self.active_dialog:
                    if self.dialog_phase == "npc_speaking":
                        self.dialog_phase = "choose_option"
                    elif self.dialog_phase == "player_speaking":
                        self.advance_dialog_after_player_line()
                    elif self.dialog_phase == "reply_speaking":
                        self.finish_dialog_option_transition()

        # Player movement update
        dx = self.target_x - self.player_x
        dy = self.target_y - self.player_y
        dist = math.hypot(dx, dy)
        player_moving = dist > 4.0
        if player_moving:
            step = min(dist, self.player_speed * dt)
            self.player_x += (dx / dist) * step
            self.player_y += (dy / dist) * step
            if abs(dx) >= abs(dy) * 0.75:
                self.move_dir = "left" if dx < 0 else "right"
                self.facing_left = dx < 0
            else:
                self.move_dir = "up" if dy < 0 else "down"
        else:
            self.player_x, self.player_y = self.target_x, self.target_y
            if self.pending_action and not self.active_cutscene and not self.active_dialog:
                act = self.pending_action
                self.pending_action = None
                self.execute_hotspot_interaction(act["hotspot"], act["verb"], act["item"])

        # Partner movement update (scripted cutscene walk OR normal follower AI)
        if self.partner_anim is not None:
            if self.partner_target_x is not None and self.partner_target_y is not None:
                pdx = self.partner_target_x - self.partner_x
                pdy = self.partner_target_y - self.partner_y
                pdist = math.hypot(pdx, pdy)
                if pdist > 4.0:
                    self.partner_is_moving = True
                    pstep = min(pdist, self.partner_speed * dt)
                    self.partner_x += (pdx / pdist) * pstep
                    self.partner_y += (pdy / pdist) * pstep
                    if abs(pdx) >= abs(pdy) * 0.75:
                        self.partner_move_dir = "left" if pdx < 0 else "right"
                    else:
                        self.partner_move_dir = "up" if pdy < 0 else "down"
                else:
                    self.partner_x, self.partner_y = self.partner_target_x, self.partner_target_y
                    self.partner_is_moving = False
            elif not self.active_cutscene:
                pdx = self.player_x - self.partner_x
                pdy = self.player_y - self.partner_y
                pdist = math.hypot(pdx, pdy)
                follow_start_dist = 140.0
                follow_stop_dist = 120.0
                threshold = follow_stop_dist if self.partner_is_moving else follow_start_dist
                if pdist > threshold:
                    self.partner_is_moving = True
                    pstep = min(pdist - follow_stop_dist + 2.0, self.partner_speed * dt)
                    nx = self.partner_x + (pdx / pdist) * pstep
                    ny = self.partner_y + (pdy / pdist) * pstep
                    nx, ny = clamp_to_poly_bounds(nx, ny, self.current_room.get("walkable_polygon", []))
                    self.partner_x, self.partner_y = nx, ny
                    if abs(pdx) >= abs(pdy) * 0.75:
                        self.partner_move_dir = "left" if pdx < 0 else "right"
                    else:
                        self.partner_move_dir = "up" if pdy < 0 else "down"
                else:
                    self.partner_is_moving = False
            else:
                self.partner_is_moving = False

        # Cutscene step progression
        if self.active_cutscene:
            self.cutscene_step_timer += dt
            if self.fade_effect:
                self.fade_timer += dt
            steps = self.active_cutscene.get("steps", [])
            if 0 <= self.cutscene_step_idx < len(steps):
                cur_step = steps[self.cutscene_step_idx]
                stype = cur_step.get("type", "say")
                if stype == "walk":
                    actor = cur_step.get("actor", "player")
                    if actor == "partner" and self.partner_anim is not None:
                        if not self.partner_is_moving:
                            self.advance_cutscene_step()
                    else:
                        if not player_moving:
                            self.advance_cutscene_step()
                elif self.cutscene_step_timer >= self.cutscene_step_duration:
                    self.advance_cutscene_step()

        # Check if an active dialog has 0 options on choose_option (auto-exit after speech)
        if self.active_dialog and self.dialog_phase == "choose_option":
            avail = self.get_available_dialog_options()
            if not avail:
                self.active_dialog = None
                self.active_dialog_node = None
                self.dialog_phase = ""

    def draw(self):
        # Camera shake offset if active
        ox, oy = 0, 0
        if self.active_cutscene and self.fade_effect == "shake":
            ox = random.randint(-7, 7)
            oy = random.randint(-5, 5)

        # 1. Room Background
        if self.bg_surface:
            self.screen.blit(self.bg_surface, (ox, oy))
        else:
            self.screen.fill((28, 32, 46), pygame.Rect(0, 0, SCREEN_W, VIEW_H))

        # 2. Draw visible Hotspots (Props, Pickups, Doors, and Animated NPCs)
        for hs in self.current_room.get("hotspots", []):
            if hs["id"] in self.picked_up_hotspots:
                continue
            r = hs.get("rect", {"x": 0, "y": 0, "w": 50, "h": 50})
            if hs.get("type") == "npc" and hs.get("sprite_id") in self.sprite_anims:
                npc_anim_obj = self.sprite_anims[hs["sprite_id"]]
                npc_anim_name = hs.get("npc_anim") or "idle_down"
                npc_frame = npc_anim_obj.get_frame(npc_anim_name, self.anim_timer)
                if npc_frame:
                    scaled_npc = pygame.transform.scale(npc_frame, (max(24, int(r["w"])), max(24, int(r["h"]))))
                    self.screen.blit(scaled_npc, (r["x"] + ox, r["y"] + oy))
                    continue
            if hs["id"] in self.hotspot_icons:
                self.screen.blit(self.hotspot_icons[hs["id"]], (r["x"] + ox, r["y"] + oy))

        # 3. Draw Partner & Player Sprites (Y-sorted for depth)
        dx = self.target_x - self.player_x
        dy = self.target_y - self.player_y
        is_moving = math.hypot(dx, dy) > 4.0

        chars_to_draw = []
        if self.player_override_anim:
            player_frame = self.player_anim.get_frame(self.player_override_anim, self.anim_timer)
        else:
            player_frame = self.player_anim.get_directional_frame(self.move_dir, is_moving, self.anim_timer)
        chars_to_draw.append((self.player_y, self.player_x, player_frame, (240, 200, 80)))

        if self.partner_anim is not None:
            if self.partner_override_anim:
                partner_frame = self.partner_anim.get_frame(self.partner_override_anim, self.anim_timer)
            else:
                partner_frame = self.partner_anim.get_directional_frame(
                    self.partner_move_dir, self.partner_is_moving, self.anim_timer
                )
            chars_to_draw.append((self.partner_y, self.partner_x, partner_frame, (120, 210, 255)))

        chars_to_draw.sort(key=lambda item: item[0])
        for cy, cx, cframe, fallback_col in chars_to_draw:
            if cframe:
                fw, fh = cframe.get_size()
                self.screen.blit(cframe, (int(cx - fw / 2) + ox, int(cy - fh) + oy))
            else:
                pygame.draw.circle(self.screen, fallback_col, (int(cx) + ox, int(cy - 40) + oy), 22)

        # 3b. Cutscene Fade / Flash Overlay & Letterbox Bars
        if self.active_cutscene:
            if self.fade_effect in ("fade_in", "fade_out", "flash_white"):
                progress = min(1.0, max(0.0, self.fade_timer / max(0.01, self.fade_duration)))
                if self.fade_effect == "fade_in":
                    alpha = int(255 * (1.0 - progress))
                    col = (0, 0, 0)
                elif self.fade_effect == "fade_out":
                    alpha = int(255 * progress)
                    col = (0, 0, 0)
                else:
                    alpha = int(255 * (1.0 - progress))
                    col = (255, 255, 255)
                overlay = pygame.Surface((SCREEN_W, VIEW_H), pygame.SRCALPHA)
                overlay.fill((*col, alpha))
                self.screen.blit(overlay, (0, 0))

            # Top letterbox bar
            pygame.draw.rect(self.screen, (8, 10, 15), pygame.Rect(0, 0, SCREEN_W, 54))
            pygame.draw.line(self.screen, (220, 180, 75), (0, 54), (SCREEN_W, 54), 2)
            cs_title = self.active_cutscene.get("name", "Cutscene")
            cs_lbl = self.font_small.render(
                f"🎬 {cs_title}   [Click / Space: Next Step  |  Tab: Skip Cutscene]",
                True,
                (235, 200, 95)
            )
            self.screen.blit(cs_lbl, (20, 18))

        # 4. Speech subtitle box (supports multi-line wrap & speaker tag)
        if self.speech_text:
            lines = wrap_text_lines(self.speech_text, self.font_dialog, SCREEN_W - 180)
            line_surfs = [self.font_dialog.render(line, True, self.speech_color) for line in lines]
            max_w = max(s.get_width() for s in line_surfs)
            spk_surf = None
            if self.speech_speaker:
                spk_surf = self.font_small.render(self.speech_speaker.upper(), True, (255, 255, 255))
                max_w = max(max_w, spk_surf.get_width() + 20)

            box_h = len(line_surfs) * 28 + (24 if spk_surf else 0) + 22
            box_w = max_w + 36
            top_y = 68 if self.active_cutscene else 24
            bg_rect = pygame.Rect((SCREEN_W - box_w) // 2, top_y, box_w, box_h)
            pygame.draw.rect(self.screen, (14, 17, 26), bg_rect, border_radius=10)
            pygame.draw.rect(self.screen, self.speech_color, bg_rect, width=2, border_radius=10)

            cur_y = top_y + 10
            if spk_surf:
                self.screen.blit(spk_surf, spk_surf.get_rect(centerx=SCREEN_W // 2, top=cur_y))
                cur_y += 22
            for s in line_surfs:
                self.screen.blit(s, s.get_rect(centerx=SCREEN_W // 2, top=cur_y))
                cur_y += 28

        # 5. Bottom UI Bar (Cutscene bar OR Dialog Tree Choices OR Standard Verb/Inventory Bar)
        pygame.draw.rect(self.screen, (18, 20, 28), pygame.Rect(0, VIEW_H, SCREEN_W, UI_H))
        pygame.draw.line(self.screen, (70, 80, 110), (0, VIEW_H), (SCREEN_W, VIEW_H), 2)

        if self.active_cutscene:
            steps = self.active_cutscene.get("steps", [])
            step_info = f"Step {min(len(steps), self.cutscene_step_idx + 1)} of {len(steps)}"
            info_surf = self.font_main.render(step_info, True, (180, 195, 225))
            self.screen.blit(info_surf, info_surf.get_rect(center=(SCREEN_W // 2, VIEW_H + UI_H // 2)))

        elif self.active_dialog:
            dlg_title = self.active_dialog.get("name") or f"Conversation with {self.active_dialog.get('npc_name', 'NPC')}"
            hdr = self.font_small.render(
                f"💬 {dlg_title}   (Click a response or press 1-4)",
                True,
                (140, 205, 255)
            )
            self.screen.blit(hdr, (24, VIEW_H + 8))

            if self.dialog_phase == "choose_option":
                avail = self.get_available_dialog_options()
                mx, my = pygame.mouse.get_pos()
                visible = avail[self.dialog_scroll:self.dialog_scroll + 4]
                for disp_i, (orig_idx, opt) in enumerate(visible):
                    ry = VIEW_H + 34 + disp_i * 25
                    rect = pygame.Rect(24, ry, SCREEN_W - 120, 24)
                    hovered = rect.collidepoint(mx, my)
                    col = (255, 225, 95) if hovered else (210, 225, 250)
                    prefix = "▸ " if hovered else "   "
                    line_txt = f"{prefix}{disp_i + 1}. {opt.get('text', '...')}"
                    surf = self.font_choice.render(line_txt, True, col)
                    self.screen.blit(surf, (24, ry + 2))
            else:
                hint = self.font_small.render("[Click or press Space to continue...]", True, (160, 175, 200))
                self.screen.blit(hint, (24, VIEW_H + 60))

        else:
            # Standard Verb & Inventory Bar
            mx, my = pygame.mouse.get_pos()
            hovered_hs = self.get_hovered_hotspot(mx, my)
            hover_name = ""
            if hovered_hs:
                hover_name = hovered_hs.get("name", "")
            elif self.is_hovering_partner(mx, my):
                hover_name = self.partner_name

            if self.selected_item:
                sentence = f"Use {self.selected_item['name']} with {hover_name}"
            else:
                sentence = f"{self.current_verb} {hover_name}"
            status_surf = self.font_main.render(sentence, True, (130, 210, 255))
            self.screen.blit(status_surf, (22, VIEW_H + 10))

            room_lbl = self.font_small.render(
                f"Room: {self.current_room.get('name', '')}  (ESC to close)",
                True,
                (140, 150, 175)
            )
            self.screen.blit(room_lbl, (SCREEN_W - room_lbl.get_width() - 20, VIEW_H + 12))

            # Verb Buttons
            for idx, v in enumerate(VERBS):
                col = idx % 3
                row = idx // 3
                bx = 20 + col * 145
                by = VIEW_H + 42 + row * 44
                rect = pygame.Rect(bx, by, 135, 38)
                active = (self.current_verb == v and self.selected_item is None)
                color = (55, 95, 155) if active else (34, 40, 56)
                border = (120, 185, 255) if active else (65, 75, 100)
                pygame.draw.rect(self.screen, color, rect, border_radius=6)
                pygame.draw.rect(self.screen, border, rect, width=2, border_radius=6)
                v_surf = self.font_small.render(v, True, (240, 245, 255))
                self.screen.blit(v_surf, v_surf.get_rect(center=rect.center))

            # Inventory Tray
            inv_label = self.font_small.render("INVENTORY", True, (160, 170, 195))
            self.screen.blit(inv_label, (520, VIEW_H + 16))
            for slot in range(8):
                ix = 520 + slot * 72
                iy = VIEW_H + 42
                rect = pygame.Rect(ix, iy, 64, 64)
                is_sel = (
                    slot < len(self.inventory)
                    and self.selected_item
                    and self.selected_item["id"] == self.inventory[slot]["id"]
                )
                pygame.draw.rect(self.screen, (28, 32, 44), rect, border_radius=6)
                pygame.draw.rect(self.screen, (250, 210, 80) if is_sel else (60, 70, 95), rect, width=2, border_radius=6)
                if slot < len(self.inventory):
                    it = self.inventory[slot]
                    icon = self.item_icons.get(it["id"])
                    if icon:
                        self.screen.blit(icon, (ix + 6, iy + 6))
                    else:
                        lbl = self.font_small.render(it["name"][:6], True, (255, 220, 120))
                        self.screen.blit(lbl, lbl.get_rect(center=rect.center))

        pygame.display.flip()

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(60) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_TAB and self.active_cutscene:
                        self.finish_cutscene()
                    elif event.key == pygame.K_SPACE:
                        self.handle_click(SCREEN_W // 2, VIEW_H // 2, right_click=False)
                    elif self.active_dialog and self.dialog_phase == "choose_option":
                        if pygame.K_1 <= event.key <= pygame.K_9:
                            choice_num = event.key - pygame.K_1
                            avail = self.get_available_dialog_options()
                            if 0 <= choice_num < len(avail):
                                orig_idx, opt = avail[choice_num]
                                self.select_dialog_option(orig_idx, opt)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self.handle_click(*event.pos, right_click=False)
                    elif event.button == 3:
                        self.handle_click(*event.pos, right_click=True)
            self.update(dt)
            self.draw()
        pygame.quit()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("positional_room", nargs="?", default=None)
    parser.add_argument("--room", default=None)
    parser.add_argument("--cutscene", default=None)
    parser.add_argument("--dialog", default=None)
    args = parser.parse_args()

    room_override = args.room or args.positional_room
    game = AdventureRuntime(
        start_room_override=room_override,
        start_cutscene_override=args.cutscene,
        start_dialog_override=args.dialog
    )
    game.run()

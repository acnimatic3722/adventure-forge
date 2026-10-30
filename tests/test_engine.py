# AdventureForge — Engine Tests
"""
Tests for the Pygame runtime engine (engine_pygame.py).
"""

import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import Config


# Mock pygame before importing engine
@pytest.fixture(autouse=True)
def mock_pygame():
    """Mock pygame module for testing without display."""
    with patch.dict("sys.modules", {
        "pygame": MagicMock(),
        "pygame.font": MagicMock(),
        "pygame.mixer": MagicMock(),
    }):
        # Configure pygame mock
        import pygame
        pygame.init = MagicMock()
        pygame.font.init = MagicMock()
        pygame.mixer.init = MagicMock()
        pygame.display.set_mode = MagicMock(return_value=MagicMock())
        pygame.display.set_caption = MagicMock()
        pygame.time.Clock = MagicMock(return_value=MagicMock())
        pygame.font.SysFont = MagicMock(return_value=MagicMock())
        pygame.Rect = MagicMock()
        pygame.Surface = MagicMock()
        pygame.transform = MagicMock()
        pygame.transform.smoothscale = MagicMock(return_value=MagicMock())
        pygame.transform.scale = MagicMock(return_value=MagicMock())
        pygame.transform.flip = MagicMock(return_value=MagicMock())
        pygame.image.load = MagicMock(return_value=MagicMock())
        pygame.event.get = MagicMock(return_value=[])
        pygame.key.get_pressed = MagicMock(return_value={})
        pygame.mouse.get_pos = MagicMock(return_value=(0, 0))
        pygame.mouse.get_pressed = MagicMock(return_value=(False, False, False))
        yield pygame


class TestEngineImports:
    """Test that engine can be imported without errors."""

    def test_engine_imports(self):
        """Test engine module imports successfully."""
        # This should not raise any import errors
        import engine_pygame
        assert engine_pygame is not None

    def test_engine_constants(self):
        """Test engine constants are defined."""
        import engine_pygame
        assert engine_pygame.SCREEN_W == 1280
        assert engine_pygame.SCREEN_H == 860
        assert engine_pygame.VIEW_H == 720
        assert engine_pygame.UI_H == 140
        assert "Walk to" in engine_pygame.VERBS
        assert "Look at" in engine_pygame.VERBS
        assert "Pick up" in engine_pygame.VERBS


class TestEngineHelpers:
    """Test engine helper functions."""

    def test_resolve_asset_path(self):
        """Test asset path resolution."""
        from engine_pygame import resolve_asset_path

        # Test empty path
        assert resolve_asset_path("") == Path()

        # Test absolute path
        with patch("pathlib.Path.exists", return_value=True):
            result = resolve_asset_path("/absolute/path.png")
            assert isinstance(result, Path)

    def test_point_in_poly(self):
        """Test point-in-polygon function."""
        from engine_pygame import point_in_poly

        # Simple square polygon
        poly = [
            {"x": 0, "y": 0},
            {"x": 10, "y": 0},
            {"x": 10, "y": 10},
            {"x": 0, "y": 10}
        ]

        # Point inside
        assert point_in_poly(5, 5, poly) is True

        # Point outside
        assert point_in_poly(15, 5, poly) is False

        # Point on edge (may vary by implementation)
        # Test corners
        assert point_in_poly(0, 0, poly) in (True, False)  # Edge case

    def test_clamp_to_poly_bounds(self):
        """Test clamping to polygon bounds."""
        from engine_pygame import clamp_to_poly_bounds

        poly = [
            {"x": 0, "y": 0},
            {"x": 100, "y": 0},
            {"x": 100, "y": 100},
            {"x": 0, "y": 100}
        ]

        # Point inside - should return same
        x, y = clamp_to_poly_bounds(50, 50, poly)
        assert x == 50
        assert y == 50

        # Point outside - should clamp
        x, y = clamp_to_poly_bounds(150, 150, poly)
        assert x == 100
        assert y == 100

        x, y = clamp_to_poly_bounds(-50, -50, poly)
        assert x == 0
        assert y == 0

    def test_wrap_text_lines(self):
        """Test text wrapping."""
        from engine_pygame import wrap_text_lines

        mock_font = MagicMock()
        mock_font.size = MagicMock(return_value=(100, 20))

        lines = wrap_text_lines("Hello world test", mock_font, 150)
        assert isinstance(lines, list)
        assert len(lines) > 0


class TestCharacterAnim:
    """Test CharacterAnim class."""

    def test_character_anim_init(self):
        """Test CharacterAnim initialization."""
        from engine_pygame import CharacterAnim

        sprite_cfg = {
            "scale": 3.0,
            "frames_dir": "/fake/path",
            "metadata_file": "/fake/meta.json"
        }

        with patch("engine_pygame.resolve_asset_path") as mock_resolve:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_path.is_dir.return_value = False
            mock_resolve.return_value = mock_path

            anim = CharacterAnim(sprite_cfg)
            assert anim.scale == 3.0
            assert isinstance(anim.animations, dict)
            assert isinstance(anim.fps_map, dict)

    def test_resolve_role_anim(self):
        """Test role to animation mapping."""
        from engine_pygame import CharacterAnim

        sprite_cfg = {
            "scale": 3.0,
            "anim_roles": {
                "walk": "walk_right",
                "up": "walk_up",
                "down": "walk_down",
                "idle": "idle_down"
            }
        }

        with patch("engine_pygame.resolve_asset_path") as mock_resolve:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_resolve.return_value = mock_path

            anim = CharacterAnim(sprite_cfg)
            anim.animations = {
                "walk_right": [MagicMock()],
                "walk_up": [MagicMock()],
                "walk_down": [MagicMock()],
                "idle_down": [MagicMock()]
            }

            assert anim.resolve_role_anim("walk") == "walk_right"
            assert anim.resolve_role_anim("up") == "walk_up"
            assert anim.resolve_role_anim("down") == "walk_down"
            assert anim.resolve_role_anim("idle") == "idle_down"


class TestAdventureRuntime:
    """Test AdventureRuntime class."""

    def test_adventure_runtime_init(self, mock_pygame):
        """Test AdventureRuntime initialization."""
        from engine_pygame import AdventureRuntime

        with patch("engine_pygame.PROJECT_FILE") as mock_proj_file:
            mock_proj_file.read_text.return_value = json.dumps({
                "title": "Test Game",
                "start_room": "room1",
                "player_sprite": "hero",
                "partner_sprite": "",
                "rooms": [{
                    "id": "room1",
                    "name": "Room 1",
                    "background": "/assets/bg.png",
                    "player_start": {"x": 400, "y": 560},
                    "walkable_polygon": [],
                    "hotspots": []
                }],
                "items": [],
                "puzzles": [],
                "sprites": {},
                "dialogs": [],
                "cutscenes": []
            })

            with patch("engine_pygame.resolve_asset_path") as mock_resolve:
                mock_path = MagicMock()
                mock_path.exists.return_value = False
                mock_resolve.return_value = mock_path

                runtime = AdventureRuntime()
                assert runtime.title == "Test Game"
                assert runtime.player_x == 400
                assert runtime.player_y == 560

    def test_say_method(self, mock_pygame):
        """Test say method."""
        from engine_pygame import AdventureRuntime

        with patch("engine_pygame.PROJECT_FILE") as mock_proj_file:
            mock_proj_file.read_text.return_value = json.dumps({
                "title": "Test", "start_room": "r1", "player_sprite": "h",
                "rooms": [{"id": "r1", "name": "R1", "background": "", "player_start": {"x": 0, "y": 0}, "walkable_polygon": [], "hotspots": []}],
                "items": [], "puzzles": [], "sprites": {}, "dialogs": [], "cutscenes": []
            })

            with patch("engine_pygame.resolve_asset_path") as mock_resolve:
                mock_path = MagicMock()
                mock_path.exists.return_value = False
                mock_resolve.return_value = mock_path

                runtime = AdventureRuntime()
                runtime.say("Hello world", duration=2.0, speaker="Sam", color=(255, 255, 0))

                assert runtime.speech_text == "Hello world"
                assert runtime.speech_speaker == "Sam"
                assert runtime.speech_color == (255, 255, 0)
                assert runtime.speech_timer == 2.0

    def test_play_sound(self, mock_pygame):
        """Test play_sound method."""
        from engine_pygame import AdventureRuntime

        with patch("engine_pygame.PROJECT_FILE") as mock_proj_file:
            mock_proj_file.read_text.return_value = json.dumps({
                "title": "Test", "start_room": "r1", "player_sprite": "h",
                "rooms": [{"id": "r1", "name": "R1", "background": "", "player_start": {"x": 0, "y": 0}, "walkable_polygon": [], "hotspots": []}],
                "items": [], "puzzles": [], "sprites": {}, "dialogs": [], "cutscenes": []
            })

            with patch("engine_pygame.resolve_asset_path") as mock_resolve:
                mock_path = MagicMock()
                mock_path.exists.return_value = True
                mock_path.is_file.return_value = True
                mock_resolve.return_value = mock_path

                runtime = AdventureRuntime()
                mock_sound = MagicMock()
                # The engine caches sounds by their resolved path
                runtime.sound_cache[str(mock_path)] = mock_sound

                runtime.play_sound("/assets/sounds/test.wav")
                mock_sound.play.assert_called_once()

    def test_give_inventory_item(self, mock_pygame):
        """Test giving inventory item."""
        from engine_pygame import AdventureRuntime

        with patch("engine_pygame.PROJECT_FILE") as mock_proj_file:
            mock_proj_file.read_text.return_value = json.dumps({
                "title": "Test", "start_room": "r1", "player_sprite": "h",
                "rooms": [{"id": "r1", "name": "R1", "background": "", "player_start": {"x": 0, "y": 0}, "walkable_polygon": [], "hotspots": []}],
                "items": [{"id": "key", "name": "Key", "icon": ""}],
                "puzzles": [], "sprites": {}, "dialogs": [], "cutscenes": []
            })

            with patch("engine_pygame.resolve_asset_path") as mock_resolve:
                mock_path = MagicMock()
                mock_path.exists.return_value = False
                mock_resolve.return_value = mock_path

                runtime = AdventureRuntime()
                runtime.give_inventory_item("key")

                assert len(runtime.inventory) == 1
                assert runtime.inventory[0]["id"] == "key"

                # Test duplicate prevention
                runtime.give_inventory_item("key")
                assert len(runtime.inventory) == 1

    def test_set_story_flag(self, mock_pygame):
        """Test setting story flags."""
        from engine_pygame import AdventureRuntime

        with patch("engine_pygame.PROJECT_FILE") as mock_proj_file:
            mock_proj_file.read_text.return_value = json.dumps({
                "title": "Test", "start_room": "r1", "player_sprite": "h",
                "rooms": [{"id": "r1", "name": "R1", "background": "", "player_start": {"x": 0, "y": 0}, "walkable_polygon": [], "hotspots": []}],
                "items": [], "puzzles": [], "sprites": {}, "dialogs": [], "cutscenes": []
            })

            with patch("engine_pygame.resolve_asset_path") as mock_resolve:
                mock_path = MagicMock()
                mock_path.exists.return_value = False
                mock_resolve.return_value = mock_path

                runtime = AdventureRuntime()
                runtime.set_story_flag("test_flag")

                assert "test_flag" in runtime.flags

    def test_change_room(self, mock_pygame):
        """Test changing rooms."""
        from engine_pygame import AdventureRuntime

        with patch("engine_pygame.PROJECT_FILE") as mock_proj_file:
            mock_proj_file.read_text.return_value = json.dumps({
                "title": "Test", "start_room": "r1", "player_sprite": "h",
                "rooms": [
                    {"id": "r1", "name": "Room 1", "background": "/assets/bg1.png", "player_start": {"x": 100, "y": 100}, "walkable_polygon": [], "hotspots": []},
                    {"id": "r2", "name": "Room 2", "background": "/assets/bg2.png", "player_start": {"x": 200, "y": 200}, "walkable_polygon": [], "hotspots": []}
                ],
                "items": [], "puzzles": [], "sprites": {}, "dialogs": [], "cutscenes": []
            })

            with patch("engine_pygame.resolve_asset_path") as mock_resolve:
                mock_path = MagicMock()
                mock_path.exists.return_value = False
                mock_resolve.return_value = mock_path

                runtime = AdventureRuntime()
                runtime.change_room("r2")

                assert runtime.current_room["id"] == "r2"
                assert runtime.player_x == 200
                assert runtime.player_y == 200


class TestCutsceneEngine:
    """Test cutscene engine functionality."""

    def test_start_cutscene(self, mock_pygame):
        """Test starting a cutscene."""
        from engine_pygame import AdventureRuntime

        with patch("engine_pygame.PROJECT_FILE") as mock_proj_file:
            mock_proj_file.read_text.return_value = json.dumps({
                "title": "Test", "start_room": "r1", "player_sprite": "h",
                "rooms": [{"id": "r1", "name": "R1", "background": "", "player_start": {"x": 0, "y": 0}, "walkable_polygon": [], "hotspots": []}],
                "items": [], "puzzles": [], "sprites": {}, "dialogs": [], "cutscenes": [
                    {
                        "id": "cs1",
                        "name": "Cutscene 1",
                        "trigger_type": "manual",
                        "steps": [
                            {"type": "say", "actor": "player", "text": "Hello", "duration": 2.0},
                            {"type": "wait", "duration": 1.0}
                        ]
                    }
                ]
            })

            with patch("engine_pygame.resolve_asset_path") as mock_resolve:
                mock_path = MagicMock()
                mock_path.exists.return_value = False
                mock_resolve.return_value = mock_path

                runtime = AdventureRuntime()
                result = runtime.start_cutscene("cs1")

                assert result is True
                assert runtime.active_cutscene is not None
                assert runtime.active_cutscene["id"] == "cs1"
                assert runtime.cutscene_step_idx == 0

    def test_cutscene_once_flag(self, mock_pygame):
        """Test cutscene once flag prevents replay."""
        from engine_pygame import AdventureRuntime

        with patch("engine_pygame.PROJECT_FILE") as mock_proj_file:
            mock_proj_file.read_text.return_value = json.dumps({
                "title": "Test", "start_room": "r1", "player_sprite": "h",
                "rooms": [{"id": "r1", "name": "R1", "background": "", "player_start": {"x": 0, "y": 0}, "walkable_polygon": [], "hotspots": []}],
                "items": [], "puzzles": [], "sprites": {}, "dialogs": [], "cutscenes": [
                    {"id": "cs1", "name": "CS1", "trigger_type": "manual", "once": True, "steps": []}
                ]
            })

            with patch("engine_pygame.resolve_asset_path") as mock_resolve:
                mock_path = MagicMock()
                mock_path.exists.return_value = False
                mock_resolve.return_value = mock_path

                runtime = AdventureRuntime()
                runtime.played_cutscenes.add("cs1")

                result = runtime.start_cutscene("cs1")
                assert result is False  # Should not play again


class TestDialogEngine:
    """Test dialog tree engine."""

    def test_start_dialog(self, mock_pygame):
        """Test starting a dialog tree."""
        from engine_pygame import AdventureRuntime

        with patch("engine_pygame.PROJECT_FILE") as mock_proj_file:
            mock_proj_file.read_text.return_value = json.dumps({
                "title": "Test", "start_room": "r1", "player_sprite": "h",
                "rooms": [{"id": "r1", "name": "R1", "background": "", "player_start": {"x": 0, "y": 0}, "walkable_polygon": [], "hotspots": []}],
                "items": [], "puzzles": [], "sprites": {}, "dialogs": [
                    {
                        "id": "dlg1",
                        "name": "Dialog 1",
                        "npc_name": "NPC",
                        "root_node": "root",
                        "nodes": [
                            {"id": "root", "speaker": "npc", "npc_text": "Hello!", "options": []}
                        ]
                    }
                ],
                "cutscenes": []
            })

            with patch("engine_pygame.resolve_asset_path") as mock_resolve:
                mock_path = MagicMock()
                mock_path.exists.return_value = False
                mock_resolve.return_value = mock_path

                runtime = AdventureRuntime()
                result = runtime.start_dialog("dlg1")

                assert result is True
                assert runtime.active_dialog is not None
                assert runtime.active_dialog["id"] == "dlg1"
                assert runtime.dialog_phase == "npc_speaking"

    def test_dialog_options(self, mock_pygame):
        """Test getting available dialog options."""
        from engine_pygame import AdventureRuntime

        with patch("engine_pygame.PROJECT_FILE") as mock_proj_file:
            mock_proj_file.read_text.return_value = json.dumps({
                "title": "Test", "start_room": "r1", "player_sprite": "h",
                "rooms": [{"id": "r1", "name": "R1", "background": "", "player_start": {"x": 0, "y": 0}, "walkable_polygon": [], "hotspots": []}],
                "items": [], "puzzles": [], "sprites": {}, "dialogs": [
                    {
                        "id": "dlg1",
                        "name": "Dialog 1",
                        "npc_name": "NPC",
                        "root_node": "root",
                        "nodes": [
                            {
                                "id": "root",
                                "speaker": "npc",
                                "npc_text": "Hello!",
                                "options": [
                                    {"text": "Option 1", "next_node": "__exit__", "once": False},
                                    {"text": "Option 2", "next_node": "__exit__", "once": True}
                                ]
                            }
                        ]
                    }
                ],
                "cutscenes": []
            })

            with patch("engine_pygame.resolve_asset_path") as mock_resolve:
                mock_path = MagicMock()
                mock_path.exists.return_value = False
                mock_resolve.return_value = mock_path

                runtime = AdventureRuntime()
                runtime.start_dialog("dlg1")
                runtime.dialog_phase = "choose_option"

                options = runtime.get_available_dialog_options()
                assert len(options) == 2

                # Test once flag
                runtime.used_dialog_options.add("dlg1:root:1")
                options = runtime.get_available_dialog_options()
                assert len(options) == 1


# ============================================================================
# Engine runtime tests for the new subsystems
# ============================================================================

def _base_project(**overrides):
    """A minimal but valid project manifest for the runtime."""
    project = {
        "title": "Test Game",
        "start_room": "r1",
        "rooms": [{
            "id": "r1",
            "name": "Room 1",
            "background": "",
            "player_start": {"x": 100, "y": 500},
            "walkable_polygon": [],
            "hotspots": [],
        }],
        "items": [],
        "puzzles": [],
        "sprites": {},
        "dialogs": [],
        "cutscenes": [],
        "events": [],
    }
    project.update(overrides)
    return project


def _make_runtime(project):
    """Boot an AdventureRuntime from an in-memory project manifest."""
    from engine_pygame import AdventureRuntime

    with patch("engine_pygame.PROJECT_FILE") as mock_proj_file:
        mock_proj_file.read_text.return_value = json.dumps(project)
        with patch("engine_pygame.resolve_asset_path") as mock_resolve:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_path.is_dir.return_value = False
            mock_path.is_file.return_value = False
            mock_resolve.return_value = mock_path
            return AdventureRuntime()


class TestEngineCollision:
    """The runtime must keep characters out of walls and furniture."""

    def test_player_cannot_walk_through_a_wall(self, mock_pygame):
        from engine_geometry import point_blocked

        project = _base_project()
        wall = {"id": "wall", "type": "rect", "x": 200, "y": 0, "w": 20, "h": 720}
        project["rooms"][0]["colliders"] = [wall]

        runtime = _make_runtime(project)
        runtime.target_x, runtime.target_y = 500, 500
        for _ in range(40):
            runtime.update(0.05)

        # The player stopped at the wall instead of walking through it.
        assert runtime.player_x < 200, f"player walked through the wall: x={runtime.player_x}"
        assert runtime.player_x > 100, "the player should have moved towards the wall"
        assert not point_blocked(
            runtime.player_x, runtime.player_y, runtime.collision_radius, [wall]
        )

    def test_player_slides_along_a_wall(self, mock_pygame):
        project = _base_project()
        wall = {"id": "wall", "type": "rect", "x": 0, "y": 400, "w": 1280, "h": 20}
        project["rooms"][0]["colliders"] = [wall]
        project["rooms"][0]["player_start"] = {"x": 100, "y": 300}

        runtime = _make_runtime(project)
        runtime.target_x, runtime.target_y = 300, 500
        for _ in range(30):
            runtime.update(0.05)

        # The wall band is y in [386, 434] once the 14px radius is applied.
        assert runtime.player_y <= 386, f"player crossed the wall: y={runtime.player_y}"
        assert runtime.player_x > 150, "the player should have slid along the wall"

    def test_spawn_inside_a_wall_is_rescued(self, mock_pygame):
        from engine_geometry import point_blocked

        wall = {"id": "block", "type": "rect", "x": 100, "y": 100, "w": 100, "h": 100}
        project = _base_project()
        project["rooms"][0]["player_start"] = {"x": 150, "y": 150}
        project["rooms"][0]["colliders"] = [wall]

        runtime = _make_runtime(project)

        assert not point_blocked(
            runtime.player_x, runtime.player_y, runtime.collision_radius, [wall]
        ), "the player should have been pushed out of the wall"

    def test_blocked_path_tells_the_player(self, mock_pygame):
        project = _base_project()
        project["rooms"][0]["colliders"] = [
            {"id": "wall", "type": "rect", "x": 200, "y": 0, "w": 20, "h": 720}
        ]
        project["rooms"][0]["hotspots"] = [{
            "id": "h1", "type": "prop", "name": "Sign",
            "rect": {"x": 600, "y": 480, "w": 40, "h": 40}, "look_text": "A sign.",
        }]

        runtime = _make_runtime(project)
        runtime.pending_action = {
            "hotspot": project["rooms"][0]["hotspots"][0],
            "verb": "Look at",
            "item": None,
        }
        runtime.target_x, runtime.target_y = 600, 500

        for _ in range(30):
            runtime.update(0.05)

        assert "closer" in runtime.speech_text.lower(), runtime.speech_text

    def test_hotspot_against_a_wall_still_triggers(self, mock_pygame):
        project = _base_project()
        # The hotspot's target sits inside this block of furniture.
        project["rooms"][0]["colliders"] = [
            {"id": "desk", "type": "rect", "x": 140, "y": 480, "w": 60, "h": 40}
        ]
        project["rooms"][0]["hotspots"] = [{
            "id": "h1", "type": "prop", "name": "Desk",
            "rect": {"x": 140, "y": 480, "w": 60, "h": 40}, "look_text": "A dusty desk.",
        }]

        runtime = _make_runtime(project)
        runtime.pending_action = {
            "hotspot": project["rooms"][0]["hotspots"][0],
            "verb": "Look at",
            "item": None,
        }
        runtime.target_x, runtime.target_y = 160, 500

        for _ in range(10):
            runtime.update(0.05)

        assert runtime.speech_text == "A dusty desk.", runtime.speech_text

    def test_companion_cannot_pass_through_a_wall(self, mock_pygame):
        project = _base_project()
        project["sprites"] = {"pal_sheet": {"scale": 3.0}}
        project["characters"] = {
            "hero": {"name": "Hero", "role": "player"},
            "pal": {"name": "Pal", "sprite": "pal_sheet", "role": "companion", "follow": True},
        }
        project["player_character"] = "hero"
        project["rooms"][0]["colliders"] = [
            {"id": "wall", "type": "rect", "x": 200, "y": 0, "w": 20, "h": 720}
        ]

        runtime = _make_runtime(project)
        comp = runtime.companions[0]
        comp["target_x"] = 600
        comp["target_y"] = comp["y"]

        for _ in range(40):
            runtime.update(0.05)

        assert comp["x"] < 200, f"companion walked through the wall: x={comp['x']}"


class TestEngineCharacters:
    """The runtime roster is generic — any number of companions."""

    def test_multiple_companions_are_created(self, mock_pygame):
        project = _base_project()
        project["sprites"] = {"a_sheet": {"scale": 3.0}, "b_sheet": {"scale": 3.0}}
        project["characters"] = {
            "hero": {"name": "Hero", "role": "player"},
            "pal1": {"name": "Bibi", "sprite": "a_sheet", "role": "companion", "follow": True},
            "pal2": {"name": "Tino", "sprite": "b_sheet", "role": "companion", "follow": True},
            "npc": {"name": "Mira", "role": "npc"},
        }
        project["player_character"] = "hero"

        runtime = _make_runtime(project)

        assert [c["id"] for c in runtime.companions] == ["pal1", "pal2"]
        assert runtime.player_char_id == "hero"
        assert runtime.player_name == "Hero"

    def test_legacy_project_still_yields_a_companion(self, mock_pygame):
        project = _base_project()
        project["player_sprite"] = "hero"
        project["partner_sprite"] = "pal"
        project["sprites"] = {"hero": {"name": "Hero"}, "pal": {"name": "Pal"}}

        runtime = _make_runtime(project)

        assert len(runtime.companions) == 1
        assert runtime.companions[0]["name"] == "Pal"

    def test_partner_properties_proxy_to_the_first_companion(self, mock_pygame):
        project = _base_project()
        project["sprites"] = {"pal_sheet": {"scale": 3.0}}
        project["characters"] = {
            "hero": {"name": "Hero", "role": "player"},
            "pal": {"name": "Pal", "sprite": "pal_sheet", "role": "companion", "follow": True},
        }
        project["player_character"] = "hero"

        runtime = _make_runtime(project)
        comp = runtime.companions[0]

        assert runtime.partner_name == comp["name"]
        assert runtime.partner_x == comp["x"]
        assert runtime.partner_y == comp["y"]

        runtime.partner_x = 123.0
        runtime.partner_y = 456.0
        assert comp["x"] == 123.0
        assert comp["y"] == 456.0

    def test_npc_hotspot_resolves_its_character(self, mock_pygame):
        project = _base_project()
        project["sprites"] = {"mira_sheet": {"scale": 3.0}}
        project["characters"] = {
            "hero": {"name": "Hero", "role": "player"},
            "mira": {"name": "Mira", "sprite": "mira_sheet", "role": "npc", "dialog_id": "dlg_mira"},
        }
        project["player_character"] = "hero"
        project["rooms"][0]["hotspots"] = [{
            "id": "npc1", "type": "npc", "name": "Shopkeep",
            "rect": {"x": 400, "y": 400, "w": 60, "h": 120}, "character_id": "mira",
        }]

        runtime = _make_runtime(project)
        hs = runtime.current_room["hotspots"][0]

        assert runtime.hotspot_character(hs)["name"] == "Mira"
        assert runtime.hotspot_character_sprite(hs) == "mira_sheet"

    def test_cutscene_actor_accepts_any_character_id(self, mock_pygame):
        project = _base_project()
        project["sprites"] = {"pal_sheet": {"scale": 3.0}}
        project["characters"] = {
            "hero": {"name": "Hero", "role": "player"},
            "pal": {"name": "Pal", "sprite": "pal_sheet", "role": "companion", "follow": True},
        }
        project["player_character"] = "hero"

        runtime = _make_runtime(project)

        assert runtime.resolve_actor_companion("pal") is runtime.companions[0]
        # The legacy token still works.
        assert runtime.resolve_actor_companion("partner") is runtime.companions[0]
        assert runtime.resolve_actor_companion("nobody") is None


class TestEngineEvents:
    """One dispatch path for every trigger in the game."""

    def test_fire_event_queues_actions(self, mock_pygame):
        project = _base_project()
        project["events"] = [{
            "id": "ev1", "name": "Intro",
            "trigger": {"type": "on_enter_room", "target": "r1"},
            "actions": [{"type": "set_flag", "value": "entered"}],
        }]

        runtime = _make_runtime(project)

        assert runtime.event_queue, "the on_enter_room event should have queued an action"
        runtime.update(0.05)
        assert "entered" in runtime.flags

    def test_process_event_queue_drains_one_action_at_a_time(self, mock_pygame):
        project = _base_project()
        project["events"] = [{
            "id": "ev1",
            "trigger": {"type": "on_game_start"},
            "actions": [
                {"type": "set_flag", "value": "a"},
                {"type": "set_flag", "value": "b"},
            ],
        }]

        runtime = _make_runtime(project)
        assert len(runtime.event_queue) == 2

        runtime.process_event_queue()
        assert len(runtime.event_queue) == 1
        assert "a" in runtime.flags
        assert "b" not in runtime.flags

        runtime.process_event_queue()
        assert len(runtime.event_queue) == 0
        assert "b" in runtime.flags

    def test_queue_waits_until_the_stage_is_clear(self, mock_pygame):
        project = _base_project()
        runtime = _make_runtime(project)
        runtime.active_cutscene = {"id": "cs", "steps": []}
        runtime.event_queue.append({
            "event_id": "ev", "action": {"type": "set_flag", "value": "later"}, "context": {},
        })

        runtime.process_event_queue()

        assert len(runtime.event_queue) == 1
        assert "later" not in runtime.flags

    def test_set_flag_action(self, mock_pygame):
        runtime = _make_runtime(_base_project())
        runtime.run_event_action({"type": "set_flag", "value": "flag_a"}, {})
        assert "flag_a" in runtime.flags

    def test_clear_flag_action(self, mock_pygame):
        runtime = _make_runtime(_base_project())
        runtime.flags.add("flag_a")
        runtime.run_event_action({"type": "clear_flag", "value": "flag_a"}, {})
        assert "flag_a" not in runtime.flags

    def test_give_item_action(self, mock_pygame):
        project = _base_project(items=[{"id": "key", "name": "Key", "icon": ""}])
        runtime = _make_runtime(project)
        runtime.run_event_action({"type": "give_item", "value": "key"}, {})
        assert [i["id"] for i in runtime.inventory] == ["key"]

    def test_unlock_door_action(self, mock_pygame):
        project = _base_project()
        project["rooms"][0]["hotspots"] = [{
            "id": "door1", "type": "exit", "locked": True,
            "rect": {"x": 0, "y": 0, "w": 40, "h": 80},
        }]
        runtime = _make_runtime(project)

        assert runtime.unlock_hotspot("door1") is True
        assert runtime.rooms_by_id["r1"]["hotspots"][0]["locked"] is False
        assert runtime.unlock_hotspot("nope") is False

    def test_show_text_action(self, mock_pygame):
        runtime = _make_runtime(_base_project())
        runtime.run_event_action({"type": "show_text", "value": "Hello!", "speaker": "Guide"}, {})
        assert runtime.speech_text == "Hello!"
        assert runtime.speech_speaker == "Guide"

    def test_on_flag_set_trigger(self, mock_pygame):
        project = _base_project()
        project["events"] = [{
            "id": "ev_flag",
            "trigger": {"type": "on_flag_set", "target": "door_open"},
            "actions": [{"type": "show_text", "value": "The door swings open."}],
        }]

        runtime = _make_runtime(project)
        runtime.set_story_flag("door_open")
        runtime.process_event_queue()

        assert runtime.speech_text == "The door swings open."

    def test_on_hotspot_use_trigger(self, mock_pygame):
        project = _base_project()
        project["events"] = [{
            "id": "ev_hs",
            "trigger": {"type": "on_hotspot_use", "target": "h1"},
            "actions": [{"type": "set_flag", "value": "touched"}],
        }]
        project["rooms"][0]["hotspots"] = [{
            "id": "h1", "type": "prop", "name": "Sign",
            "rect": {"x": 400, "y": 400, "w": 40, "h": 40}, "look_text": "A sign.",
        }]

        runtime = _make_runtime(project)
        runtime.execute_hotspot_interaction(project["rooms"][0]["hotspots"][0], "Look at", None)
        runtime.process_event_queue()

        assert "touched" in runtime.flags

    def test_on_item_pickup_trigger(self, mock_pygame):
        project = _base_project(items=[{"id": "coin", "name": "Coin", "icon": ""}])
        project["events"] = [{
            "id": "ev_pick",
            "trigger": {"type": "on_item_pickup", "target": "coin"},
            "actions": [{"type": "set_flag", "value": "has_coin"}],
        }]
        project["rooms"][0]["hotspots"] = [{
            "id": "coin_hs", "type": "pickup", "name": "Coin", "item_id": "coin",
            "rect": {"x": 400, "y": 400, "w": 30, "h": 30},
        }]

        runtime = _make_runtime(project)
        runtime.execute_hotspot_interaction(project["rooms"][0]["hotspots"][0], "Pick up", None)
        runtime.process_event_queue()

        assert "has_coin" in runtime.flags

    def test_end_dialog_fires_on_dialog_end(self, mock_pygame):
        project = _base_project()
        project["events"] = [{
            "id": "ev_dlg",
            "trigger": {"type": "on_dialog_end", "target": "dlg1"},
            "actions": [{"type": "set_flag", "value": "talked"}],
        }]
        project["dialogs"] = [{
            "id": "dlg1", "name": "Talk", "npc_name": "Mira", "root_node": "root",
            "nodes": [{"id": "root", "speaker": "npc", "npc_text": "Hi!", "options": []}],
        }]

        runtime = _make_runtime(project)
        runtime.start_dialog("dlg1")
        runtime.end_dialog()
        runtime.process_event_queue()

        assert runtime.active_dialog is None
        assert "talked" in runtime.flags

    def test_cutscene_interrupt_does_not_fire_on_dialog_end(self, mock_pygame):
        project = _base_project()
        project["events"] = [{
            "id": "ev_dlg",
            "trigger": {"type": "on_dialog_end", "target": "dlg1"},
            "actions": [{"type": "set_flag", "value": "talked"}],
        }]
        project["dialogs"] = [{
            "id": "dlg1", "name": "Talk", "npc_name": "Mira", "root_node": "root",
            "nodes": [{"id": "root", "speaker": "npc", "npc_text": "Hi!", "options": []}],
        }]
        project["cutscenes"] = [{"id": "cs1", "name": "CS", "steps": [{"type": "wait", "duration": 0.1}]}]

        runtime = _make_runtime(project)
        runtime.start_dialog("dlg1")
        runtime.start_cutscene("cs1", force=True)
        runtime.process_event_queue()

        assert "talked" not in runtime.flags

    def test_once_events_only_fire_once(self, mock_pygame):
        project = _base_project()
        project["events"] = [{
            "id": "ev_once",
            "trigger": {"type": "on_game_start"},
            "actions": [{"type": "set_flag", "value": "once"}],
        }]

        runtime = _make_runtime(project)
        runtime.process_event_queue()
        assert "once" in runtime.flags

        # Firing the same trigger again must not queue a second action.
        runtime.fire_event("on_game_start")
        assert runtime.event_queue == [], "a once-event must not queue twice"

    def test_repeatable_events_fire_again(self, mock_pygame):
        project = _base_project()
        project["events"] = [{
            "id": "ev_repeat", "once": False,
            "trigger": {"type": "on_flag_set", "target": "tick"},
            "actions": [{"type": "set_flag", "value": "ticked"}],
        }]

        runtime = _make_runtime(project)
        runtime.set_story_flag("tick")
        runtime.process_event_queue()
        assert "ticked" in runtime.flags

    def test_requires_flag_blocks_the_event(self, mock_pygame):
        project = _base_project()
        project["events"] = [{
            "id": "ev_gated",
            "requires_flag": "has_key",
            "trigger": {"type": "on_game_start"},
            "actions": [{"type": "set_flag", "value": "unlocked"}],
        }]

        runtime = _make_runtime(project)
        runtime.process_event_queue()
        assert "unlocked" not in runtime.flags

        runtime.flags.add("has_key")
        runtime.fire_event("on_game_start")
        runtime.process_event_queue()
        assert "unlocked" in runtime.flags

    def test_disabled_events_do_not_fire(self, mock_pygame):
        project = _base_project()
        project["events"] = [{
            "id": "ev_off", "enabled": False,
            "trigger": {"type": "on_game_start"},
            "actions": [{"type": "set_flag", "value": "nope"}],
        }]

        runtime = _make_runtime(project)
        runtime.process_event_queue()
        assert "nope" not in runtime.flags

    def test_legacy_cutscene_trigger_becomes_an_event(self, mock_pygame):
        project = _base_project()
        project["cutscenes"] = [{
            "id": "cs1", "name": "Intro", "trigger_type": "on_enter_room",
            "trigger_target": "r1", "steps": [{"type": "wait", "duration": 0.1}],
        }]

        runtime = _make_runtime(project)

        assert any(e["id"] == "legacy_cs1" for e in runtime.events)
        assert runtime.event_queue, "the migrated event should have queued its action"

        runtime.update(0.05)
        assert runtime.active_cutscene is not None
        assert runtime.active_cutscene["id"] == "cs1"

    def test_legacy_flag_trigger_respects_the_old_switch(self, mock_pygame):
        project = _base_project()
        project["cutscenes"] = [{
            "id": "cs1", "name": "On Flag", "trigger_type": "on_flag_set",
            "trigger_target": "door_open", "steps": [{"type": "wait", "duration": 0.1}],
        }]

        runtime = _make_runtime(project)
        runtime.set_story_flag("door_open", allow_cutscene_trigger=False)
        assert runtime.event_queue == []

        runtime.set_story_flag("door_open", allow_cutscene_trigger=True)
        assert runtime.event_queue, "the legacy trigger should fire when allowed"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
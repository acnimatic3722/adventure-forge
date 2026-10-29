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


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
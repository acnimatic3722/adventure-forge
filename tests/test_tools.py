# AdventureForge — Test Suite
"""
Tests for AdventureForge MCP tools, API endpoints, and core functionality.
Run with: pytest tests/ -v
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import Config
from tools import (
    get_project_summary,
    get_full_project,
    set_project_title,
    list_rooms,
    get_room,
    create_or_update_room,
    delete_room,
    update_room_map_position,
    set_room_walkable_polygon,
    set_start_room,
    list_hotspots,
    get_hotspot,
    create_or_update_hotspot,
    delete_hotspot,
    link_door,
    set_hotspot_lock,
    list_items,
    get_item,
    create_or_update_item,
    delete_item,
    link_item_usage,
    list_puzzles,
    get_puzzle,
    create_or_update_puzzle,
    delete_puzzle,
    list_dialog_trees,
    get_dialog_tree,
    create_or_update_dialog_tree,
    delete_dialog_tree,
    add_or_update_dialog_node,
    add_dialog_player_choice,
    list_cutscenes,
    get_cutscene,
    create_or_update_cutscene,
    add_cutscene_step,
    list_sprites,
    get_sprite,
    list_assets,
    list_room_colliders,
    add_room_collider,
    set_room_colliders,
    clear_room_colliders,
    list_characters,
    get_character,
    create_or_update_character,
    delete_character,
    set_player_character,
    assign_character_to_hotspot,
    list_events,
    get_event,
    create_or_update_event,
    delete_event,
    add_event_action,
    remove_event_action,
    set_event_actions,
    migrate_legacy_triggers,
    TOOLS_LIST,
    TOOLS_BY_NAME,
)
from tools.project import launch_pygame_game, stop_pygame_game
from tools._core import _load_proj, _save_proj, PROJECT_FILE


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    data_dir = temp_dir / "data"
    assets_dir = data_dir / "assets"
    for subdir in ["backgrounds", "items", "sprites", "sounds", "music"]:
        (assets_dir / subdir).mkdir(parents=True)

    project_file = data_dir / "project.json"
    initial_project = {
        "title": "Test Adventure",
        "start_room": "test_room",
        "player_sprite": "hero",
        "partner_sprite": "",
        "rooms": [
            {
                "id": "test_room",
                "name": "Test Room",
                "map_x": 100,
                "map_y": 100,
                "background": "/assets/backgrounds/test.png",
                "player_start": {"x": 400, "y": 560},
                "walkable_polygon": [
                    {"x": 60, "y": 470},
                    {"x": 1220, "y": 470},
                    {"x": 1240, "y": 700},
                    {"x": 40, "y": 700}
                ],
                "hotspots": []
            }
        ],
        "items": [
            {
                "id": "test_item",
                "name": "Test Item",
                "icon": "/assets/items/test.png",
                "description": "A test item"
            }
        ],
        "puzzles": [],
        "sprites": {},
        "dialogs": [],
        "cutscenes": []
    }
    project_file.write_text(json.dumps(initial_project, indent=2))

    # Patch config paths
    original_base = Config.BASE_DIR
    original_data = Config.DATA_DIR
    original_assets = Config.ASSETS_DIR
    original_project = Config.PROJECT_FILE

    Config.BASE_DIR = temp_dir
    Config.DATA_DIR = data_dir
    Config.ASSETS_DIR = assets_dir
    Config.PROJECT_FILE = project_file

    yield temp_dir

    # Restore
    Config.BASE_DIR = original_base
    Config.DATA_DIR = original_data
    Config.ASSETS_DIR = original_assets
    Config.PROJECT_FILE = original_project

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_project(temp_project_dir):
    """Load a sample project."""
    return _load_proj()


# ============================================================================
# Config Tests
# ============================================================================

class TestConfig:
    def test_config_paths(self):
        """Test that config paths are properly structured."""
        assert Config.BASE_DIR.exists()
        assert Config.DATA_DIR == Config.BASE_DIR / "data"
        assert Config.ASSETS_DIR == Config.DATA_DIR / "assets"
        assert Config.PROJECT_FILE == Config.DATA_DIR / "project.json"

    def test_ensure_dirs(self):
        """Test directory creation."""
        with tempfile.TemporaryDirectory() as tmp:
            Config.DATA_DIR = Path(tmp) / "data"
            Config.ASSETS_DIR = Config.DATA_DIR / "assets"
            Config.ensure_dirs()
            assert Config.DATA_DIR.exists()
            assert Config.ASSETS_DIR.exists()
            assert (Config.ASSETS_DIR / "backgrounds").exists()
            assert (Config.ASSETS_DIR / "items").exists()
            assert (Config.ASSETS_DIR / "sprites").exists()
            assert (Config.ASSETS_DIR / "sounds").exists()
            assert (Config.ASSETS_DIR / "music").exists()

    def test_get_model_paths(self):
        """Test model path helpers."""
        sd_path = Config.get_sd15_model_path("q8")
        assert "sd15" in str(sd_path)
        assert sd_path.name.endswith(".gguf")

        iris_path = Config.get_iris_model_path()
        assert "iris-3b" in str(iris_path)


# ============================================================================
# Project Store Tests
# ============================================================================

class TestProjectStore:
    def test_load_proj(self, sample_project):
        """Test loading project."""
        proj = _load_proj()
        assert proj["title"] == "Test Adventure"
        assert proj["start_room"] == "test_room"
        assert len(proj["rooms"]) == 1
        assert len(proj["items"]) == 1

    def test_save_proj(self, sample_project):
        """Test saving project."""
        proj = _load_proj()
        proj["title"] = "Updated Title"
        _save_proj(proj)

        reloaded = _load_proj()
        assert reloaded["title"] == "Updated Title"


# ============================================================================
# Room Tests
# ============================================================================

class TestRooms:
    def test_list_rooms(self, sample_project):
        """Test listing rooms."""
        result = list_rooms()
        assert result["count"] == 1
        assert result["rooms"][0]["id"] == "test_room"
        assert result["rooms"][0]["name"] == "Test Room"

    def test_get_room(self, sample_project):
        """Test getting a specific room."""
        result = get_room("test_room")
        assert "room" in result
        assert result["room"]["id"] == "test_room"

    def test_get_room_not_found(self, sample_project):
        """Test getting non-existent room."""
        result = get_room("nonexistent")
        assert "error" in result

    def test_create_room(self, sample_project):
        """Test creating a new room."""
        result = create_or_update_room(
            room_id="new_room",
            name="New Room",
            background="/assets/backgrounds/new.png",
            player_start_x=500,
            player_start_y=500
        )
        assert result["status"] == "ok"
        assert result["action"] == "created"
        assert result["room"]["id"] == "new_room"

        # Verify it was added
        rooms = list_rooms()
        assert rooms["count"] == 2

    def test_update_room(self, sample_project):
        """Test updating an existing room."""
        result = create_or_update_room(
            room_id="test_room",
            name="Updated Room Name",
            background="/assets/backgrounds/updated.png"
        )
        assert result["status"] == "ok"
        assert result["action"] == "updated"
        assert result["room"]["name"] == "Updated Room Name"

    def test_delete_room(self, sample_project):
        """Test deleting a room."""
        # Create a second room first
        create_or_update_room("room2", "Room 2")
        result = delete_room("room2")
        assert result["status"] == "ok"
        assert result["deleted"] == 1

        rooms = list_rooms()
        assert rooms["count"] == 1

    def test_set_start_room(self, sample_project):
        """Test setting start room."""
        create_or_update_room("another_room", "Another Room")
        result = set_start_room("another_room")
        assert result["status"] == "ok"
        assert result["start_room"] == "another_room"

        proj = _load_proj()
        assert proj["start_room"] == "another_room"


# ============================================================================
# Hotspot Tests
# ============================================================================

class TestHotspots:
    def test_list_hotspots(self, sample_project):
        """Test listing hotspots."""
        result = list_hotspots("test_room")
        assert result["room_id"] == "test_room"
        assert result["count"] == 0

    def test_create_hotspot(self, sample_project):
        """Test creating a hotspot."""
        result = create_or_update_hotspot(
            room_id="test_room",
            hotspot_id="test_prop",
            name="Test Prop",
            hs_type="prop",
            x=100, y=200, w=50, h=60,
            look_text="It's a test prop."
        )
        assert result["status"] == "ok"
        assert result["action"] == "created"
        assert result["hotspot"]["id"] == "test_prop"
        assert result["hotspot"]["type"] == "prop"

    def test_create_door_hotspot(self, sample_project):
        """Test creating an exit door."""
        # Create another room first
        create_or_update_room("room2", "Room 2")

        result = create_or_update_hotspot(
            room_id="test_room",
            hotspot_id="door_to_room2",
            name="Door to Room 2",
            hs_type="exit",
            x=600, y=200, w=100, h=200,
            target_room="room2"
        )
        assert result["status"] == "ok"
        assert result["hotspot"]["type"] == "exit"
        assert result["hotspot"]["target_room"] == "room2"

    def test_delete_hotspot(self, sample_project):
        """Test deleting a hotspot."""
        create_or_update_hotspot("test_room", "to_delete", "Delete Me", hs_type="prop")
        result = delete_hotspot("test_room", "to_delete")
        assert result["status"] == "ok"
        assert result["deleted"] == 1

    def test_link_door(self, sample_project):
        """Test linking doors with auto return door."""
        create_or_update_room("room2", "Room 2")

        result = link_door(
            source_room_id="test_room",
            hotspot_id="door1",
            target_room_id="room2",
            door_name="Door to Room 2",
            create_return_door=True
        )
        assert result["status"] == "ok"
        assert result["door"]["target_room"] == "room2"
        assert result["return_door"] is not None
        assert result["return_door"]["target_room"] == "test_room"


# ============================================================================
# Item Tests
# ============================================================================

class TestItems:
    def test_list_items(self, sample_project):
        """Test listing items."""
        result = list_items()
        assert result["count"] == 1
        assert result["items"][0]["id"] == "test_item"

    def test_create_item(self, sample_project):
        """Test creating an item."""
        result = create_or_update_item(
            item_id="new_item",
            name="New Item",
            description="A brand new item",
            icon="/assets/items/new.png"
        )
        assert result["status"] == "ok"
        assert result["item"]["id"] == "new_item"
        assert result["item"]["name"] == "New Item"

    def test_create_item_with_placement(self, sample_project):
        """Test creating an item and placing it in a room."""
        result = create_or_update_item(
            item_id="placed_item",
            name="Placed Item",
            description="An item on the floor",
            icon="/assets/items/placed.png",
            place_in_room="test_room",
            x=300, y=400
        )
        assert result["status"] == "ok"
        assert result["placed_hotspot"] is not None
        assert result["placed_hotspot"]["type"] == "pickup"
        assert result["placed_hotspot"]["item_id"] == "placed_item"

    def test_delete_item(self, sample_project):
        """Test deleting an item."""
        create_or_update_item("to_delete", "Delete Me")
        result = delete_item("to_delete")
        assert result["status"] == "ok"
        assert result["deleted"] == 1

    def test_link_item_usage_unlock_door(self, sample_project):
        """Test linking item to unlock a door."""
        create_or_update_room("locked_room", "Locked Room")
        create_or_update_hotspot("locked_room", "locked_door", "Locked Door", hs_type="exit", locked=True)

        result = link_item_usage(
            item_id="test_item",
            target_id="locked_door",
            purpose="unlock_door",
            sets_flag="door_unlocked"
        )
        assert result["status"] == "ok"
        assert result["puzzle"]["trigger"] == "use_item_on_hotspot"
        assert result["door_updated"] is True


# ============================================================================
# Puzzle Tests
# ============================================================================

class TestPuzzles:
    def test_list_puzzles(self, sample_project):
        """Test listing puzzles."""
        result = list_puzzles()
        assert result["count"] == 0
        assert result["puzzles"] == []

    def test_create_puzzle(self, sample_project):
        """Test creating a puzzle."""
        result = create_or_update_puzzle(
            puzzle_id="test_puzzle",
            name="Test Puzzle",
            trigger="use_item_on_hotspot",
            item_id="test_item",
            target_id="some_target",
            sets_flag="puzzle_solved"
        )
        assert result["status"] == "ok"
        assert result["action"] == "created"
        assert result["puzzle"]["id"] == "test_puzzle"

    def test_update_puzzle(self, sample_project):
        """Test updating a puzzle."""
        create_or_update_puzzle("puzzle1", "Puzzle 1")
        result = create_or_update_puzzle("puzzle1", "Updated Puzzle Name")
        assert result["action"] == "updated"
        assert result["puzzle"]["name"] == "Updated Puzzle Name"

    def test_delete_puzzle(self, sample_project):
        """Test deleting a puzzle."""
        create_or_update_puzzle("to_delete", "Delete Me")
        result = delete_puzzle("to_delete")
        assert result["status"] == "ok"
        assert result["deleted"] == 1


# ============================================================================
# Dialog Tests
# ============================================================================

class TestDialogs:
    def test_list_dialog_trees(self, sample_project):
        """Test listing dialog trees."""
        result = list_dialog_trees()
        assert result["count"] == 0

    def test_create_dialog_tree(self, sample_project):
        """Test creating a dialog tree."""
        result = create_or_update_dialog_tree(
            dialog_id="test_dialog",
            name="Test Conversation",
            npc_name="Test NPC",
            root_node="start"
        )
        assert result["status"] == "ok"
        assert result["dialog"]["id"] == "test_dialog"
        assert result["dialog"]["npc_name"] == "Test NPC"
        assert len(result["dialog"]["nodes"]) == 1  # Default root node

    def test_add_dialog_node(self, sample_project):
        """Test adding a node to a dialog tree."""
        create_or_update_dialog_tree("dialog1", "Dialog 1", "NPC 1")
        result = add_or_update_dialog_node(
            dialog_id="dialog1",
            node_id="node2",
            speaker="npc",
            npc_text="This is node 2"
        )
        assert result["status"] == "ok"
        assert result["node"]["id"] == "node2"
        assert result["node"]["speaker"] == "npc"

    def test_add_dialog_choice(self, sample_project):
        """Test adding a player choice."""
        create_or_update_dialog_tree("dialog1", "Dialog 1", "NPC 1")
        result = add_dialog_player_choice(
            dialog_id="dialog1",
            node_id="root",
            text="Hello there!",
            reply_text="Hi!",
            next_node="__exit__"
        )
        assert result["status"] == "ok"
        assert result["choice"]["text"] == "Hello there!"
        assert result["choice"]["next_node"] == "__exit__"


# ============================================================================
# Cutscene Tests
# ============================================================================

class TestCutscenes:
    def test_list_cutscenes(self, sample_project):
        """Test listing cutscenes."""
        result = list_cutscenes()
        assert result["count"] == 0

    def test_create_cutscene(self, sample_project):
        """Test creating a cutscene."""
        result = create_or_update_cutscene(
            cutscene_id="intro",
            name="Introduction",
            trigger_type="on_enter_room",
            trigger_target="test_room"
        )
        assert result["status"] == "ok"
        assert result["cutscene"]["id"] == "intro"
        assert result["cutscene"]["trigger_type"] == "on_enter_room"

    def test_add_cutscene_step(self, sample_project):
        """Test adding steps to a cutscene."""
        create_or_update_cutscene("cs1", "Cutscene 1")

        # Add say step
        result = add_cutscene_step("cs1", "say", actor="player", text="Hello!", duration=3.0)
        assert result["status"] == "ok"
        assert result["step"]["type"] == "say"

        # Add walk step
        result = add_cutscene_step("cs1", "walk", actor="player", x=500, y=500)
        assert result["step"]["type"] == "walk"

        # Add fade step
        result = add_cutscene_step("cs1", "fade", effect="fade_in", duration=1.0)
        assert result["step"]["type"] == "fade"

    def test_get_cutscene(self, sample_project):
        """Test getting full cutscene details."""
        create_or_update_cutscene("cs1", "Cutscene 1")
        add_cutscene_step("cs1", "say", actor="player", text="Line 1")
        add_cutscene_step("cs1", "say", actor="partner", text="Line 2")

        result = get_cutscene("cs1")
        assert "cutscene" in result
        steps = result["cutscene"]["steps"]
        # create_or_update_cutscene seeds 2 default steps, plus the 2 added above
        assert len(steps) == 4
        assert steps[-1]["text"] == "Line 2"


# ============================================================================
# Sprite Tests
# ============================================================================

class TestSprites:
    def test_list_sprites(self, sample_project):
        """Test listing sprites."""
        result = list_sprites()
        assert result["count"] == 0
        assert result["sprites"] == []


# ============================================================================
# Asset Tests
# ============================================================================

class TestAssets:
    def test_list_assets(self, sample_project):
        """Test listing assets."""
        result = list_assets()
        assert "count" in result
        assert "assets" in result
        assert isinstance(result["assets"], list)


# ============================================================================
# Tool Registry Tests
# ============================================================================

class TestToolRegistry:
    def test_tools_list_not_empty(self):
        """Test that tools are registered."""
        assert len(TOOLS_LIST) > 50  # We have 57+ tools
        assert len(TOOLS_BY_NAME) == len(TOOLS_LIST)

    def test_all_tools_have_names(self):
        """Test all tools have proper names."""
        for fn in TOOLS_LIST:
            assert hasattr(fn, "__name__")
            assert fn.__name__ in TOOLS_BY_NAME

    def test_all_tools_have_docstrings(self):
        """Test all tools have docstrings."""
        for fn in TOOLS_LIST:
            assert fn.__doc__ is not None
            assert len(fn.__doc__.strip()) > 0

    def test_tool_categories_covered(self):
        """Test that all major categories have tools."""
        tool_names = [fn.__name__ for fn in TOOLS_LIST]

        # Check key categories
        assert any("room" in n for n in tool_names)
        assert any("hotspot" in n for n in tool_names)
        assert any("item" in n for n in tool_names)
        assert any("puzzle" in n for n in tool_names)
        assert any("dialog" in n for n in tool_names)
        assert any("cutscene" in n for n in tool_names)
        assert any("sprite" in n for n in tool_names)
        assert any("asset" in n for n in tool_names)
        assert any("media" in n or "sound" in n or "image" in n for n in tool_names)
        assert any("vlm" in n for n in tool_names)


# ============================================================================
# Pygame Process Tests
# ============================================================================

class TestPygameProcess:
    @patch("tools.project.subprocess.Popen")
    def test_launch_pygame_game(self, mock_popen, sample_project):
        """Test launching pygame game."""
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        result = launch_pygame_game(room_id="test_room")
        assert result["status"] == "launched"
        assert result["pid"] == 12345
        assert "test_room" in str(result)

    @patch("tools._core.PYGAME_PROC", new_callable=lambda: MagicMock())
    def test_stop_pygame_game(self, mock_proc, sample_project):
        """Test stopping pygame game."""
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345

        result = stop_pygame_game()
        assert result["status"] == "stopped"
        assert result["pid"] == 12345


# ============================================================================
# Collision Geometry Tool Tests
# ============================================================================

class TestColliderTools:
    """The MCP surface for marking blocked space (walls, furniture)."""

    def test_list_colliders_on_empty_room(self, sample_project):
        result = list_room_colliders("test_room")
        assert result["count"] == 0
        assert result["colliders"] == []

    def test_list_colliders_unknown_room(self, sample_project):
        assert "error" in list_room_colliders("nope")

    def test_add_rect_collider(self, sample_project):
        result = add_room_collider("test_room", "rect", x=100, y=200, w=300, h=40)
        assert result["status"] == "ok"
        collider = result["collider"]
        assert collider["type"] == "rect"
        assert collider["x"] == 100
        assert collider["w"] == 300

        stored = list_room_colliders("test_room")
        assert stored["count"] == 1

    def test_add_poly_collider(self, sample_project):
        pts = json.dumps([{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 50, "y": 100}])
        result = add_room_collider("test_room", "poly", points_json=pts)
        assert result["status"] == "ok"
        assert result["collider"]["type"] == "poly"
        assert len(result["collider"]["points"]) == 3

    def test_add_poly_with_bad_json(self, sample_project):
        result = add_room_collider("test_room", "poly", points_json="{not json")
        assert "error" in result

    def test_add_collider_unknown_room(self, sample_project):
        assert "error" in add_room_collider("nope", "rect")

    def test_collider_ids_are_unique(self, sample_project):
        add_room_collider("test_room", "rect", collider_id="wall")
        add_room_collider("test_room", "rect", collider_id="wall")
        colliders = list_room_colliders("test_room")["colliders"]
        ids = [c["id"] for c in colliders]
        assert len(set(ids)) == 2

    def test_set_room_colliders_replaces_all(self, sample_project):
        add_room_collider("test_room", "rect")
        payload = json.dumps([
            {"type": "rect", "x": 1, "y": 2, "w": 3, "h": 4},
            {"type": "poly", "points": [{"x": 0, "y": 0}, {"x": 9, "y": 0}, {"x": 9, "y": 9}]},
        ])
        result = set_room_colliders("test_room", payload)
        assert result["count"] == 2
        assert list_room_colliders("test_room")["count"] == 2

    def test_set_room_colliders_rejects_junk(self, sample_project):
        assert "error" in set_room_colliders("test_room", "not json")
        assert "error" in set_room_colliders("test_room", json.dumps({"a": 1}))
        assert "error" in set_room_colliders("test_room", json.dumps([{"type": "blob"}]))

    def test_clear_room_colliders(self, sample_project):
        add_room_collider("test_room", "rect")
        result = clear_room_colliders("test_room")
        assert result["removed"] == 1
        assert list_room_colliders("test_room")["count"] == 0


# ============================================================================
# Character Tool Tests
# ============================================================================

class TestCharacterTools:
    """The MCP surface for the generic character roster."""

    def test_list_characters_seeds_from_legacy(self, sample_project):
        result = list_characters()
        assert result["count"] == 1
        assert result["characters"][0]["sprite"] == "hero"
        assert result["characters"][0]["is_player"] is True

    def test_create_character(self, sample_project):
        result = create_or_update_character("npc_mira", name="Mira", sprite="mira", role="npc")
        assert result["status"] == "ok"
        assert result["character"]["name"] == "Mira"
        assert result["character"]["role"] == "npc"

    def test_create_companion_defaults_to_following(self, sample_project):
        create_or_update_character("pal", name="Bibi", sprite="bibi", role="companion")
        chars = {c["id"]: c for c in list_characters()["characters"]}
        assert chars["pal"]["follow"] is True
        assert chars["pal"]["is_companion"] is True

    def test_update_character_keeps_other_fields(self, sample_project):
        create_or_update_character("pal", name="Bibi", sprite="bibi", role="companion")
        create_or_update_character("pal", dialog_id="dlg_bibi")
        char = get_character("pal")["character"]
        assert char["name"] == "Bibi"
        assert char["dialog_id"] == "dlg_bibi"

    def test_set_player_character(self, sample_project):
        create_or_update_character("hero2", name="Vex", sprite="vex", role="npc")
        result = set_player_character("hero2")
        assert result["status"] == "ok"
        assert list_characters()["player_character"] == "hero2"

    def test_set_player_character_unknown(self, sample_project):
        assert "error" in set_player_character("ghost")

    def test_delete_character(self, sample_project):
        create_or_update_character("temp", name="Temp")
        result = delete_character("temp")
        assert result["deleted"] == "temp"
        assert "error" in get_character("temp")

    def test_delete_character_detaches_hotspots(self, sample_project):
        create_or_update_hotspot("test_room", "npc1", name="Guard", hs_type="npc")
        create_or_update_character("guard", name="Guard", role="npc")
        assign_character_to_hotspot("test_room", "npc1", "guard")
        result = delete_character("guard")
        assert result["detached_hotspots"] == 1
        room = get_room("test_room")["room"]
        assert "character_id" not in room["hotspots"][0]

    def test_assign_character_to_hotspot(self, sample_project):
        create_or_update_hotspot("test_room", "npc1", name="Guard", hs_type="npc")
        create_or_update_character("guard", name="Guard", sprite="guard_sheet", role="npc")
        result = assign_character_to_hotspot("test_room", "npc1", "guard")
        assert result["status"] == "ok"
        room = get_room("test_room")["room"]
        hs = room["hotspots"][0]
        assert hs["character_id"] == "guard"
        assert hs["sprite_id"] == "guard_sheet"

    def test_assign_character_unknown_hotspot(self, sample_project):
        assert "error" in assign_character_to_hotspot("test_room", "nope", "x")

    def test_legacy_set_character_roles_updates_registry(self, sample_project):
        from tools import set_character_roles
        result = set_character_roles(player_sprite="newhero")
        assert result["player_sprite"] == "newhero"
        assert list_characters()["player_character"]


# ============================================================================
# Event Tool Tests
# ============================================================================

class TestEventTools:
    """The MCP surface for the event system."""

    def test_list_events_empty(self, sample_project):
        result = list_events()
        assert result["count"] == 0
        assert "on_enter_room" in result["trigger_types"]
        assert "set_flag" in result["action_types"]

    def test_create_event(self, sample_project):
        result = create_or_update_event(
            "ev_intro", name="Intro", trigger_type="on_enter_room", trigger_target="test_room"
        )
        assert result["status"] == "ok"
        assert result["event"]["trigger"]["target"] == "test_room"
        assert list_events()["count"] == 1

    def test_get_event(self, sample_project):
        create_or_update_event("ev1", name="One")
        assert get_event("ev1")["event"]["name"] == "One"
        assert "error" in get_event("missing")

    def test_update_event_preserves_actions(self, sample_project):
        create_or_update_event("ev1", name="One")
        add_event_action("ev1", "set_flag", "flag_a")
        create_or_update_event("ev1", name="Renamed")
        event = get_event("ev1")["event"]
        assert event["name"] == "Renamed"
        assert len(event["actions"]) == 1

    def test_add_and_remove_action(self, sample_project):
        create_or_update_event("ev1")
        add_event_action("ev1", "set_flag", "a")
        add_event_action("ev1", "play_cutscene", "intro")
        event = get_event("ev1")["event"]
        assert len(event["actions"]) == 2
        remove_event_action("ev1", 0)
        event = get_event("ev1")["event"]
        assert len(event["actions"]) == 1
        assert event["actions"][0]["type"] == "play_cutscene"

    def test_remove_action_out_of_range(self, sample_project):
        create_or_update_event("ev1")
        assert "error" in remove_event_action("ev1", 5)

    def test_add_action_unknown_type(self, sample_project):
        create_or_update_event("ev1")
        assert "error" in add_event_action("ev1", "explode", "x")

    def test_add_action_to_missing_event(self, sample_project):
        assert "error" in add_event_action("ghost", "set_flag", "x")

    def test_set_event_actions(self, sample_project):
        create_or_update_event("ev1")
        payload = json.dumps([
            {"type": "set_flag", "value": "a"},
            {"type": "show_text", "value": "Hello"},
        ])
        result = set_event_actions("ev1", payload)
        assert result["action_count"] == 2
        assert "error" in set_event_actions("ev1", "nope")

    def test_delete_event(self, sample_project):
        create_or_update_event("ev1")
        result = delete_event("ev1")
        assert result["deleted"] == 1
        assert list_events()["count"] == 0

    def test_migrate_legacy_triggers(self, sample_project):
        create_or_update_cutscene("cs1", "Intro Cutscene", trigger_type="on_enter_room", trigger_target="test_room")
        result = migrate_legacy_triggers()
        assert result["migrated"] == 1
        events = list_events()["events"]
        assert events[0]["trigger"]["type"] == "on_enter_room"
        assert events[0]["actions"][0]["type"] == "play_cutscene"

    def test_migrate_legacy_triggers_is_idempotent(self, sample_project):
        create_or_update_cutscene("cs1", "Intro", trigger_type="on_enter_room", trigger_target="test_room")
        migrate_legacy_triggers()
        second = migrate_legacy_triggers()
        assert second["migrated"] == 0
        assert list_events()["count"] == 1


# ============================================================================
# Registry Tests
# ============================================================================

class TestToolRegistry:
    def test_new_tools_are_registered(self):
        for name in (
            "list_room_colliders", "add_room_collider", "set_room_colliders", "clear_room_colliders",
            "list_characters", "create_or_update_character", "set_player_character",
            "list_events", "create_or_update_event", "add_event_action", "migrate_legacy_triggers",
        ):
            assert name in TOOLS_BY_NAME, f"{name} is not registered"

    def test_no_duplicate_tools(self):
        names = [fn.__name__ for fn in TOOLS_LIST]
        assert len(names) == len(set(names))

    def test_every_tool_has_a_docstring(self):
        for fn in TOOLS_LIST:
            assert fn.__doc__, f"{fn.__name__} has no docstring"


# ============================================================================
# API Integration Tests (require running server)
# ============================================================================

class TestAPIEndpoints:
    """Integration tests for API endpoints - require running server."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """Test health check endpoint."""
        # This would require a running server
        pass


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
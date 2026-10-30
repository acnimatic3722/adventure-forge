# AdventureForge — Tests for the new subsystems
"""
Covers the three features added in this pass:

* collision geometry (``engine_geometry``) — the maths the runtime uses to
  keep characters out of walls, and the MCP tools that author them;
* the generic character system (``engine_characters`` + ``tools.characters``);
* the event system (``engine_events`` + ``tools.events``).
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine_geometry import (
    BLOCKED_ARRIVE_DISTANCE,
    collider_blocks,
    collider_contains_point,
    collider_points,
    nearest_free_point,
    normalize_collider,
    point_blocked,
    point_in_poly,
    resolve_movement,
)
from engine_characters import (
    build_character_registry,
    companion_character_ids,
    normalize_character,
    resolve_player_character_id,
)
from engine_events import (
    event_matches,
    migrate_cutscene_triggers,
    normalize_event,
    normalize_events,
    sort_events,
)


# ============================================================================
# Collision geometry
# ============================================================================

class TestColliderGeometry:
    """The pure maths behind 'the character cannot walk through this'."""

    def test_rect_contains_point(self):
        c = {"id": "a", "type": "rect", "x": 100, "y": 100, "w": 50, "h": 50}
        assert collider_contains_point(120, 120, c)
        assert not collider_contains_point(90, 120, c)
        assert not collider_contains_point(160, 120, c)

    def test_rect_blocks_within_radius(self):
        c = {"id": "a", "type": "rect", "x": 100, "y": 100, "w": 50, "h": 50}
        # 10px outside the left edge, radius 14 -> blocked
        assert collider_blocks(90, 120, 14, c)
        # 30px outside -> clear
        assert not collider_blocks(70, 120, 14, c)

    def test_rect_with_zero_size_blocks_nothing(self):
        c = {"id": "a", "type": "rect", "x": 100, "y": 100, "w": 0, "h": 50}
        assert not collider_blocks(100, 120, 14, c)

    def test_poly_contains_point(self):
        c = {
            "id": "p", "type": "poly",
            "points": [{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 100}, {"x": 0, "y": 100}],
        }
        assert collider_contains_point(50, 50, c)
        assert not collider_contains_point(150, 50, c)

    def test_poly_blocks_near_the_edge(self):
        c = {
            "id": "p", "type": "poly",
            "points": [{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 100}, {"x": 0, "y": 100}],
        }
        assert collider_blocks(108, 50, 14, c)
        assert not collider_blocks(140, 50, 14, c)

    def test_rect_points_are_corners(self):
        pts = collider_points({"type": "rect", "x": 0, "y": 0, "w": 10, "h": 20})
        assert pts == [(0.0, 0.0), (10.0, 0.0), (10.0, 20.0), (0.0, 20.0)]

    def test_point_blocked_checks_every_collider(self):
        colliders = [
            {"id": "a", "type": "rect", "x": 0, "y": 0, "w": 10, "h": 10},
            {"id": "b", "type": "rect", "x": 100, "y": 100, "w": 10, "h": 10},
        ]
        assert point_blocked(5, 5, 2, colliders)
        assert point_blocked(105, 105, 2, colliders)
        assert not point_blocked(50, 50, 2, colliders)

    def test_point_blocked_with_no_colliders(self):
        assert not point_blocked(10, 10, 14, None)
        assert not point_blocked(10, 10, 14, [])


class TestMovementResolution:
    """Movement slides along walls instead of stopping dead."""

    def test_free_move_is_untouched(self):
        nx, ny = resolve_movement(50, 50, 40, 40, 14, [])
        assert (nx, ny) == (50, 50)

    def test_blocked_move_stops_at_origin(self):
        wall = [{"id": "w", "type": "rect", "x": 100, "y": 0, "w": 100, "h": 200}]
        nx, ny = resolve_movement(150, 50, 50, 50, 14, wall)
        assert (nx, ny) == (50, 50)

    def test_slides_horizontally_along_a_wall(self):
        # Wall to the right; the character should keep sliding vertically.
        wall = [{"id": "w", "type": "rect", "x": 100, "y": 0, "w": 100, "h": 200}]
        nx, ny = resolve_movement(150, 80, 50, 50, 14, wall)
        assert nx == 50      # horizontal blocked
        assert ny == 80      # vertical allowed -> slides

    def test_slides_vertically_along_a_wall(self):
        # Wall below; the character should keep sliding horizontally.
        wall = [{"id": "w", "type": "rect", "x": 0, "y": 100, "w": 200, "h": 100}]
        nx, ny = resolve_movement(80, 150, 50, 50, 14, wall)
        assert nx == 80      # horizontal allowed
        assert ny == 50      # vertical blocked

    def test_corner_is_fully_blocked(self):
        # Two walls that block the horizontal step *and* the vertical step.
        walls = [
            {"id": "a", "type": "rect", "x": 100, "y": 0, "w": 100, "h": 100},
            {"id": "b", "type": "rect", "x": 0, "y": 100, "w": 200, "h": 100},
        ]
        nx, ny = resolve_movement(150, 150, 50, 50, 14, walls)
        assert (nx, ny) == (50, 50)

    def test_radius_is_respected(self):
        # A 10px gap is passable for a 4px character but not a 14px one.
        gap = [
            {"id": "a", "type": "rect", "x": 100, "y": 0, "w": 100, "h": 45},
            {"id": "b", "type": "rect", "x": 100, "y": 55, "w": 100, "h": 100},
        ]
        assert resolve_movement(150, 50, 50, 50, 4, gap) == (150, 50)
        assert resolve_movement(150, 50, 50, 50, 14, gap) == (50, 50)


class TestNearestFreePoint:
    def test_returns_original_when_free(self):
        assert nearest_free_point(50, 50, 14, []) == (50, 50)

    def test_pushes_out_of_a_wall(self):
        wall = [{"id": "w", "type": "rect", "x": 0, "y": 0, "w": 100, "h": 100}]
        x, y = nearest_free_point(50, 50, 14, wall)
        assert not point_blocked(x, y, 14, wall)

    def test_gives_up_gracefully(self):
        # Everything is blocked — return the original point rather than looping.
        wall = [{"id": "w", "type": "rect", "x": 0, "y": 0, "w": 1000, "h": 1000}]
        assert nearest_free_point(500, 500, 14, wall, max_radius=16) == (500, 500)


class TestNormalizeCollider:
    def test_rect_is_coerced(self):
        out = normalize_collider({"id": "a", "type": "rect", "x": "10", "y": "20", "w": "30", "h": "40"})
        assert out == {"id": "a", "type": "rect", "x": 10.0, "y": 20.0, "w": 30.0, "h": 40.0}

    def test_poly_requires_three_points(self):
        with pytest.raises(ValueError):
            normalize_collider({"type": "poly", "points": [{"x": 0, "y": 0}]})

    def test_rejects_unknown_type(self):
        with pytest.raises(ValueError):
            normalize_collider({"type": "circle", "x": 0, "y": 0})

    def test_defaults_to_rect(self):
        out = normalize_collider({"x": 1, "y": 2, "w": 3, "h": 4})
        assert out["type"] == "rect"


# ============================================================================
# Character system
# ============================================================================

class TestCharacterRegistry:
    def test_builds_from_explicit_map(self):
        project = {
            "characters": {
                "hero": {"name": "Vex", "sprite": "vex_sheet", "role": "player"},
                "pal": {"name": "Bibi", "sprite": "bibi_sheet", "role": "companion", "follow": True},
                "shopkeep": {"name": "Mira", "role": "npc"},
            },
            "player_character": "hero",
        }
        registry = build_character_registry(project)
        assert set(registry) == {"hero", "pal", "shopkeep"}
        assert registry["hero"]["name"] == "Vex"
        assert registry["pal"]["follow"] is True
        assert registry["shopkeep"]["follow"] is False

    def test_falls_back_to_legacy_sprite_slots(self):
        project = {
            "player_sprite": "sam",
            "partner_sprite": "max",
            "partner_dialog_id": "max_banter",
            "sprites": {"sam": {"name": "Sam"}, "max": {"name": "Max"}},
        }
        registry = build_character_registry(project)
        assert len(registry) == 2
        roles = {c["role"] for c in registry.values()}
        assert roles == {"player", "companion"}
        companion = next(c for c in registry.values() if c["role"] == "companion")
        assert companion["name"] == "Max"
        assert companion["dialog_id"] == "max_banter"

    def test_player_resolution_prefers_explicit(self):
        project = {
            "characters": {
                "a": {"role": "player", "sprite": "a"},
                "b": {"role": "player", "sprite": "b"},
            },
            "player_character": "b",
        }
        assert resolve_player_character_id(project) == "b"

    def test_player_resolution_falls_back_to_role(self):
        project = {"characters": {"a": {"role": "player", "sprite": "a"}}}
        assert resolve_player_character_id(project) == "a"

    def test_no_characters_at_all(self):
        assert build_character_registry({}) == {}
        assert resolve_player_character_id({}) == ""

    def test_companion_ids_only_include_followers(self):
        registry = build_character_registry({
            "characters": {
                "a": {"role": "companion", "follow": True},
                "b": {"role": "companion", "follow": False},
                "c": {"role": "npc"},
            }
        })
        assert companion_character_ids(registry) == ["a"]

    def test_name_defaults_from_sprite_metadata(self):
        char = normalize_character("x", {"sprite": "sam", "role": "npc"}, {"sam": {"name": "Sam (Dog)"}})
        assert char["name"] == "Sam"

    def test_invalid_role_falls_back_to_npc(self):
        char = normalize_character("x", {"role": "wizard"})
        assert char["role"] == "npc"

    def test_color_parsing(self):
        assert normalize_character("x", {"color": "255,128,0"})["color"] == [255, 128, 0]
        assert normalize_character("x", {"color": "#ff8000"})["color"] == [255, 128, 0]
        assert normalize_character("x", {"color": [1, 2, 3]})["color"] == [1, 2, 3]

    def test_scale_zero_means_use_sprite_scale(self):
        assert normalize_character("x", {"scale": 0})["scale"] == 0.0
        assert normalize_character("x", {"scale": 4.5})["scale"] == 4.5


# ============================================================================
# Event system
# ============================================================================

class TestEventModel:
    def test_normalises_trigger_and_actions(self):
        ev = normalize_event("e1", {
            "name": "Intro",
            "trigger": {"type": "on_enter_room", "target": "lobby"},
            "actions": [{"type": "set_flag", "value": "seen"}, "play_cutscene"],
        })
        assert ev["id"] == "e1"
        assert ev["trigger"] == {"type": "on_enter_room", "target": "lobby"}
        assert ev["actions"][0] == {"type": "set_flag", "value": "seen"}
        assert ev["actions"][1]["type"] == "play_cutscene"

    def test_unknown_trigger_is_dropped(self):
        ev = normalize_event("e1", {"trigger": {"type": "on_tuesday"}})
        assert ev["trigger"]["type"] == ""

    def test_normalize_events_accepts_a_dict(self):
        events = normalize_events({"e1": {"trigger": {"type": "on_game_start"}}})
        assert len(events) == 1
        assert events[0]["id"] == "e1"

    def test_matching_requires_the_target(self):
        ev = normalize_event("e1", {"trigger": {"type": "on_enter_room", "target": "lobby"}})
        assert event_matches(ev, "on_enter_room", "lobby")
        assert not event_matches(ev, "on_enter_room", "cellar")
        assert not event_matches(ev, "on_flag_set", "lobby")

    def test_empty_target_matches_anything(self):
        ev = normalize_event("e1", {"trigger": {"type": "on_item_pickup", "target": ""}})
        assert event_matches(ev, "on_item_pickup", "anything")

    def test_requires_flag_gate(self):
        ev = normalize_event("e1", {
            "trigger": {"type": "on_enter_room"},
            "requires_flag": "has_key",
        })
        assert not event_matches(ev, "on_enter_room", "r", flags=set())
        assert event_matches(ev, "on_enter_room", "r", flags={"has_key"})

    def test_disabled_events_never_match(self):
        ev = normalize_event("e1", {"trigger": {"type": "on_game_start"}, "enabled": False})
        assert not event_matches(ev, "on_game_start")

    def test_priority_sorting_is_highest_first(self):
        events = [
            normalize_event("low", {"priority": 1}),
            normalize_event("high", {"priority": 10}),
            normalize_event("mid", {"priority": 5}),
        ]
        assert [e["id"] for e in sort_events(events)] == ["high", "mid", "low"]


class TestLegacyMigration:
    def test_migrates_on_enter_room_cutscene(self):
        cutscenes = [{
            "id": "intro",
            "name": "Intro",
            "trigger_type": "on_enter_room",
            "trigger_target": "lobby",
            "once": True,
        }]
        migrated = migrate_cutscene_triggers(cutscenes)
        assert len(migrated) == 1
        assert migrated[0]["trigger"] == {"type": "on_enter_room", "target": "lobby"}
        assert migrated[0]["actions"][0] == {"type": "play_cutscene", "value": "intro"}
        assert migrated[0]["legacy"] is True

    def test_migrates_on_flag_set_cutscene(self):
        cutscenes = [{"id": "cs", "trigger_type": "on_flag_set", "trigger_target": "door_open"}]
        migrated = migrate_cutscene_triggers(cutscenes)
        assert migrated[0]["trigger"]["type"] == "on_flag_set"

    def test_manual_cutscenes_are_not_migrated(self):
        assert migrate_cutscene_triggers([{"id": "cs", "trigger_type": "manual"}]) == []

    def test_flag_target_is_required(self):
        assert migrate_cutscene_triggers([{"id": "cs", "trigger_type": "on_flag_set"}]) == []

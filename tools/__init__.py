"""
AdventureForge — MCP Tools Package
All tools organized by domain.
"""

from .project import (
    get_project_summary,
    get_full_project,
    set_project_title,
    set_character_roles,
    launch_pygame_game,
    stop_pygame_game,
)

from .rooms import (
    list_rooms,
    get_room,
    create_or_update_room,
    delete_room,
    update_room_map_position,
    set_room_walkable_polygon,
    set_start_room,
)

from .hotspots import (
    list_hotspots,
    get_hotspot,
    create_or_update_hotspot,
    delete_hotspot,
    link_door,
    set_hotspot_lock,
)

from .items import (
    list_items,
    get_item,
    create_or_update_item,
    delete_item,
    link_item_usage,
)

from .puzzles import (
    list_puzzles,
    get_puzzle,
    create_or_update_puzzle,
    delete_puzzle,
)

from .dialogs import (
    list_dialog_trees,
    get_dialog_tree,
    create_or_update_dialog_tree,
    delete_dialog_tree,
    add_or_update_dialog_node,
    delete_dialog_node,
    add_dialog_player_choice,
    delete_dialog_player_choice,
    ai_generate_dialog_tree,
)

from .cutscenes import (
    list_cutscenes,
    get_cutscene,
    create_or_update_cutscene,
    delete_cutscene,
    add_cutscene_step,
    delete_cutscene_step,
    ai_generate_cutscene,
)

from .sprites import (
    list_sprites,
    get_sprite,
    add_or_update_sprite_animation,
    delete_sprite_animation,
    assign_sprite_direction_role,
    set_sprite_scale,
)

from .assets import (
    list_assets,
    remove_asset_background,
    restore_asset_original,
    delete_asset_file,
    pixelize_asset,
)

from .media import (
    list_available_media_apis,
    search_and_download_sound_effects,
    search_and_download_images,
    spritefusion_get_credits,
    spritefusion_list_saved_assets,
    spritefusion_generate_pixel_art,
    jetson_generate_image,
    generate_image_ai,
    download_asset_from_url,
)

from .vlm import (
    create_coordinate_grid_overlay,
    vlm_auto_detect_and_place_props,
    vlm_generate_and_place_items,
    vlm_describe_hotspot,
    vlm_inspect_room_scene,
)

# Collect all tools for MCP server
TOOLS_LIST = [
    get_project_summary,
    get_full_project,
    set_project_title,
    set_character_roles,
    launch_pygame_game,
    stop_pygame_game,
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
    delete_dialog_node,
    add_dialog_player_choice,
    delete_dialog_player_choice,
    ai_generate_dialog_tree,
    list_cutscenes,
    get_cutscene,
    create_or_update_cutscene,
    delete_cutscene,
    add_cutscene_step,
    delete_cutscene_step,
    ai_generate_cutscene,
    list_sprites,
    get_sprite,
    add_or_update_sprite_animation,
    delete_sprite_animation,
    assign_sprite_direction_role,
    set_sprite_scale,
    list_assets,
    remove_asset_background,
    restore_asset_original,
    delete_asset_file,
    pixelize_asset,
    list_available_media_apis,
    search_and_download_sound_effects,
    search_and_download_images,
    spritefusion_get_credits,
    spritefusion_list_saved_assets,
    spritefusion_generate_pixel_art,
    jetson_generate_image,
    generate_image_ai,
    download_asset_from_url,
    create_coordinate_grid_overlay,
    vlm_auto_detect_and_place_props,
    vlm_generate_and_place_items,
    vlm_describe_hotspot,
    vlm_inspect_room_scene,
]

TOOLS_BY_NAME = {fn.__name__: fn for fn in TOOLS_LIST}
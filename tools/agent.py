"""
AdventureForge — Agent Interaction Loop (NVIDIA NIM Primary + Gemini Fallback)
"""
import inspect
import json
import re
import io
import base64
import time
import urllib.request
import os
from typing import Any

from google import genai
from google.genai import types
from PIL import Image

from ._core import (
    _load_proj,
    _get_api_keys,
    load_env,
    _resolve_asset,
)

# The canonical tool registry. Imported from the package (not from a module
# copy) so the in-app chat agent and external MCP clients operate on exactly
# the same tools. `tools/__init__.py` deliberately does NOT import this
# module, which keeps this import free of circularity.
from tools import TOOLS_LIST, TOOLS_BY_NAME


def _coerce_tool_args(fn, raw_args: dict[str, Any]) -> dict[str, Any]:
    """Coerce string arguments from LLM function calls into typed integers, floats, or booleans based on function signature."""
    if not callable(fn) or not isinstance(raw_args, dict):
        return raw_args or {}
    try:
        sig = inspect.signature(fn)
    except Exception:
        return raw_args

    coerced = {}
    for name, val in raw_args.items():
        if name not in sig.parameters:
            coerced[name] = val
            continue
        param = sig.parameters[name]
        ann = param.annotation
        if ann is int and isinstance(val, (str, float)):
            try:
                coerced[name] = int(val)
                continue
            except Exception:
                pass
        elif ann is float and isinstance(val, (str, int)):
            try:
                coerced[name] = float(val)
                continue
            except Exception:
                pass
        elif ann is bool and isinstance(val, str):
            coerced[name] = val.lower() in ("true", "1", "yes")
            continue
        coerced[name] = val
    return coerced


def function_to_openai_tool(fn) -> dict[str, Any]:
    """Convert a Python function into an OpenAI-compatible function calling tool schema."""
    doc = (fn.__doc__ or "").strip()
    sig = inspect.signature(fn)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for param_name, param in sig.parameters.items():
        param_type = "string"
        if param.annotation is int:
            param_type = "integer"
        elif param.annotation is float:
            param_type = "number"
        elif param.annotation is bool:
            param_type = "boolean"
        elif getattr(param.annotation, "__origin__", None) is list or param.annotation is list:
            param_type = "array"
        elif getattr(param.annotation, "__origin__", None) is dict or param.annotation is dict:
            param_type = "object"

        properties[param_name] = {"type": param_type}
        if param.default == inspect.Parameter.empty:
            required.append(param_name)

    return {
        "type": "function",
        "function": {
            "name": fn.__name__,
            "description": doc,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }
    }


def get_project_summary() -> dict[str, Any]:
    """Get a complete summary of the AdventureForge project."""
    proj = _load_proj()
    rooms_summary = []
    for r in proj.get("rooms", []):
        rooms_summary.append({
            "id": r.get("id"),
            "name": r.get("name"),
            "map_x": r.get("map_x", 100),
            "map_y": r.get("map_y", 100),
            "background": r.get("background"),
            "player_start": r.get("player_start"),
            "hotspots": [
                {
                    "id": h.get("id"),
                    "name": h.get("name"),
                    "type": h.get("type"),
                    "rect": h.get("rect"),
                    "item_id": h.get("item_id", ""),
                    "target_room": h.get("target_room", ""),
                    "locked": h.get("locked", False),
                    "required_flag": h.get("required_flag", ""),
                    "dialog_id": h.get("dialog_id", ""),
                    "cutscene_id": h.get("cutscene_id", ""),
                    "look_text": h.get("look_text", "")
                }
                for h in r.get("hotspots", [])
            ]
        })
    return {
        "title": proj.get("title"),
        "start_room": proj.get("start_room"),
        "player_sprite": proj.get("player_sprite"),
        "partner_sprite": proj.get("partner_sprite"),
        "partner_dialog_id": proj.get("partner_dialog_id", ""),
        "rooms": rooms_summary,
        "items": proj.get("items", []),
        "puzzles": proj.get("puzzles", []),
        "sprites": list(proj.get("sprites", {}).keys()),
        "dialogs": [{"id": d.get("id"), "name": d.get("name"), "npc_name": d.get("npc_name"), "node_count": len(d.get("nodes", []))} for d in proj.get("dialogs", [])],
        "cutscenes": [{"id": c.get("id"), "name": c.get("name"), "trigger_type": c.get("trigger_type"), "trigger_target": c.get("trigger_target"), "step_count": len(c.get("steps", []))} for c in proj.get("cutscenes", [])]
    }


def _run_nvidia_agent(
    user_message: str,
    current_room_id: str = "",
    include_room_vision: bool = True,
    history: list[dict[str, Any]] | None = None,
    model_name: str = "meta/llama-3.2-11b-vision-instruct"
) -> dict[str, Any]:
    """Run autonomous MCP agent powered by NVIDIA NIM (multimodal vision + 63 tool calling)."""
    keys = _get_api_keys()
    nv_key = keys.get("nvidia")
    if not nv_key:
        raise ValueError("NVIDIA_API_KEY not configured in .env")

    proj = _load_proj()
    openai_tools = [function_to_openai_tool(fn) for fn in TOOLS_LIST]

    summary_str = json.dumps(get_project_summary(), indent=2)
    system_instruction = f"""You are the AdventureForge AI Co-Creator & MCP Game Engine Architect, powered by NVIDIA NIM ({model_name}).
You have direct tool-calling access to inspect and modify data/project.json and /assets/*.
You have {len(TOOLS_LIST)} tools available. Call appropriate tools to fulfill the user's request.
Project Summary:
{summary_str}

Guidelines:
1. Always call the appropriate tool(s) to execute the user's intent. You can call multiple tools!
2. When the user asks for sound effects, audio, or music, use `search_and_download_sound_effects` with Freesound.
3. When the user asks for pixel art sprites, icons, props, or background images, use `jetson_generate_image` (NVIDIA Jetson GPU local Sakura-Iris-3B diffusion model), `spritefusion_generate_pixel_art`, `generate_image_ai`, or `search_and_download_images`. If the user asks for local/offline generation, prioritize `jetson_generate_image`.
4. When creating items that should appear in the world, use `create_or_update_item` with `place_in_room`.
5. When wiring items to doors, use `link_item_usage`.
6. Keep final responses clear, concise, and report what tools were called and what assets were created."""

    # Room Visual Inspection via NVIDIA Vision Encoder
    room_visual_summary = ""
    if include_room_vision and current_room_id:
        room = next((r for r in proj.get("rooms", []) if r.get("id") == current_room_id), None)
        if room and room.get("background"):
            bg_path = _resolve_asset(room["background"])
            if bg_path.exists():
                try:
                    with Image.open(bg_path).convert("RGB") as im:
                        im.thumbnail((800, 450))
                        buf = io.BytesIO()
                        im.save(buf, format="JPEG", quality=80)
                        b64_img = base64.b64encode(buf.getvalue()).decode("utf-8")
                        v_payload = {
                            "model": model_name,
                            "messages": [{
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": "<|image|>\nDescribe the key objects, scenery, doors, and visual style of this adventure game room scene in 2-3 sentences."},
                                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                                ]
                            }],
                            "max_tokens": 120,
                            "temperature": 0.2
                        }
                        v_req = urllib.request.Request(
                            "https://integrate.api.nvidia.com/v1/chat/completions",
                            data=json.dumps(v_payload).encode("utf-8"),
                            headers={"Authorization": f"Bearer {nv_key}", "Content-Type": "application/json"}
                        )
                        with urllib.request.urlopen(v_req, timeout=12) as v_resp:
                            v_data = json.loads(v_resp.read().decode("utf-8"))
                            room_visual_summary = v_data["choices"][0]["message"]["content"].strip()
                except Exception:
                    pass

    if room_visual_summary:
        system_instruction += f"\n\nVisual Inspection of Active Room ('{current_room_id}'):\n{room_visual_summary}"

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_instruction}
    ]

    # Add conversation history
    if history:
        for h in history[-4:]:
            r = "user" if h.get("role") == "user" else "assistant"
            messages.append({"role": r, "content": h.get("text", "")})

    user_text = f"[Active Room in Editor: '{current_room_id}']\n{user_message}" if current_room_id else user_message
    messages.append({"role": "user", "content": user_text})

    tool_logs: list[dict[str, Any]] = []
    final_text = ""

    for _turn in range(8):
        req_payload = {
            "model": model_name,
            "messages": messages,
            "tools": openai_tools,
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "temperature": 0.1
        }
        req_bytes = json.dumps(req_payload).encode("utf-8")
        nv_req = urllib.request.Request(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            data=req_bytes,
            headers={
                "Authorization": f"Bearer {nv_key}",
                "Content-Type": "application/json"
            }
        )
        try:
            with urllib.request.urlopen(nv_req, timeout=35) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as http_err:
            body = http_err.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"NVIDIA API Error {http_err.code}: {body}")

        msg = data["choices"][0]["message"]
        tcalls = msg.get("tool_calls") or []

        if not tcalls:
            content_text = (msg.get("content") or "").strip()
            # Handle text-formatted JSON tool calls from LLaMA 3.2
            if content_text.startswith("{") and ("name" in content_text or "function" in content_text):
                try:
                    cleaned_json = re.sub(r":\s*True\b", ": true", re.sub(r":\s*False\b", ": false", content_text))
                    obj = json.loads(cleaned_json)
                    fn_name = obj.get("name") or obj.get("function")
                    if isinstance(obj, dict) and fn_name in TOOLS_BY_NAME:
                        args_dict = obj.get("parameters") or obj.get("arguments") or obj.get("args") or {}
                        tcalls = [{
                            "id": f"call_inline_{int(time.time()*1000)}",
                            "type": "function",
                            "function": {
                                "name": fn_name,
                                "arguments": json.dumps(args_dict)
                            }
                        }]
                except Exception:
                    pass

            if not tcalls:
                final_text = content_text or "Done!"
                break

        # NVIDIA NIM enforces single tool-call per message
        tc = tcalls[0]
        fname = tc["function"]["name"]
        raw_args = tc["function"].get("arguments") or "{}"
        try:
            fargs = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except Exception:
            fargs = {}

        fn = TOOLS_BY_NAME.get(fname)
        if fn:
            coerced_args = _coerce_tool_args(fn, fargs)
            try:
                fres = fn(**coerced_args)
            except Exception as e:
                fres = {"error": str(e)}
        else:
            fres = {"error": f"Tool '{fname}' not found"}

        tool_logs.append({
            "tool": fname,
            "args": coerced_args if fn else fargs,
            "result": fres
        })

        messages.append({
            "role": "assistant",
            "content": msg.get("content") or None,
            "tool_calls": [tc]
        })
        messages.append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": json.dumps(fres)
        })

    if not final_text:
        final_text = "Completed the requested actions!"

    return {
        "reply": final_text,
        "tool_calls": tool_logs,
        "project": _load_proj(),
        "model_used": f"NVIDIA NIM ({model_name})"
    }


def _run_gemini_agent(
    user_message: str,
    current_room_id: str = "",
    include_room_vision: bool = True,
    history: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Run a multi-step Gemini LLM/VLM Agent with full MCP tool-calling access to AdventureForge."""
    load_env()
    client = genai.Client()
    proj = _load_proj()

    system_instruction = f"""You are the AdventureForge AI Co-Creator & MCP Game Engine Architect (LLM + VLM).
You have direct tool-calling access to inspect and modify the entire point-and-click adventure game project (`data/project.json` and `/assets/*`).
You have {len(TOOLS_LIST)} comprehensive tools covering:
- Project titles, character sprite roles, and launching/stopping the Pygame runtime
- World Map screen nodes, positions, walkable floor polygons, and start room
- Hotspot props, pickups, NPCs, doors, and door locks
- Inventory items and puzzle interaction rules
- Branching Dialog Trees (nodes, speaker lines, player choices, conditions)
- Cutscenes (timeline steps: walk, say, fade, wait, change_room, give_item, set_flag, start_dialog)
- Sprite Studio animations (frames, fps, walk/up/down/idle role mappings, scale)
- Asset Library & Background removal (corner flood fill, global key, auto-trim, and original file restore)
- AI Media Generation, Sound Effects & Search (.env API keys):
  * `search_and_download_sound_effects`: Search and download sound effects and ambient music from FreeSound.org via FREESOUND_API_KEY
  * `search_and_download_images`: Search and download Google Images via SERP_API_KEY with auto-transparency
  * `generate_image_ai`: Generate or acquire game asset graphics with auto background removal and entity linking
  * `spritefusion_generate_pixel_art`: Generate authentic 16/32/64px pixel art using the Sprite Fusion MCP Server (https://www.spritefusion.com/mcp) via SPRITE_FUSION_API_KEY
  * `download_asset_from_url`: Download any web media asset directly into the game project
  * `list_available_media_apis`: Inspect available media generation and search API keys
- Gemini VLM visual inspection (detecting props from room background, Look At/Use lines, room scene inspection)

Guidelines:
1. Always call the appropriate tool(s) to execute the user's intent. You can call multiple tools in sequence!
2. When the user asks for sound effects, audio, or music, use `search_and_download_sound_effects` with Freesound.
3. When the user asks for item icons, props, or background images, use `generate_image_ai` or `search_and_download_images` with SerpApi and auto background removal.
4. When creating items that should appear in the world, use `create_or_update_item` with `place_in_room`.
5. When wiring items to doors, use `link_item_usage`.
6. Keep final responses clear, concise, and report what tools and assets were created."""

    contents: list[Any] = []
    summary_str = json.dumps(get_project_summary(), indent=2)
    context_header = f"Current Active Room in Editor: {current_room_id or proj.get('start_room', 'reception')}\nProject State Summary:\n{summary_str}"
    contents.append(context_header)

    if include_room_vision and current_room_id:
        room = next((r for r in proj.get("rooms", []) if r.get("id") == current_room_id), None)
        if room and room.get("background"):
            try:
                bg_path = _resolve_asset(room["background"])
                if bg_path.exists():
                    bg_img = Image.open(bg_path).convert("RGB").resize((1280, 720))
                    contents.append(bg_img)
            except Exception:
                pass

    if history:
        for h in history[-6:]:
            role_label = "User" if h.get("role") == "user" else "Assistant"
            contents.append(f"{role_label}: {h.get('text', '')}")

    contents.append(f"User Request: {user_message}")

    tool_logs: list[dict[str, Any]] = []
    chat_contents = list(contents)
    final_text = ""

    try:
        for _step in range(10):
            response = None
            last_err = None
            for model_candidate in ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"):
                try:
                    response = client.models.generate_content(
                        model=model_candidate,
                        contents=chat_contents,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            tools=TOOLS_LIST,
                            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                            temperature=0.2,
                        )
                    )
                    if response:
                        break
                except Exception as model_err:
                    last_err = model_err
                    err_str = str(model_err)
                    if "503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str:
                        continue
                    raise

            if not response:
                if last_err:
                    raise last_err
                break

            cand = response.candidates[0] if response.candidates else None
            if not cand or not cand.content:
                break

            chat_contents.append(cand.content)

            fn_calls = [p.function_call for p in (cand.content.parts or []) if p.function_call]
            if not fn_calls:
                text_parts = [p.text for p in (cand.content.parts or []) if getattr(p, "text", None)]
                final_text = "\n".join(text_parts).strip() or getattr(response, "text", "") or "Done!"
                break

            fn_response_parts = []
            for fc in fn_calls:
                fn_name = fc.name
                fn_args = dict(fc.args) if fc.args else {}
                fn_obj = TOOLS_BY_NAME.get(fn_name)
                if fn_obj:
                    coerced_args = _coerce_tool_args(fn_obj, fn_args)
                    try:
                        res = fn_obj(**coerced_args)
                    except Exception as e:
                        res = {"error": str(e)}
                else:
                    res = {"error": f"Unknown tool: {fn_name}"}

                tool_logs.append({
                    "tool": fn_name,
                    "args": coerced_args if fn_obj else fn_args,
                    "result": res
                })
                fn_response_parts.append(
                    types.Part.from_function_response(
                        name=fn_name,
                        response={"result": res}
                    )
                )

            chat_contents.append(types.Content(role="tool", parts=fn_response_parts))
    except Exception as e:
        return {
            "reply": f"Agent notification: {e}",
            "tool_calls": tool_logs,
            "project": _load_proj()
        }

    if not final_text:
        final_text = "Completed the requested actions!"

    return {
        "reply": final_text,
        "tool_calls": tool_logs,
        "project": _load_proj(),
        "model_used": "Gemini (gemini-2.5-flash)"
    }


def run_agent_instruction(
    user_message: str,
    current_room_id: str = "",
    include_room_vision: bool = True,
    history: list[dict[str, Any]] | None = None,
    preferred_model: str = ""
) -> dict[str, Any]:
    """Run autonomous AI Agent with full MCP tool-calling access to AdventureForge.
    Prioritizes NVIDIA NIM models (meta/llama-3.2-11b-vision-instruct / meta/llama-3.2-90b-vision-instruct)
    when NVIDIA_API_KEY is configured in .env."""
    load_env()
    keys = _get_api_keys()

    nv_key = keys.get("nvidia")
    # If NVIDIA API key is available and Gemini is not specifically forced
    if nv_key and ("gemini" not in preferred_model.lower()):
        nv_model = preferred_model if ("llama" in preferred_model or "nvidia" in preferred_model) else os.getenv("NVIDIA_MODEL", "meta/llama-3.2-11b-vision-instruct")
        try:
            return _run_nvidia_agent(
                user_message=user_message,
                current_room_id=current_room_id,
                include_room_vision=include_room_vision,
                history=history,
                model_name=nv_model
            )
        except Exception as nv_err:
            print(f"NVIDIA Agent error, attempting fallback: {nv_err}")
            if not keys.get("gemini"):
                return {
                    "reply": f"NVIDIA Agent error: {nv_err}",
                    "tool_calls": [],
                    "project": _load_proj()
                }

    # Fallback / Gemini Agent
    return _run_gemini_agent(
        user_message=user_message,
        current_room_id=current_room_id,
        include_room_vision=include_room_vision,
        history=history
    )
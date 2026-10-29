#!/usr/bin/env python3
"""
AdventureForge — Interactive AI CLI Agent (LLM + VLM + MCP Tools)
Run interactively:
  python3 forge_cli.py
Or one-shot from bash:
  python3 forge_cli.py "Create a brass key item in reception and make it unlock the computer exit"
"""

import sys
import json
from tools import TOOLS_LIST, get_project_summary, run_agent_instruction


def print_tool_calls(tool_calls: list[dict]):
    for idx, tc in enumerate(tool_calls, 1):
        args_str = ", ".join(f"{k}={repr(v)}" for k, v in (tc.get("args") or {}).items())
        print(f"  \033[93m⚡ [MCP Tool #{idx}] {tc['tool']}({args_str})\033[0m")
        res = tc.get("result", {})
        status = res.get("status") or ("error" if "error" in res else "ok")
        print(f"     \033[90m↳ status: {status}\033[0m")


def main():
    if len(sys.argv) > 1:
        arg1 = sys.argv[1]
        if arg1 in ("--summary", "-s", "/summary"):
            print(json.dumps(get_project_summary(), indent=2))
            return
        if arg1 in ("--tools", "-t", "/tools", "--list"):
            print(f"AdventureForge MCP Tools ({len(TOOLS_LIST)} registered):")
            for fn in TOOLS_LIST:
                doc = (fn.__doc__ or "").strip().split("\n")[0]
                print(f" - \033[93m{fn.__name__}\033[0m: {doc}")
            return
        if arg1 in ("--help", "-h"):
            print("Usage: python3 forge_cli.py [\"prompt\" | --summary | --tools]")
            return

        prompt = " ".join(sys.argv[1:])
        print(f"\033[96m🤖 AdventureForge Agent executing:\033[0m {prompt}")
        out = run_agent_instruction(prompt)
        print_tool_calls(out.get("tool_calls", []))
        print(f"\n\033[92m{out.get('reply', '')}\033[0m")
        return

    print("\033[95m================================================================\033[0m")
    print("\033[95m🕹️  AdventureForge CLI + MCP Agent (LLM + VLM Vision Enabled)\033[0m")
    print("Type what you want to build or change, or use:")
    print(f"  \033[96m/tools\033[0m   — List all {len(TOOLS_LIST)} MCP tools")
    print("  \033[96m/summary\033[0m — Print current project summary")
    print("  \033[96m/quit\033[0m    — Exit CLI")
    print("\033[95m================================================================\033[0m")

    history = []
    while True:
        try:
            user_in = input("\n\033[94mforge>\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
        if not user_in:
            continue
        if user_in in ("/quit", "/exit", "exit", "quit"):
            break
        if user_in == "/tools":
            for fn in TOOLS_LIST:
                print(f" - \033[93m{fn.__name__}\033[0m: {(fn.__doc__ or '').strip()}")
            continue
        if user_in == "/summary":
            print(json.dumps(get_project_summary(), indent=2))
            continue

        out = run_agent_instruction(user_in, history=history)
        print_tool_calls(out.get("tool_calls", []))
        print(f"\n\033[92m🤖 {out.get('reply', '')}\033[0m")
        history.append({"role": "user", "text": user_in})
        history.append({"role": "assistant", "text": out.get("reply", "")})


if __name__ == "__main__":
    main()

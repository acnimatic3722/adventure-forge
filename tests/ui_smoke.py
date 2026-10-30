"""Headless smoke test for the AdventureForge editor UI.

Drives the real page in Chrome and exercises the three new subsystems:
the collision tool, the characters roster and the events tab.

The server runs against a throwaway data directory so the live
``data/project.json`` is never touched.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PORT = 8799
BASE = f"http://127.0.0.1:{PORT}"

# Find a Chrome/Chromium build. Playwright's own download is not required —
# any system browser works, and GitHub's ubuntu runners ship one.
CHROME_CANDIDATES = (
    "/usr/bin/google-chrome-stable",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
)


def find_chrome() -> str | None:
    for path in CHROME_CANDIDATES:
        if Path(path).exists():
            return path
    return None

# Isolate the test from the real project.
TMP_DATA = Path(tempfile.mkdtemp(prefix="af-ui-smoke-"))
shutil.copytree(ROOT / "data" / "assets", TMP_DATA / "assets", dirs_exist_ok=True)
shutil.copy2(ROOT / "data" / "project.json", TMP_DATA / "project.json")

env = os.environ.copy()
env["ADVENTURE_FORGE_DATA_DIR"] = str(TMP_DATA)

server = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(PORT)],
    cwd=str(ROOT),
    env=env,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

failures = []
console_errors = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}{(' — ' + str(detail)) if detail and not cond else ''}")
    if not cond:
        failures.append(f"{name}: {detail}")


try:
    chrome = find_chrome()
    if not chrome:
        print("SKIP: no Chrome/Chromium found. Install Chrome to run this suite.")
        sys.exit(0)

    time.sleep(5)
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=chrome,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(f"PAGEERROR: {e}"))
        page.on("response", lambda r: console_errors.append(f"HTTP {r.status}: {r.url}")
                if r.status >= 400 else None)

        print("\n== Loading editor ==")
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(1500)

        # ---------------------------------------------------------- collisions
        print("\n== Collision tool ==")
        page.click(".tab-btn >> text=Room & Hotspots")
        page.wait_for_timeout(700)
        page.click("#tool-collide")
        check("collision tool activates", page.get_attribute("#tool-collide", "class") == "btn-primary")
        hint = page.inner_text("#toolHelpText")
        check("collision hint shown", "Blocked Area" in hint, hint[:80])

        # Draw a blocked area by dragging on the canvas.
        canvas = page.query_selector("#roomCanvas")
        box = canvas.bounding_box()
        page.mouse.move(box["x"] + 120, box["y"] + 120)
        page.mouse.down()
        page.mouse.move(box["x"] + 260, box["y"] + 200, steps=8)
        page.mouse.up()
        page.wait_for_timeout(400)

        count = page.inner_text("#colliderCountBadge")
        check("collider created by drag", count.strip() == "1", f"badge={count!r}")

        colliders = page.evaluate("() => (getSelectedRoom().colliders || []).length")
        check("collider stored on room", colliders == 1, f"n={colliders}")

        geom = page.evaluate(
            "() => { const c = (getSelectedRoom().colliders||[])[0];"
            " return c ? {id:c.id,type:c.type,x:c.x,y:c.y,w:c.w,h:c.h} : null; }"
        )
        check("collider has sane geometry",
              geom and geom["type"] == "rect" and geom["w"] > 20 and geom["h"] > 20, geom)
        check("collider got an id", bool(geom and geom.get("id")), geom)

        # The sidebar list should show it.
        list_text = page.inner_text("#colliderList")
        check("collider listed in sidebar", "Box 1" in list_text, list_text[:80])

        # Undo should remove it.
        page.keyboard.press("Control+z")
        page.wait_for_timeout(400)
        after_undo = page.evaluate("() => (getSelectedRoom().colliders || []).length")
        check("undo removes the collider", after_undo == 0, f"n={after_undo}")

        # Redo brings it back.
        page.keyboard.press("Control+y")
        page.wait_for_timeout(400)
        after_redo = page.evaluate("() => (getSelectedRoom().colliders || []).length")
        check("redo restores the collider", after_redo == 1, f"n={after_redo}")

        # Select + move it.
        page.mouse.move(box["x"] + 180, box["y"] + 150)
        page.mouse.down()
        page.mouse.move(box["x"] + 230, box["y"] + 190, steps=6)
        page.mouse.up()
        page.wait_for_timeout(300)
        moved = page.evaluate("() => { const c=(getSelectedRoom().colliders||[])[0]; return c?{x:c.x,y:c.y}:null; }")
        check("collider can be moved", moved and moved["x"] != geom["x"], f"{geom} -> {moved}")

        # Clear all.
        page.click("button[onclick='clearRoomColliders()']")
        page.wait_for_timeout(300)
        cleared = page.evaluate("() => (getSelectedRoom().colliders || []).length")
        check("clear walls empties the list", cleared == 0, f"n={cleared}")

        # ------------------------------------------------------------ characters
        print("\n== Characters ==")
        page.click(".tab-btn >> text=Sprite & Animation")
        page.wait_for_timeout(700)
        page.click("button[onclick='newCharacter()']")
        page.wait_for_timeout(400)
        nchars = page.evaluate("() => Object.keys(project.characters || {}).length")
        check("character created", nchars >= 1, f"n={nchars}")

        page.fill("#charName", "Test Hero")
        page.dispatch_event("#charName", "input")
        page.wait_for_timeout(300)
        named = page.evaluate("() => Object.values(project.characters||{}).some(c => c.name === 'Test Hero')")
        check("character name saves", named)

        page.click("#charSetPlayer")
        page.wait_for_timeout(400)
        pcid = page.evaluate("() => project.player_character")
        check("character set as player", bool(pcid), pcid)

        # ------------------------------------------------------- events & triggers
        print("\n== Events & Triggers ==")
        page.click(".tab-btn >> text=Events & Triggers")
        page.wait_for_timeout(700)
        check("events tab visible", page.is_visible("#tab-events"))

        page.click("button[onclick='newEvent()']")
        page.wait_for_timeout(400)
        nevents = page.evaluate("() => (project.events || []).length")
        check("event created", nevents >= 1, f"n={nevents}")

        page.fill("#eventName", "Intro on entry")
        page.dispatch_event("#eventName", "input")
        page.select_option("#eventTriggerType", "on_enter_room")
        page.fill("#eventTriggerTarget", "reception")
        page.dispatch_event("#eventTriggerTarget", "input")
        page.wait_for_timeout(300)
        trig = page.evaluate("() => { const e=project.events[project.events.length-1]; return e ? {name:e.name,trigger:e.trigger} : null; }")
        check("event trigger saves",
              trig and trig["name"] == "Intro on entry" and trig["trigger"]["type"] == "on_enter_room",
              trig)
        check("event target saves", trig and trig["trigger"]["target"] == "reception", trig)

        page.select_option("#eventActionType", "set_flag")
        page.click("button[onclick='addEventAction()']")
        page.wait_for_timeout(400)
        actions = page.evaluate("() => { const e=project.events[project.events.length-1]; return e ? e.actions : []; }")
        check("action added", len(actions) == 1 and actions[0]["type"] == "set_flag", actions)

        # Edit the action's value through the inline input.
        page.fill("#eventActionList input", "intro_seen")
        page.dispatch_event("#eventActionList input", "change")
        page.wait_for_timeout(400)
        val = page.evaluate("() => { const e=project.events[project.events.length-1]; return e.actions[0].value; }")
        check("action value saves", val == "intro_seen", val)

        # The list should show the event.
        ev_list = page.inner_text("#eventList")
        check("event listed", "Intro on entry" in ev_list, ev_list[:80])

        # ------------------------------------------------------- round-trip save
        print("\n== Save round-trip ==")
        page.evaluate("() => saveProject()")
        page.wait_for_timeout(1200)
        saved = page.evaluate("() => fetch('/api/project').then(r => r.json())")
        check("events persisted to project.json", len(saved.get("events") or []) >= 1,
              saved.get("events"))
        check("characters persisted to project.json", len(saved.get("characters") or {}) >= 1,
              list((saved.get("characters") or {}).keys()))

        browser.close()

    print("\n== Console errors ==")
    real_errors = [e for e in console_errors if "favicon" not in e.lower()]
    check("no console errors", not real_errors, real_errors[:5])

finally:
    server.terminate()
    try:
        server.wait(timeout=5)
    except Exception:
        server.kill()
    shutil.rmtree(TMP_DATA, ignore_errors=True)

print("\n" + "=" * 60)
if failures:
    print(f"FAILED ({len(failures)}):")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("ALL UI CHECKS PASSED")

#!/usr/bin/env python3
"""
AdventureForge — Collision Geometry

Pure geometry helpers for the room collision system. No Pygame, no I/O, no
global state — so the rules can be unit-tested without spinning up a window.

A room may carry a ``colliders`` list. Each collider is either::

    {"id": "col_1", "type": "rect", "x": 100, "y": 200, "w": 300, "h": 40}
    {"id": "col_2", "type": "poly", "points": [{"x": 0, "y": 0}, ...]}

Characters are treated as a circle of ``radius`` centred on their *feet*
point (the engine draws sprites bottom-centre on that point), so a character
can stand right up against a wall without their head poking through it.

Movement resolution slides along obstacles: if a straight step is blocked,
the horizontal component is tried on its own, then the vertical component.
That is what lets you walk diagonally into a wall and still slide along it
instead of stopping dead.
"""
from __future__ import annotations

import math
from typing import Any, Iterable

# Default collision radius for a character, in logical pixels.
DEFAULT_COLLISION_RADIUS = 14.0

# How close (in pixels) a character must be to its walk target before the
# interaction is considered "arrived" when the target itself is unreachable
# (e.g. the hotspot sits inside a collider).
BLOCKED_ARRIVE_DISTANCE = 56.0


# ============================================================================
# Basic polygon maths
# ============================================================================

def point_in_poly(x: float, y: float, poly: list[dict]) -> bool:
    """Ray-casting point-in-polygon test.

    A polygon with fewer than three points is treated as "contains
    everything" — the caller is responsible for validating the shape.
    """
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


def distance_to_segment(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> float:
    """Shortest distance from point ``(px, py)`` to the segment ``a-b``."""
    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def distance_point_to_poly(x: float, y: float, points: list[tuple[float, float]]) -> float:
    """Shortest distance from a point to a polygon's outline (0 if inside)."""
    if not points:
        return float("inf")
    if len(points) == 1:
        return math.hypot(x - points[0][0], y - points[0][1])
    best = float("inf")
    n = len(points)
    for i in range(n):
        ax, ay = points[i]
        bx, by = points[(i + 1) % n]
        best = min(best, distance_to_segment(x, y, ax, ay, bx, by))
    return best


# ============================================================================
# Collider helpers
# ============================================================================

def collider_points(collider: dict[str, Any]) -> list[tuple[float, float]]:
    """Return a collider's outline as a list of ``(x, y)`` tuples.

    Rectangles are converted to their four corners so both collider types can
    share the same code paths.
    """
    if not isinstance(collider, dict):
        return []
    ctype = (collider.get("type") or "rect").lower()

    if ctype == "poly":
        raw = collider.get("points") or []
        pts: list[tuple[float, float]] = []
        for pt in raw:
            if isinstance(pt, dict) and "x" in pt and "y" in pt:
                pts.append((float(pt["x"]), float(pt["y"])))
        return pts

    try:
        x = float(collider.get("x", 0))
        y = float(collider.get("y", 0))
        w = float(collider.get("w", 0))
        h = float(collider.get("h", 0))
    except (TypeError, ValueError):
        return []
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def collider_contains_point(x: float, y: float, collider: dict[str, Any]) -> bool:
    """True when the *point* lies inside the collider's area."""
    if not isinstance(collider, dict):
        return False
    ctype = (collider.get("type") or "rect").lower()

    if ctype == "poly":
        points = collider_points(collider)
        if len(points) < 3:
            return False
        return point_in_poly(x, y, [{"x": px, "y": py} for px, py in points])

    try:
        rx = float(collider.get("x", 0))
        ry = float(collider.get("y", 0))
        rw = float(collider.get("w", 0))
        rh = float(collider.get("h", 0))
    except (TypeError, ValueError):
        return False
    if rw <= 0 or rh <= 0:
        return False
    return rx <= x <= rx + rw and ry <= y <= ry + rh


def collider_blocks(x: float, y: float, radius: float, collider: dict[str, Any]) -> bool:
    """True when a circle of ``radius`` at ``(x, y)`` overlaps the collider."""
    if not isinstance(collider, dict):
        return False
    ctype = (collider.get("type") or "rect").lower()
    radius = max(0.0, float(radius))

    if ctype == "poly":
        points = collider_points(collider)
        if len(points) < 3:
            return False
        if point_in_poly(x, y, [{"x": px, "y": py} for px, py in points]):
            return True
        return distance_point_to_poly(x, y, points) <= radius

    try:
        rx = float(collider.get("x", 0))
        ry = float(collider.get("y", 0))
        rw = float(collider.get("w", 0))
        rh = float(collider.get("h", 0))
    except (TypeError, ValueError):
        return False
    if rw <= 0 or rh <= 0:
        return False

    # Closest point on the rectangle to the circle centre.
    cx = max(rx, min(x, rx + rw))
    cy = max(ry, min(y, ry + rh))
    return math.hypot(x - cx, y - cy) <= radius


def point_blocked(x: float, y: float, radius: float, colliders: Iterable[dict] | None) -> bool:
    """True when any collider in ``colliders`` blocks the circle at ``(x, y)``."""
    for collider in colliders or []:
        if collider_blocks(x, y, radius, collider):
            return True
    return False


def resolve_movement(
    nx: float,
    ny: float,
    ox: float,
    oy: float,
    radius: float,
    colliders: Iterable[dict] | None,
) -> tuple[float, float]:
    """Resolve a movement step, sliding along obstacles.

    ``(nx, ny)`` is the desired new position, ``(ox, oy)`` the current one.
    The returned position is the furthest reachable point:

    1. the full step, if nothing blocks it;
    2. otherwise the horizontal component alone (slide along a wall);
    3. otherwise the vertical component alone;
    4. otherwise the original position (fully boxed in).
    """
    colliders = list(colliders or [])
    if not colliders:
        return nx, ny

    if not point_blocked(nx, ny, radius, colliders):
        return nx, ny

    # Slide horizontally.
    if not point_blocked(nx, oy, radius, colliders):
        return nx, oy

    # Slide vertically.
    if not point_blocked(ox, ny, radius, colliders):
        return ox, ny

    return ox, oy


def nearest_free_point(
    x: float,
    y: float,
    radius: float,
    colliders: Iterable[dict] | None,
    max_radius: int = 160,
    step: int = 8,
) -> tuple[float, float]:
    """Find the closest unblocked position to ``(x, y)``.

    Used to rescue a character that has been placed inside geometry (a bad
    spawn point, a resized wall) by pushing them out to the nearest free
    spot. Returns the original point if nothing free is found.
    """
    colliders = list(colliders or [])
    if not point_blocked(x, y, radius, colliders):
        return x, y

    for r in range(step, max_radius + 1, step):
        for angle in range(0, 360, 15):
            rad = math.radians(angle)
            tx = x + math.cos(rad) * r
            ty = y + math.sin(rad) * r
            if not point_blocked(tx, ty, radius, colliders):
                return tx, ty
    return x, y


def normalize_collider(collider: dict[str, Any]) -> dict[str, Any]:
    """Coerce a collider dict into the canonical shape.

    Returns a dict with an ``id`` and a ``type`` of ``rect`` or ``poly``.
    Rectangles keep ``x/y/w/h``; polygons keep ``points``.
    """
    if not isinstance(collider, dict):
        raise ValueError("Collider must be an object")

    ctype = str(collider.get("type") or "rect").lower()
    if ctype not in ("rect", "poly"):
        raise ValueError(f"Unsupported collider type: {ctype!r} (use 'rect' or 'poly')")

    out: dict[str, Any] = {
        "id": str(collider.get("id") or "").strip(),
        "type": ctype,
    }

    if ctype == "rect":
        try:
            x = float(collider.get("x", 0))
            y = float(collider.get("y", 0))
            w = float(collider.get("w", 0))
            h = float(collider.get("h", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid rectangle collider: {exc}") from exc
        out["x"] = round(x, 2)
        out["y"] = round(y, 2)
        out["w"] = round(max(0.0, w), 2)
        out["h"] = round(max(0.0, h), 2)
    else:
        raw = collider.get("points") or []
        points: list[dict[str, float]] = []
        for pt in raw:
            if isinstance(pt, dict) and "x" in pt and "y" in pt:
                points.append({"x": round(float(pt["x"]), 2), "y": round(float(pt["y"]), 2)})
        if len(points) < 3:
            raise ValueError("A polygon collider needs at least 3 points")
        out["points"] = points

    return out

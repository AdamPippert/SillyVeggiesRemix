import math
import random

from . import content as game_content

WORLD_MAP = game_content.WORLD_MAP
GATE_SEGMENTS = game_content.GATE_SEGMENTS
CURRENT_GATE_LOCKS = list(game_content.CURRENT_GATE_LOCKS)


def sync_gate_locks(unlocked_keys: int):
    CURRENT_GATE_LOCKS[:] = [idx >= unlocked_keys for idx in range(len(GATE_SEGMENTS))]


def gate_blocked(x: float, y: float) -> bool:
    for idx, g in enumerate(GATE_SEGMENTS):
        if idx < len(CURRENT_GATE_LOCKS) and CURRENT_GATE_LOCKS[idx]:
            if abs(x - g["x"]) < 0.22 and g["y1"] <= y <= g["y2"]:
                return True
    return False


def is_wall(x: float, y: float) -> bool:
    if y < 0 or y >= len(WORLD_MAP) or x < 0 or x >= len(WORLD_MAP[0]):
        return True
    if WORLD_MAP[int(y)][int(x)] == "#":
        return True
    return gate_blocked(x, y)


def has_line_of_sight(x1: float, y1: float, x2: float, y2: float) -> bool:
    dx = x2 - x1
    dy = y2 - y1
    dist = math.hypot(dx, dy)
    if dist <= 0.0001:
        return True
    steps = max(2, int(dist * 18))
    for i in range(1, steps):
        t = i / steps
        x = x1 + dx * t
        y = y1 + dy * t
        if is_wall(x, y):
            return False
    return True


def random_open_position(min_dist_from_player=0.0, px=0.0, py=0.0, bounds=None):
    open_tiles = []
    bx1 = by1 = bx2 = by2 = None
    if bounds is not None:
        bx1, by1, bx2, by2 = bounds

    for y, row in enumerate(WORLD_MAP):
        for x, ch in enumerate(row):
            if ch == "#":
                continue
            cx = x + 0.5
            cy = y + 0.5
            if bounds is not None and not (bx1 <= cx <= bx2 and by1 <= cy <= by2):
                continue
            if gate_blocked(cx, cy):
                continue
            if math.hypot(cx - px, cy - py) >= min_dist_from_player:
                open_tiles.append((cx, cy))
    if not open_tiles:
        return 1.5, 1.5
    return random.choice(open_tiles)

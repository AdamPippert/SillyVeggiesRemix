import argparse
import base64
import json
import math
import pickle
import random
import sys
import time
from array import array
from pathlib import Path

import pygame

WIDTH, HEIGHT = 1280, 720
HALF_H = HEIGHT // 2
FOV = math.pi / 3
HALF_FOV = FOV / 2
NUM_RAYS = 240
MAX_DEPTH = 20
SCALE = WIDTH // NUM_RAYS

PLAYER_START = (2.5, 2.5, 0.0)
MAX_HP = 100
ROPE_BASE_PULL = 2.6
ROPE_BOOST_MULT = 1.75
ROPE_BOOST_DURATION = 6.0
BOSS_WAVE_INTERVAL = 5

WORLD_MAP = [
    "################",
    "#......T.......#",
    "#..####....P...#",
    "#..#..#........#",
    "#..#..####..G..#",
    "#..............#",
    "#..R....####...#",
    "#.......#..#...#",
    "#..####.#..#...#",
    "#......P....V..#",
    "################",
]

ROOM_WAVES_REQUIRED = 2
ROOMS = [
    {"name": "Pallet Yard", "bounds": (1.2, 1.2, 5.2, 9.6), "spawn": (2.5, 2.5, 0.0)},
    {"name": "Tractor Bay", "bounds": (6.0, 1.2, 10.0, 9.6), "spawn": (7.2, 2.5, 0.0)},
    {"name": "Tool Depot", "bounds": (11.0, 1.2, 14.6, 9.6), "spawn": (12.4, 2.5, 0.0)},
]
GATE_SEGMENTS = [
    {"x": 5.5, "y1": 1.15, "y2": 9.85},
    {"x": 10.5, "y1": 1.15, "y2": 9.85},
]
CURRENT_GATE_LOCKS = [True, True]
SAVE_VERSION = 1
DEFAULT_SAVE_FILE = "run_save.json"


class AudioBank:
    def __init__(self):
        self.enabled = False
        self.sounds = {}

    def init(self):
        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
            self.sounds["lasso_fire"] = self._tone(540, 45, 0.25)
            self.sounds["lasso_latch"] = self._tone(760, 65, 0.2)
            self.sounds["capture"] = self._tone(980, 95, 0.23)
            self.sounds["player_hit"] = self._tone(170, 110, 0.3)
            self.sounds["spit"] = self._tone(260, 60, 0.2)
            self.sounds["pickup"] = self._tone(840, 70, 0.2)
            self.enabled = True
        except pygame.error:
            self.enabled = False

    def _tone(self, freq_hz: float, dur_ms: int, volume: float):
        sample_rate = 22050
        samples = int(sample_rate * dur_ms / 1000)
        buf = array("h")
        for i in range(samples):
            t = i / sample_rate
            env = 1.0 - (i / samples)
            val = int(32767 * volume * env * math.sin(2 * math.pi * freq_hz * t))
            buf.append(val)
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def play(self, key: str):
        if self.enabled and key in self.sounds:
            self.sounds[key].play()


def sync_gate_locks(unlocked_keys: int):
    global CURRENT_GATE_LOCKS
    CURRENT_GATE_LOCKS = [idx >= unlocked_keys for idx in range(len(GATE_SEGMENTS))]


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


def draw_background(screen):
    # Sky gradient + subtle scanlines
    for y in range(HALF_H):
        k = y / HALF_H
        r = int(55 + 35 * (1 - k))
        g = int(95 + 45 * (1 - k))
        b = int(145 + 35 * (1 - k))
        pygame.draw.line(screen, (r, g, b), (0, y), (WIDTH, y))

    # Dirt floor gradient with horizontal bands to fake texture
    for y in range(HALF_H, HEIGHT):
        k = (y - HALF_H) / HALF_H
        r = int(95 - 30 * k)
        g = int(65 - 25 * k)
        b = int(40 - 20 * k)
        pygame.draw.line(screen, (r, g, b), (0, y), (WIDTH, y))
        if y % 22 == 0:
            pygame.draw.line(screen, (70, 46, 30), (0, y), (WIDTH, y))


def cast_rays(screen, px, py, angle):
    start_angle = angle - HALF_FOV
    for ray in range(NUM_RAYS):
        ray_angle = start_angle + (FOV / NUM_RAYS) * ray
        sin_a = math.sin(ray_angle)
        cos_a = math.cos(ray_angle)

        depth = 0.01
        while depth < MAX_DEPTH:
            x = px + cos_a * depth
            y = py + sin_a * depth
            if is_wall(x, y):
                break
            depth += 0.02

        depth *= math.cos(angle - ray_angle)
        wall_h = min(int(HEIGHT / (depth + 0.0001)), HEIGHT)

        shade = max(30, 255 - int(depth * 35))
        wood_variation = (ray % 7) * 3
        color = (
            max(20, shade // 2 + wood_variation),
            max(20, shade // 2 - 8 + wood_variation),
            max(15, shade // 3 - 10),
        )
        wall_rect = (ray * SCALE, HALF_H - wall_h // 2, SCALE + 1, wall_h)
        pygame.draw.rect(screen, color, wall_rect)
        if ray % 3 == 0:
            pygame.draw.line(
                screen,
                (max(0, color[0] - 25), max(0, color[1] - 25), max(0, color[2] - 20)),
                (ray * SCALE, HALF_H - wall_h // 2),
                (ray * SCALE, HALF_H + wall_h // 2),
            )


def project_sprite(px, py, angle, sx, sy):
    dx = sx - px
    dy = sy - py
    dist = math.hypot(dx, dy)
    if dist < 0.05:
        return None

    target_angle = math.atan2(dy, dx)
    delta = (target_angle - angle + math.pi) % (2 * math.pi) - math.pi
    if abs(delta) > HALF_FOV * 1.25:
        return None

    screen_x = int((delta + HALF_FOV) / FOV * WIDTH)
    size = max(8, int(560 / (dist + 0.2)))
    screen_y = HALF_H + int(50 / (dist + 0.1))
    return screen_x, screen_y, size, dist


def spawn_veggies(wave: int, px: float, py: float, bounds=None):
    wave = max(1, wave)

    # Boss cadence: every Nth wave
    if wave % BOSS_WAVE_INTERVAL == 0:
        bx, by = random_open_position(4.0, px, py, bounds)
        boss = {
            "kind": "boss",
            "x": bx,
            "y": by,
            "vx": random.choice([-1.0, 1.0]),
            "vy": random.choice([-1.0, 1.0]),
            "wander_t": 1.0,
            "captured": False,
            "latched": False,
            "attack_cd": 1.0,
            "weakpoints": 3,
            "exposed": True,
            "phase_timer": 3.5,
        }

        support_count = min(4, 1 + wave // BOSS_WAVE_INTERVAL)
        support = []
        for i in range(support_count):
            sx, sy = random_open_position(3.0, px, py, bounds)
            kind = "spitter" if i % 2 == 0 else "carrot"
            support.append(
                {
                    "kind": kind,
                    "x": sx,
                    "y": sy,
                    "vx": random.choice([-1.0, 1.0]),
                    "vy": random.choice([-1.0, 1.0]),
                    "wander_t": random.uniform(0.8, 1.8),
                    "captured": False,
                    "latched": False,
                    "attack_cd": random.uniform(0.4, 1.0),
                }
            )
        return [boss, *support]

    total = min(10, 2 + wave)
    spitters = min(total - 1, max(1, wave // 2))
    carrots = total - spitters

    veggies = []
    for _ in range(carrots):
        x, y = random_open_position(3.0, px, py, bounds)
        veggies.append(
            {
                "kind": "carrot",
                "x": x,
                "y": y,
                "vx": random.choice([-1.0, 1.0]),
                "vy": random.choice([-1.0, 1.0]),
                "wander_t": random.uniform(0.8, 1.6),
                "captured": False,
                "latched": False,
                "attack_cd": random.uniform(0.3, 1.0),
            }
        )

    for _ in range(spitters):
        x, y = random_open_position(3.0, px, py, bounds)
        veggies.append(
            {
                "kind": "spitter",
                "x": x,
                "y": y,
                "vx": random.choice([-1.0, 1.0]),
                "vy": random.choice([-1.0, 1.0]),
                "wander_t": random.uniform(0.8, 1.8),
                "captured": False,
                "latched": False,
                "attack_cd": random.uniform(0.5, 1.2),
            }
        )

    return veggies


def draw_veggies(screen, px, py, angle, veggies):
    projected = []
    for idx, v in enumerate(veggies):
        if v["captured"]:
            continue
        p = project_sprite(px, py, angle, v["x"], v["y"])
        if p is None:
            continue
        screen_x, screen_y, size, dist = p
        projected.append((dist, idx, screen_x, screen_y, size))

    projected.sort(reverse=True)
    for _, idx, screen_x, screen_y, size in projected:
        v = veggies[idx]
        if v["kind"] == "carrot":
            col = (235, 120, 40)
            accent = (255, 190, 90)
        elif v["kind"] == "spitter":
            col = (115, 170, 70)
            accent = (180, 230, 130)
        else:
            if v.get("exposed", False):
                col = (165, 95, 205)
                accent = (245, 190, 255)
            else:
                col = (95, 70, 130)
                accent = (150, 130, 180)

        if v["kind"] == "boss":
            size = int(size * 1.6)

        body = pygame.Rect(screen_x - size // 2, screen_y - size // 2, size, size)
        pygame.draw.rect(screen, col, body)
        pygame.draw.rect(screen, (35, 35, 35), body, 2)

        cap = pygame.Rect(screen_x - size // 4, screen_y - size // 2 - 4, size // 2, 5)
        pygame.draw.rect(screen, accent, cap)

        if v["kind"] == "boss":
            pips = max(0, int(v.get("weakpoints", 0)))
            for p in range(pips):
                px = screen_x - (pips * 7) // 2 + p * 7
                py = screen_y - size // 2 - 12
                pygame.draw.circle(screen, (255, 220, 255), (px, py), 3)

        if v["attack_cd"] < 0.15:
            blink = pygame.Rect(screen_x - size // 4, screen_y - size // 2 - 10, size // 2, 4)
            pygame.draw.rect(screen, (255, 50, 50), blink)


def draw_pickups(screen, px, py, angle, pickups):
    projected = []
    for i, p in enumerate(pickups):
        proj = project_sprite(px, py, angle, p["x"], p["y"])
        if proj is None:
            continue
        sx, sy, size, dist = proj
        projected.append((dist, i, sx, sy, max(5, size // 6)))

    projected.sort(reverse=True)
    for _, i, sx, sy, rad in projected:
        p = pickups[i]
        if p["kind"] == "health":
            color, core = (255, 70, 70), (250, 235, 235)
        elif p["kind"] == "rope":
            color, core = (80, 180, 255), (220, 240, 255)
        else:
            color, core = (245, 210, 80), (255, 245, 190)
        pygame.draw.circle(screen, color, (sx, sy), rad)
        pygame.draw.circle(screen, core, (sx, sy), max(2, rad // 2))


def draw_gates(screen, px, py, angle):
    for idx, g in enumerate(GATE_SEGMENTS):
        if idx >= len(CURRENT_GATE_LOCKS) or not CURRENT_GATE_LOCKS[idx]:
            continue
        steps = 6
        for s in range(steps):
            gy = g["y1"] + (g["y2"] - g["y1"]) * (s / (steps - 1))
            proj = project_sprite(px, py, angle, g["x"], gy)
            if proj is None:
                continue
            sx, sy, size, _ = proj
            w = max(6, size // 7)
            h = max(10, size // 2)
            pygame.draw.rect(screen, (150, 110, 70), (sx - w // 2, sy - h // 2, w, h))


def draw_hazards(screen, px, py, angle, hazards):
    projected = []
    for i, h in enumerate(hazards):
        proj = project_sprite(px, py, angle, h["x"], h["y"])
        if proj is None:
            continue
        sx, sy, size, dist = proj
        projected.append((dist, i, sx, sy, max(5, size // 6)))

    projected.sort(reverse=True)
    for _, i, sx, sy, rad in projected:
        h = hazards[i]
        if h["kind"] == "tractor_sweep":
            pygame.draw.rect(screen, (210, 160, 70), (sx - rad, sy - rad, rad * 2, rad * 2))
        elif h["kind"] == "pallet_crusher":
            pulse = h.get("pulse_radius", 0.5)
            rr = max(rad, int(rad + pulse * 5))
            pygame.draw.circle(screen, (170, 120, 70), (sx, sy), rr, 2)
        else:
            color = (220, 220, 80) if h.get("armed", False) else (120, 120, 70)
            pygame.draw.circle(screen, color, (sx, sy), rad)


def draw_projectiles(screen, px, py, angle, shots):
    projected = []
    for i, s in enumerate(shots):
        p = project_sprite(px, py, angle, s["x"], s["y"])
        if p is None:
            continue
        sx, sy, size, dist = p
        projected.append((dist, i, sx, sy, max(4, size // 5)))

    projected.sort(reverse=True)
    for _, _, sx, sy, rad in projected:
        pygame.draw.circle(screen, (140, 255, 120), (sx, sy), rad)
        pygame.draw.circle(screen, (40, 70, 30), (sx, sy), max(2, rad // 2))


def draw_minimap(screen, px, py, veggies, shots, pickups, hazards):
    tile = 12
    ox, oy = 16, 16
    for j, row in enumerate(WORLD_MAP):
        for i, c in enumerate(row):
            color = (50, 50, 50)
            if c == "#":
                color = (130, 100, 70)
            elif c in "TRPGV":
                color = (80, 130, 80)
            pygame.draw.rect(screen, color, (ox + i * tile, oy + j * tile, tile - 1, tile - 1))

    for v in veggies:
        if v["captured"]:
            continue
        if v["kind"] == "carrot":
            vc = (235, 120, 40)
        elif v["kind"] == "spitter":
            vc = (120, 210, 80)
        else:
            vc = (190, 120, 240)
        rad = 4 if v["kind"] == "boss" else 3
        pygame.draw.circle(screen, vc, (ox + int(v["x"] * tile), oy + int(v["y"] * tile)), rad)

    for s in shots:
        pygame.draw.circle(screen, (140, 255, 120), (ox + int(s["x"] * tile), oy + int(s["y"] * tile)), 2)

    for p in pickups:
        if p["kind"] == "health":
            pc = (255, 90, 90)
        elif p["kind"] == "rope":
            pc = (80, 180, 255)
        else:
            pc = (245, 210, 80)
        pygame.draw.circle(screen, pc, (ox + int(p["x"] * tile), oy + int(p["y"] * tile)), 2)

    for h in hazards:
        hc = (220, 160, 70) if h["kind"] == "tractor_sweep" else (180, 130, 70) if h["kind"] == "pallet_crusher" else (220, 220, 80)
        pygame.draw.circle(screen, hc, (ox + int(h["x"] * tile), oy + int(h["y"] * tile)), 2)

    for idx, g in enumerate(GATE_SEGMENTS):
        if idx < len(CURRENT_GATE_LOCKS) and CURRENT_GATE_LOCKS[idx]:
            ymid = (g["y1"] + g["y2"]) / 2
            pygame.draw.rect(screen, (170, 120, 70), (ox + int(g["x"] * tile) - 1, oy + int(ymid * tile) - 16, 3, 32))

    pygame.draw.circle(screen, (255, 230, 120), (ox + int(px * tile), oy + int(py * tile)), 4)


def spawn_wave_pickups(wave: int, px: float, py: float, bounds=None):
    pickups = []
    hx, hy = random_open_position(2.0, px, py, bounds)
    pickups.append({"kind": "health", "x": hx, "y": hy, "ttl": 22.0})

    if wave % 2 == 0:
        rx, ry = random_open_position(2.0, px, py, bounds)
        pickups.append({"kind": "rope", "x": rx, "y": ry, "ttl": 18.0})
    return pickups


def update_pickups(pickups, dt, px, py, hp, rope_boost_timer):
    kept = []
    picked_any = False
    keys_found = 0

    for p in pickups:
        ttl = p["ttl"] - dt
        if ttl <= 0:
            continue

        if math.hypot(px - p["x"], py - p["y"]) < 0.55:
            picked_any = True
            if p["kind"] == "health":
                hp = min(MAX_HP, hp + 25)
            elif p["kind"] == "rope":
                rope_boost_timer = max(rope_boost_timer, ROPE_BOOST_DURATION)
            elif p["kind"] == "gate_key":
                keys_found += 1
            continue

        p["ttl"] = ttl
        kept.append(p)

    return kept, hp, rope_boost_timer, picked_any, keys_found


def spawn_transition_hazards(boss, wave, exposed_now, px, py, bounds=None):
    hazards = []

    if exposed_now:
        # On exposed swap: localized crusher pulse near boss/player lane
        cx = (boss["x"] + px) / 2
        cy = (boss["y"] + py) / 2
        if is_wall(cx, cy):
            cx, cy = boss["x"], boss["y"]
        hazards.append(
            {
                "kind": "pallet_crusher",
                "x": cx,
                "y": cy,
                "ttl": 3.2,
                "pulse_t": 0.0,
                "pulse_radius": 0.4,
                "max_radius": 2.0 + min(1.2, wave * 0.06),
            }
        )
    else:
        # On armored swap: tractor sweep lane + a rake mine nearby
        lane_y = max(1.5, min(len(WORLD_MAP) - 1.5, boss["y"]))
        hazards.append(
            {
                "kind": "tractor_sweep",
                "x": 1.2,
                "y": lane_y,
                "dx": 1.0,
                "speed": 2.4 + min(1.4, wave * 0.08),
                "ttl": 5.2,
                "radius": 0.75,
            }
        )
        mx, my = random_open_position(1.3, px, py, bounds)
        hazards.append(
            {
                "kind": "rake_mine",
                "x": mx,
                "y": my,
                "ttl": 10.0,
                "armed_in": 1.0,
                "armed": False,
                "triggered": False,
                "blast_t": 0.0,
                "blast_radius": 1.35,
                "did_hit": False,
            }
        )

    return hazards


def update_hazards(hazards, dt, px, py, hp, player_invuln):
    kept = []
    took_hit = False

    for h in hazards:
        ttl = h.get("ttl", 0.0) - dt
        if ttl <= 0:
            continue
        h["ttl"] = ttl

        if h["kind"] == "tractor_sweep":
            nx = h["x"] + h["dx"] * h["speed"] * dt
            if is_wall(nx, h["y"]):
                h["ttl"] = 0
                continue
            h["x"] = nx
            if player_invuln <= 0 and math.hypot(px - h["x"], py - h["y"]) < h.get("radius", 0.7):
                hp = max(0, hp - 14)
                player_invuln = 0.5
                took_hit = True

        elif h["kind"] == "pallet_crusher":
            h["pulse_t"] = h.get("pulse_t", 0.0) + dt
            mr = h.get("max_radius", 2.0)
            h["pulse_radius"] = 0.35 + abs(math.sin(h["pulse_t"] * 6.4)) * mr
            if player_invuln <= 0 and math.hypot(px - h["x"], py - h["y"]) < h["pulse_radius"]:
                hp = max(0, hp - 9)
                player_invuln = 0.45
                took_hit = True

        else:  # rake_mine
            if not h.get("armed", False):
                h["armed_in"] = h.get("armed_in", 0.0) - dt
                if h["armed_in"] <= 0:
                    h["armed"] = True
            elif not h.get("triggered", False):
                if math.hypot(px - h["x"], py - h["y"]) < 0.95:
                    h["triggered"] = True
                    h["blast_t"] = 0.38
            else:
                h["blast_t"] -= dt
                if h["blast_t"] <= 0:
                    h["ttl"] = 0
                    continue
                if (
                    not h.get("did_hit", False)
                    and player_invuln <= 0
                    and math.hypot(px - h["x"], py - h["y"]) < h.get("blast_radius", 1.25)
                ):
                    hp = max(0, hp - 18)
                    player_invuln = 0.6
                    h["did_hit"] = True
                    took_hit = True

        if h.get("ttl", 0) > 0:
            kept.append(h)

    return kept, hp, player_invuln, took_hit


def update_shots(shots, dt, px, py, hp, player_invuln):
    kept = []
    if player_invuln > 0:
        can_hit_player = False
    else:
        can_hit_player = True

    for s in shots:
        nx = s["x"] + s["dx"] * s["speed"] * dt
        ny = s["y"] + s["dy"] * s["speed"] * dt
        ttl = s["ttl"] - dt

        if ttl <= 0 or is_wall(nx, ny):
            continue

        hit_player = False
        if can_hit_player:
            if math.hypot(px - nx, py - ny) < 0.34:
                hp = max(0, hp - 8)
                player_invuln = 0.45
                can_hit_player = False
                hit_player = True

        if not hit_player:
            s["x"], s["y"], s["ttl"] = nx, ny, ttl
            kept.append(s)

    return kept, hp, player_invuln


def update_veggies(veggies, px, py, dt, wave, room_bounds=None):
    spawned_shots = []
    spawned_hazards = []
    wave_speed_scale = 1.0 + min(0.45, wave * 0.04)
    for v in veggies:
        if v["captured"]:
            continue
        if v["latched"]:
            v["attack_cd"] = max(0.0, v["attack_cd"] - dt)
            continue

        dx = px - v["x"]
        dy = py - v["y"]
        dist = math.hypot(dx, dy)
        sees_player = has_line_of_sight(v["x"], v["y"], px, py)

        if v["kind"] == "boss":
            v["phase_timer"] = max(0.0, v.get("phase_timer", 0.0) - dt)
            if v["phase_timer"] <= 0:
                v["exposed"] = not v.get("exposed", True)
                v["phase_timer"] = 3.6 if v["exposed"] else 2.4
                spawned_hazards.extend(spawn_transition_hazards(v, wave, v["exposed"], px, py, room_bounds))

            if dist > 0.001:
                nx, ny = dx / dist, dy / dist
            else:
                nx, ny = 0.0, 0.0

            move_speed = 0.5 * wave_speed_scale
            nx_pos = v["x"] + nx * move_speed * dt
            ny_pos = v["y"] + ny * move_speed * dt
            if not is_wall(nx_pos, v["y"]):
                v["x"] = nx_pos
            if not is_wall(v["x"], ny_pos):
                v["y"] = ny_pos

            v["attack_cd"] = max(0.0, v["attack_cd"] - dt)
            if v["attack_cd"] <= 0 and sees_player:
                if v.get("exposed", False):
                    # Focused pressure: aimed triple shot
                    spread = [-0.18, 0.0, 0.18]
                    base_a = math.atan2(dy, dx)
                    for off in spread:
                        a = base_a + off
                        spawned_shots.append(
                            {
                                "x": v["x"],
                                "y": v["y"],
                                "dx": math.cos(a),
                                "dy": math.sin(a),
                                "speed": 4.0 + min(2.2, wave * 0.16),
                                "ttl": 2.4,
                            }
                        )
                    v["attack_cd"] = 1.2
                else:
                    # Arena pressure pattern: radial burst
                    rays = 10
                    for i in range(rays):
                        a = (math.tau * i) / rays
                        spawned_shots.append(
                            {
                                "x": v["x"],
                                "y": v["y"],
                                "dx": math.cos(a),
                                "dy": math.sin(a),
                                "speed": 3.4 + min(1.5, wave * 0.12),
                                "ttl": 2.0,
                            }
                        )
                    v["attack_cd"] = 1.75
            continue

        if dist < 4.5 and sees_player:
            speed = (1.0 if v["kind"] == "carrot" else 0.72) * wave_speed_scale
            if dist > 0.001:
                nx, ny = dx / dist, dy / dist
            else:
                nx, ny = 0.0, 0.0

            if v["kind"] == "spitter" and dist < 2.8:
                nx, ny = -nx, -ny
                speed = 0.9
        else:
            v["wander_t"] -= dt
            if v["wander_t"] <= 0:
                a = random.random() * math.tau
                v["vx"], v["vy"] = math.cos(a), math.sin(a)
                v["wander_t"] = random.uniform(0.8, 2.0)
            nx, ny = v["vx"], v["vy"]
            speed = 0.55 * wave_speed_scale

        nx_pos = v["x"] + nx * speed * dt
        ny_pos = v["y"] + ny * speed * dt
        if not is_wall(nx_pos, v["y"]):
            v["x"] = nx_pos
        else:
            v["vx"] *= -1
        if not is_wall(v["x"], ny_pos):
            v["y"] = ny_pos
        else:
            v["vy"] *= -1

        v["attack_cd"] = max(0.0, v["attack_cd"] - dt)

        if v["kind"] == "spitter" and v["attack_cd"] <= 0 and sees_player and dist < 6.3:
            if dist > 0.001:
                sd_x, sd_y = dx / dist, dy / dist
            else:
                sd_x, sd_y = 0.0, 0.0
            shot_speed = 3.6 + min(2.0, wave * 0.14)
            spawned_shots.append({"x": v["x"], "y": v["y"], "dx": sd_x, "dy": sd_y, "speed": shot_speed, "ttl": 2.1})
            v["attack_cd"] = max(0.75, 1.45 - wave * 0.05)

    return spawned_shots, spawned_hazards


def apply_enemy_melee(veggies, px, py, hp, player_invuln):
    if player_invuln > 0:
        return hp, player_invuln, False

    took_hit = False
    for v in veggies:
        if v["captured"] or v["latched"]:
            continue
        if v["kind"] not in ("carrot", "boss"):
            continue
        if v["attack_cd"] > 0:
            continue

        dx = px - v["x"]
        dy = py - v["y"]
        dist = math.hypot(dx, dy)

        if v["kind"] == "boss":
            hit_range = 1.9
            dmg = 18
            cooldown = 1.15
        else:
            hit_range = 1.35
            dmg = 12
            cooldown = 0.9

        if dist < hit_range and has_line_of_sight(v["x"], v["y"], px, py):
            hp -= dmg
            player_invuln = 0.65
            v["attack_cd"] = cooldown
            took_hit = True
            break

    return max(0, hp), player_invuln, took_hit


def select_lasso_target(px, py, angle, veggies, max_dist=6.0, cone=0.16):
    best_idx = None
    best_dist = 999.0
    for i, v in enumerate(veggies):
        if v["captured"]:
            continue
        dx = v["x"] - px
        dy = v["y"] - py
        dist = math.hypot(dx, dy)
        if dist > max_dist:
            continue
        a = math.atan2(dy, dx)
        delta = (a - angle + math.pi) % (2 * math.pi) - math.pi
        if abs(delta) > cone:
            continue
        if not has_line_of_sight(px, py, v["x"], v["y"]):
            continue
        if dist < best_dist:
            best_dist = dist
            best_idx = i
    return best_idx, best_dist


def get_boss_status(veggies):
    for v in veggies:
        if not v.get("captured", False) and v.get("kind") == "boss":
            return v.get("weakpoints", 0), v.get("exposed", False)
    return None


def draw_health_bar(screen, hp):
    x, y, w, h = 16, HEIGHT - 74, 320, 20
    pygame.draw.rect(screen, (35, 35, 35), (x - 2, y - 2, w + 4, h + 4))
    pygame.draw.rect(screen, (70, 18, 18), (x, y, w, h))
    fill = int((max(0, hp) / MAX_HP) * w)
    pygame.draw.rect(screen, (220, 50, 50), (x, y, fill, h))


def draw_hud(screen, font, score, combo, lasso_state, hp, round_state, wave, rope_boost_timer, boss_status=None, room_name="", keys=0):
    boost = f" BOOST {rope_boost_timer:0.1f}s" if rope_boost_timer > 0 else ""
    room = f" ROOM:{room_name}" if room_name else ""
    text = f"WAVE {wave:02d}   KEYS {keys}   SCORE {score:05d}   COMBO x{combo}   HP {hp:03d}   LASSO: {lasso_state.upper()}{boost}{room}"
    surf = font.render(text, True, (250, 250, 250))
    shadow = font.render(text, True, (20, 20, 20))
    screen.blit(shadow, (18, HEIGHT - 38))
    screen.blit(surf, (16, HEIGHT - 40))
    draw_health_bar(screen, hp)

    if boss_status is not None:
        weakpoints, exposed = boss_status
        phase = "EXPOSED" if exposed else "ARMORED"
        boss_text = f"BOSS TURNIP  WEAKPOINTS:{weakpoints}  PHASE:{phase}"
        boss_surf = font.render(boss_text, True, (240, 200, 255))
        screen.blit(boss_surf, (16, 12))

    if round_state == "win":
        msg = "ALL VEGGIES CAPTURED - PRESS R TO RESTART OR ESC TO QUIT"
        banner = font.render(msg, True, (255, 255, 120))
        screen.blit(banner, (WIDTH // 2 - 360, 24))
    elif round_state == "dead":
        msg = "YOU GOT MULCHED - PRESS R TO RESTART OR ESC TO QUIT"
        banner = font.render(msg, True, (255, 120, 120))
        screen.blit(banner, (WIDTH // 2 - 320, 24))


def reset_round():
    px, py, angle = PLAYER_START
    start_wave = 1
    room_index = 0
    room_bounds = ROOMS[room_index]["bounds"]
    sync_gate_locks(0)
    return {
        "px": px,
        "py": py,
        "angle": angle,
        "wave": start_wave,
        "room_index": room_index,
        "room_wave": 1,
        "keys": 0,
        "wave_spawn_timer": 0.0,
        "veggies": spawn_veggies(start_wave, px, py, room_bounds),
        "shots": [],
        "hazards": [],
        "pickups": spawn_wave_pickups(start_wave, px, py, room_bounds),
        "lasso_state": "idle",
        "lasso_target": None,
        "lasso_timer": 0.0,
        "break_timer": 0.0,
        "combo": 1,
        "combo_timer": 0.0,
        "hp": MAX_HP,
        "player_invuln": 0.0,
        "rope_boost_timer": 0.0,
        "round_state": "alive",
    }


def parse_cli_args():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--seed", type=str, default=None, help="Seed for deterministic run generation")
    parser.add_argument("--save-file", type=str, default=DEFAULT_SAVE_FILE, help="Path for save/load file")
    parser.add_argument("--load-file", type=str, default=None, help="Load this save file on startup")
    parser.add_argument("--fixed-dt", type=float, default=0.0, help="Optional fixed dt for deterministic simulation testing")
    return parser.parse_args()


def normalize_seed(seed_text):
    if seed_text is None:
        return int(time.time() * 1000) % 1_000_000_000
    try:
        return int(seed_text)
    except ValueError:
        return int.from_bytes(seed_text.encode("utf-8"), "little") % 1_000_000_000


def new_run(seed_text=None):
    run_seed = normalize_seed(seed_text)
    random.seed(run_seed)
    state = reset_round()
    return state, run_seed


def save_run(path: Path, state: dict, score: int, prev_space: bool, run_seed: int):
    payload = {
        "version": SAVE_VERSION,
        "game": "sillyveggiesremix",
        "seed": run_seed,
        "saved_at": int(time.time()),
        "score": score,
        "prev_space": prev_space,
        "state": state,
        "rng_state_b64": base64.b64encode(pickle.dumps(random.getstate())).decode("ascii"),
    }

    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")))
    tmp.replace(path)


def load_run(path: Path):
    path = path.expanduser()
    payload = json.loads(path.read_text())

    if payload.get("version") != SAVE_VERSION:
        raise ValueError(f"Unsupported save version: {payload.get('version')}")

    state = payload["state"]
    score = int(payload.get("score", 0))
    prev_space = bool(payload.get("prev_space", False))
    run_seed = int(payload.get("seed", 0))

    lasso_target = state.get("lasso_target")
    veggies = state.get("veggies", [])
    if lasso_target is not None and (not isinstance(lasso_target, int) or lasso_target < 0 or lasso_target >= len(veggies)):
        state["lasso_target"] = None
        state["lasso_state"] = "idle"

    rng_state_b64 = payload.get("rng_state_b64")
    if rng_state_b64:
        rng_state = pickle.loads(base64.b64decode(rng_state_b64.encode("ascii")))
        random.setstate(rng_state)
    else:
        random.seed(run_seed)

    sync_gate_locks(state.get("keys", 0))
    return state, score, prev_space, run_seed


def main():
    args = parse_cli_args()
    save_path = Path(args.save_file).expanduser()
    fixed_dt = max(0.0, float(args.fixed_dt or 0.0))

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("SillyVeggiesRemix - prototype")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 24)

    audio = AudioBank()
    audio.init()

    combo_window = 2.0

    if args.load_file:
        try:
            state, score, prev_space, run_seed = load_run(Path(args.load_file))
            print(f"[load] startup restored {Path(args.load_file).expanduser()}")
        except Exception as e:
            print(f"[load] startup failed ({e}); starting new run")
            state, run_seed = new_run(args.seed)
            score = 0
            prev_space = False
    else:
        state, run_seed = new_run(args.seed)
        score = 0
        prev_space = False

    while True:
        dt = fixed_dt if fixed_dt > 0 else (clock.tick(60) / 1000)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F5:
                    try:
                        save_run(save_path, state, score, prev_space, run_seed)
                        print(f"[save] wrote {save_path}")
                    except Exception as e:
                        print(f"[save] failed: {e}")
                elif event.key == pygame.K_F9:
                    try:
                        state, score, prev_space, run_seed = load_run(save_path)
                        print(f"[load] restored {save_path}")
                    except Exception as e:
                        print(f"[load] failed: {e}")

        keys = pygame.key.get_pressed()

        if keys[pygame.K_ESCAPE]:
            pygame.quit()
            sys.exit(0)

        if keys[pygame.K_r] and state["round_state"] in ("dead", "win"):
            state, run_seed = new_run(args.seed)
            score = 0
            prev_space = False

        state["player_invuln"] = max(0.0, state["player_invuln"] - dt)
        state["rope_boost_timer"] = max(0.0, state["rope_boost_timer"] - dt)
        sync_gate_locks(state.get("keys", 0))
        current_room = ROOMS[state.get("room_index", 0)]
        room_bounds = current_room["bounds"]

        if state["round_state"] == "alive":
            move_speed = 3.1 * dt
            rot_speed = 1.85 * dt

            if keys[pygame.K_LEFT]:
                state["angle"] -= rot_speed
            if keys[pygame.K_RIGHT]:
                state["angle"] += rot_speed

            dx = math.cos(state["angle"])
            dy = math.sin(state["angle"])

            next_x, next_y = state["px"], state["py"]
            if keys[pygame.K_w]:
                next_x += dx * move_speed
                next_y += dy * move_speed
            if keys[pygame.K_s]:
                next_x -= dx * move_speed
                next_y -= dy * move_speed
            if keys[pygame.K_a]:
                next_x += dy * move_speed
                next_y -= dx * move_speed
            if keys[pygame.K_d]:
                next_x -= dy * move_speed
                next_y += dx * move_speed

            if not is_wall(next_x, state["py"]):
                state["px"] = next_x
            if not is_wall(state["px"], next_y):
                state["py"] = next_y

            new_shots, new_hazards = update_veggies(state["veggies"], state["px"], state["py"], dt, state["wave"], room_bounds)
            if new_shots:
                state["shots"].extend(new_shots)
                audio.play("spit")
            if new_hazards:
                state["hazards"].extend(new_hazards)

            hp_before_shots = state["hp"]
            state["shots"], state["hp"], state["player_invuln"] = update_shots(
                state["shots"], dt, state["px"], state["py"], state["hp"], state["player_invuln"]
            )
            if state["hp"] < hp_before_shots:
                audio.play("player_hit")

            hp_before_haz = state["hp"]
            state["hazards"], state["hp"], state["player_invuln"], hazard_hit = update_hazards(
                state["hazards"], dt, state["px"], state["py"], state["hp"], state["player_invuln"]
            )
            if state["hp"] < hp_before_haz or hazard_hit:
                audio.play("player_hit")

            state["pickups"], state["hp"], state["rope_boost_timer"], picked_any, keys_found = update_pickups(
                state["pickups"], dt, state["px"], state["py"], state["hp"], state["rope_boost_timer"]
            )
            if keys_found > 0:
                state["keys"] = min(len(GATE_SEGMENTS), state.get("keys", 0) + keys_found)
                new_room_index = min(len(ROOMS) - 1, state["room_index"] + keys_found)
                if new_room_index != state["room_index"]:
                    state["room_index"] = new_room_index
                    sx, sy, sa = ROOMS[state["room_index"]]["spawn"]
                    state["px"], state["py"], state["angle"] = sx, sy, sa
                    state["room_wave"] = 1
                    state["wave"] += 1
                    nr_bounds = ROOMS[state["room_index"]]["bounds"]
                    state["veggies"] = spawn_veggies(state["wave"], state["px"], state["py"], nr_bounds)
                    state["shots"] = []
                    state["hazards"] = []
                    state["pickups"].extend(spawn_wave_pickups(state["wave"], state["px"], state["py"], nr_bounds))
                    state["wave_spawn_timer"] = 0.0
            if picked_any:
                audio.play("pickup")

            state["combo_timer"] -= dt
            if state["combo_timer"] <= 0:
                state["combo"] = 1

            if state["break_timer"] > 0:
                state["break_timer"] -= dt

            old_hp = state["hp"]
            state["hp"], state["player_invuln"], melee_hit = apply_enemy_melee(
                state["veggies"], state["px"], state["py"], state["hp"], state["player_invuln"]
            )
            if state["hp"] < old_hp or melee_hit:
                audio.play("player_hit")

            if state["hp"] <= 0:
                state["round_state"] = "dead"
                if state["lasso_target"] is not None and state["lasso_target"] < len(state["veggies"]):
                    state["veggies"][state["lasso_target"]]["latched"] = False
                state["lasso_state"] = "idle"
                state["lasso_target"] = None

            space_down = keys[pygame.K_SPACE]
            pressed = space_down and not prev_space
            prev_space = space_down

            if state["lasso_state"] == "idle" and pressed and state["break_timer"] <= 0:
                state["lasso_state"] = "fired"
                state["lasso_timer"] = 0.12
                audio.play("lasso_fire")
                target_idx, _ = select_lasso_target(state["px"], state["py"], state["angle"], state["veggies"])
                if target_idx is not None:
                    state["lasso_target"] = target_idx
                    state["veggies"][target_idx]["latched"] = True
                    state["lasso_state"] = "latched"
                    audio.play("lasso_latch")

            elif state["lasso_state"] == "fired":
                state["lasso_timer"] -= dt
                if state["lasso_timer"] <= 0:
                    state["lasso_state"] = "idle"

            elif state["lasso_state"] in ("latched", "reeling"):
                if (
                    state["lasso_target"] is None
                    or state["lasso_target"] >= len(state["veggies"])
                    or state["veggies"][state["lasso_target"]]["captured"]
                ):
                    state["lasso_state"] = "idle"
                    state["lasso_target"] = None
                else:
                    target = state["veggies"][state["lasso_target"]]
                    tx, ty = target["x"], target["y"]
                    tdx, tdy = tx - state["px"], ty - state["py"]
                    dist = math.hypot(tdx, tdy)

                    if dist > 7.0 or not has_line_of_sight(state["px"], state["py"], tx, ty):
                        target["latched"] = False
                        state["lasso_state"] = "idle"
                        state["lasso_target"] = None
                        state["break_timer"] = 0.35
                    else:
                        if space_down:
                            state["lasso_state"] = "reeling"
                            if dist > 0.001:
                                pull_speed = ROPE_BASE_PULL * (ROPE_BOOST_MULT if state["rope_boost_timer"] > 0 else 1.0)
                                pull = min(pull_speed * dt, dist)
                                nx, ny = tdx / dist, tdy / dist
                                nx_pos = target["x"] - nx * pull
                                ny_pos = target["y"] - ny * pull
                                if not is_wall(nx_pos, ny_pos):
                                    target["x"] = nx_pos
                                    target["y"] = ny_pos

                            if dist < 1.15:
                                if target["kind"] == "boss":
                                    if target.get("exposed", False):
                                        target["weakpoints"] = max(0, target.get("weakpoints", 1) - 1)
                                        target["exposed"] = False
                                        target["phase_timer"] = 2.2
                                        state["lasso_target"] = None
                                        state["lasso_state"] = "idle"
                                        target["latched"] = False
                                        audio.play("capture")

                                        if target["weakpoints"] <= 0:
                                            target["captured"] = True
                                            if state["combo_timer"] > 0:
                                                state["combo"] += 2
                                            else:
                                                state["combo"] = 2
                                            score += 500 * state["combo"]
                                        else:
                                            if state["combo_timer"] > 0:
                                                state["combo"] += 1
                                            else:
                                                state["combo"] = 1
                                            score += 220 * state["combo"]
                                        state["combo_timer"] = combo_window
                                    else:
                                        # Rope bounces off armor if phase is closed
                                        target["latched"] = False
                                        state["lasso_target"] = None
                                        state["lasso_state"] = "idle"
                                        state["break_timer"] = 0.25
                                else:
                                    target["captured"] = True
                                    target["latched"] = False
                                    state["lasso_target"] = None
                                    state["lasso_state"] = "idle"
                                    audio.play("capture")

                                    if state["combo_timer"] > 0:
                                        state["combo"] += 1
                                    else:
                                        state["combo"] = 1
                                    state["combo_timer"] = combo_window
                                    score += 100 * state["combo"]
                        else:
                            state["lasso_state"] = "latched"

            if all(v["captured"] for v in state["veggies"]):
                if state["wave_spawn_timer"] <= 0:
                    state["wave_spawn_timer"] = 2.0
                else:
                    state["wave_spawn_timer"] -= dt
                    if state["wave_spawn_timer"] <= 0:
                        last_room = len(ROOMS) - 1
                        in_final_room = state["room_index"] >= last_room

                        has_gate_key_drop = any(p.get("kind") == "gate_key" for p in state["pickups"])
                        if (
                            not in_final_room
                            and state.get("room_wave", 1) >= ROOM_WAVES_REQUIRED
                            and not has_gate_key_drop
                        ):
                            kx, ky = random_open_position(1.4, state["px"], state["py"], room_bounds)
                            state["pickups"].append({"kind": "gate_key", "x": kx, "y": ky, "ttl": 90.0})
                            state["wave_spawn_timer"] = 0.0
                        else:
                            state["wave"] += 1
                            state["room_wave"] = state.get("room_wave", 1) + 1
                            state["veggies"] = spawn_veggies(state["wave"], state["px"], state["py"], room_bounds)
                            state["hazards"] = []
                            state["pickups"].extend(spawn_wave_pickups(state["wave"], state["px"], state["py"], room_bounds))
                            state["wave_spawn_timer"] = 0.0

        else:
            prev_space = keys[pygame.K_SPACE]

        draw_background(screen)
        cast_rays(screen, state["px"], state["py"], state["angle"])
        draw_veggies(screen, state["px"], state["py"], state["angle"], state["veggies"])
        draw_pickups(screen, state["px"], state["py"], state["angle"], state["pickups"])
        draw_gates(screen, state["px"], state["py"], state["angle"])
        draw_hazards(screen, state["px"], state["py"], state["angle"], state["hazards"])
        draw_projectiles(screen, state["px"], state["py"], state["angle"], state["shots"])
        draw_minimap(screen, state["px"], state["py"], state["veggies"], state["shots"], state["pickups"], state["hazards"])

        if state["lasso_target"] is not None and state["lasso_target"] < len(state["veggies"]):
            target = state["veggies"][state["lasso_target"]]
            if not target["captured"]:
                proj = project_sprite(state["px"], state["py"], state["angle"], target["x"], target["y"])
                if proj is not None:
                    tx, ty, _, _ = proj
                    pygame.draw.line(screen, (245, 240, 170), (WIDTH // 2, HEIGHT // 2), (tx, ty), 2)

        if state["player_invuln"] > 0:
            flash = 130 if int(state["player_invuln"] * 20) % 2 == 0 else 0
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((255, 40, 40, flash // 3))
            screen.blit(overlay, (0, 0))

        pygame.draw.circle(screen, (255, 255, 255), (WIDTH // 2, HEIGHT // 2), 5, 1)
        boss_status = get_boss_status(state["veggies"])
        draw_hud(
            screen,
            font,
            score,
            state["combo"],
            state["lasso_state"],
            state["hp"],
            state["round_state"],
            state["wave"],
            state["rope_boost_timer"],
            boss_status,
            current_room["name"],
            state.get("keys", 0),
        )

        if state["wave_spawn_timer"] > 0:
            nxt = font.render(f"NEXT WAVE IN {state['wave_spawn_timer']:.1f}s", True, (255, 220, 120))
            screen.blit(nxt, (WIDTH // 2 - 130, 24))
        elif any(p.get("kind") == "gate_key" for p in state["pickups"]):
            gate_msg = font.render("GATE KEY DROPPED - GRAB IT TO UNLOCK NEXT ROOM", True, (255, 230, 120))
            screen.blit(gate_msg, (WIDTH // 2 - 270, 24))

        pygame.display.flip()


if __name__ == "__main__":
    main()

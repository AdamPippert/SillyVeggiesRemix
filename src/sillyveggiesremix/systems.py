import math
import random


_IS_WALL = None
_HAS_LOS = None
_RANDOM_OPEN = None
_CFG = {
    "BOSS_WAVE_INTERVAL": 5,
    "ROPE_BOOST_DURATION": 6.0,
}


def configure(is_wall_fn, has_los_fn, random_open_fn, cfg=None):
    global _IS_WALL, _HAS_LOS, _RANDOM_OPEN
    _IS_WALL = is_wall_fn
    _HAS_LOS = has_los_fn
    _RANDOM_OPEN = random_open_fn
    if cfg:
        _CFG.update(cfg)


def spawn_veggies(wave: int, px: float, py: float, bounds=None):
    wave = max(1, wave)

    if wave % int(_CFG.get("BOSS_WAVE_INTERVAL", 5)) == 0:
        bx, by = _RANDOM_OPEN(4.0, px, py, bounds)
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

        support_count = min(4, 1 + wave // int(_CFG.get("BOSS_WAVE_INTERVAL", 5)))
        support = []
        for i in range(support_count):
            sx, sy = _RANDOM_OPEN(3.0, px, py, bounds)
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
        x, y = _RANDOM_OPEN(3.0, px, py, bounds)
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
        x, y = _RANDOM_OPEN(3.0, px, py, bounds)
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


def spawn_wave_pickups(wave: int, px: float, py: float, bounds=None):
    pickups = []
    hx, hy = _RANDOM_OPEN(2.0, px, py, bounds)
    pickups.append({"kind": "health", "x": hx, "y": hy, "ttl": 22.0})

    if wave % 2 == 0:
        rx, ry = _RANDOM_OPEN(2.0, px, py, bounds)
        pickups.append({"kind": "rope", "x": rx, "y": ry, "ttl": 18.0})
    return pickups


def update_pickups(pickups, dt, px, py, hp, rope_boost_timer):
    kept = []
    picked_any = False
    keys_found = 0
    picked_kinds = {"health": 0, "rope": 0, "gate_key": 0}

    for p in pickups:
        ttl = p["ttl"] - dt
        if ttl <= 0:
            continue

        if math.hypot(px - p["x"], py - p["y"]) < 0.55:
            picked_any = True
            if p["kind"] == "health":
                hp = min(100, hp + 25)
                picked_kinds["health"] += 1
            elif p["kind"] == "rope":
                rope_boost_timer = max(rope_boost_timer, float(_CFG.get("ROPE_BOOST_DURATION", 6.0)))
                picked_kinds["rope"] += 1
            elif p["kind"] == "gate_key":
                keys_found += 1
                picked_kinds["gate_key"] += 1
            continue

        p["ttl"] = ttl
        kept.append(p)

    return kept, hp, rope_boost_timer, picked_any, keys_found, picked_kinds


def spawn_transition_hazards(boss, wave, exposed_now, px, py, bounds=None):
    hazards = []

    if exposed_now:
        cx = (boss["x"] + px) / 2
        cy = (boss["y"] + py) / 2
        if _IS_WALL(cx, cy):
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
        lane_y = max(1.5, min(9.5, boss["y"]))
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
        mx, my = _RANDOM_OPEN(1.3, px, py, bounds)
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
            if _IS_WALL(nx, h["y"]):
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

        else:
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
    can_hit_player = player_invuln <= 0

    for s in shots:
        nx = s["x"] + s["dx"] * s["speed"] * dt
        ny = s["y"] + s["dy"] * s["speed"] * dt
        ttl = s["ttl"] - dt

        if ttl <= 0 or _IS_WALL(nx, ny):
            continue

        hit_player = False
        if can_hit_player and math.hypot(px - nx, py - ny) < 0.34:
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
        sees_player = _HAS_LOS(v["x"], v["y"], px, py)

        if v["kind"] == "boss":
            v["phase_timer"] = max(0.0, v.get("phase_timer", 0.0) - dt)
            if v["phase_timer"] <= 0:
                v["exposed"] = not v.get("exposed", True)
                v["phase_timer"] = 3.6 if v["exposed"] else 2.4
                spawned_hazards.extend(spawn_transition_hazards(v, wave, v["exposed"], px, py, room_bounds))

            nx, ny = (dx / dist, dy / dist) if dist > 0.001 else (0.0, 0.0)
            move_speed = 0.5 * wave_speed_scale
            nx_pos = v["x"] + nx * move_speed * dt
            ny_pos = v["y"] + ny * move_speed * dt
            if not _IS_WALL(nx_pos, v["y"]):
                v["x"] = nx_pos
            if not _IS_WALL(v["x"], ny_pos):
                v["y"] = ny_pos

            v["attack_cd"] = max(0.0, v["attack_cd"] - dt)
            if v["attack_cd"] <= 0 and sees_player:
                if v.get("exposed", False):
                    spread = [-0.18, 0.0, 0.18]
                    base_a = math.atan2(dy, dx)
                    for off in spread:
                        a = base_a + off
                        spawned_shots.append({"x": v["x"], "y": v["y"], "dx": math.cos(a), "dy": math.sin(a), "speed": 4.0 + min(2.2, wave * 0.16), "ttl": 2.4})
                    v["attack_cd"] = 1.2
                else:
                    rays = 10
                    for i in range(rays):
                        a = (math.tau * i) / rays
                        spawned_shots.append({"x": v["x"], "y": v["y"], "dx": math.cos(a), "dy": math.sin(a), "speed": 3.4 + min(1.5, wave * 0.12), "ttl": 2.0})
                    v["attack_cd"] = 1.75
            continue

        if dist < 4.5 and sees_player:
            speed = (1.0 if v["kind"] == "carrot" else 0.72) * wave_speed_scale
            nx, ny = (dx / dist, dy / dist) if dist > 0.001 else (0.0, 0.0)
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
        if not _IS_WALL(nx_pos, v["y"]):
            v["x"] = nx_pos
        else:
            v["vx"] *= -1
        if not _IS_WALL(v["x"], ny_pos):
            v["y"] = ny_pos
        else:
            v["vy"] *= -1

        v["attack_cd"] = max(0.0, v["attack_cd"] - dt)

        if v["kind"] == "spitter" and v["attack_cd"] <= 0 and sees_player and dist < 6.3:
            sd_x, sd_y = (dx / dist, dy / dist) if dist > 0.001 else (0.0, 0.0)
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
            hit_range, dmg, cooldown = 1.9, 18, 1.15
        else:
            hit_range, dmg, cooldown = 1.35, 12, 0.9

        if dist < hit_range and _HAS_LOS(v["x"], v["y"], px, py):
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
        if not _HAS_LOS(px, py, v["x"], v["y"]):
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

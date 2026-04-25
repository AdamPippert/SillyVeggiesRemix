import math
import random
import sys
from pathlib import Path

import pygame

from .entities import AudioBank as EntityAudioBank
from . import rendering as game_rendering
from . import runtime as game_runtime
from . import systems as game_systems

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
DEFAULT_TELEMETRY_FILE = "run_telemetry.jsonl"


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
    picked_kinds = {"health": 0, "rope": 0, "gate_key": 0}

    for p in pickups:
        ttl = p["ttl"] - dt
        if ttl <= 0:
            continue

        if math.hypot(px - p["x"], py - p["y"]) < 0.55:
            picked_any = True
            if p["kind"] == "health":
                hp = min(MAX_HP, hp + 25)
                picked_kinds["health"] += 1
            elif p["kind"] == "rope":
                rope_boost_timer = max(rope_boost_timer, ROPE_BOOST_DURATION)
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
        "veggies": game_systems.spawn_veggies(start_wave, px, py, room_bounds),
        "shots": [],
        "hazards": [],
        "pickups": game_systems.spawn_wave_pickups(start_wave, px, py, room_bounds),
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


def main():
    args = game_runtime.parse_cli_args(DEFAULT_SAVE_FILE, DEFAULT_TELEMETRY_FILE)
    save_path = Path(args.save_file).expanduser()
    telemetry_path = Path(args.telemetry_file).expanduser()
    telemetry_enabled = not args.no_telemetry
    fixed_dt = max(0.0, float(args.fixed_dt or 0.0))

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("SillyVeggiesRemix - prototype")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 24)

    audio = EntityAudioBank()
    audio.init()

    game_systems.configure(
        is_wall,
        has_line_of_sight,
        random_open_position,
        {"BOSS_WAVE_INTERVAL": BOSS_WAVE_INTERVAL, "ROPE_BOOST_DURATION": ROPE_BOOST_DURATION},
    )

    combo_window = 2.0

    if args.load_file:
        try:
            state, score, prev_space, run_seed = game_runtime.load_run(Path(args.load_file), SAVE_VERSION, sync_gate_locks)
            run_metrics = game_runtime.init_run_metrics(run_seed, loaded_from=str(Path(args.load_file).expanduser()))
            print(f"[load] startup restored {Path(args.load_file).expanduser()}")
        except Exception as e:
            print(f"[load] startup failed ({e}); starting new run")
            state, run_seed = game_runtime.new_run(reset_round, args.seed)
            score = 0
            prev_space = False
            run_metrics = game_runtime.init_run_metrics(run_seed)
    else:
        state, run_seed = game_runtime.new_run(reset_round, args.seed)
        score = 0
        prev_space = False
        run_metrics = game_runtime.init_run_metrics(run_seed)

    while True:
        dt = fixed_dt if fixed_dt > 0 else (clock.tick(60) / 1000)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                if telemetry_enabled:
                    game_runtime.flush_run_metrics(telemetry_path, run_metrics, "quit", state, score)
                pygame.quit()
                sys.exit(0)
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F5:
                    try:
                        game_runtime.save_run(save_path, state, score, prev_space, run_seed, SAVE_VERSION)
                        print(f"[save] wrote {save_path}")
                    except Exception as e:
                        print(f"[save] failed: {e}")
                elif event.key == pygame.K_F9:
                    try:
                        if telemetry_enabled:
                            game_runtime.flush_run_metrics(telemetry_path, run_metrics, "manual_load", state, score)
                        state, score, prev_space, run_seed = game_runtime.load_run(save_path, SAVE_VERSION, sync_gate_locks)
                        run_metrics = game_runtime.init_run_metrics(run_seed, loaded_from=str(save_path))
                        print(f"[load] restored {save_path}")
                    except Exception as e:
                        print(f"[load] failed: {e}")

        keys = pygame.key.get_pressed()

        if keys[pygame.K_ESCAPE]:
            if telemetry_enabled:
                game_runtime.flush_run_metrics(telemetry_path, run_metrics, "escape", state, score)
            pygame.quit()
            sys.exit(0)

        if keys[pygame.K_r] and state["round_state"] in ("dead", "win"):
            if telemetry_enabled:
                outcome = "restart_after_win" if state.get("round_state") == "win" else "restart_after_death"
                game_runtime.flush_run_metrics(telemetry_path, run_metrics, outcome, state, score)
            state, run_seed = game_runtime.new_run(reset_round, args.seed)
            score = 0
            prev_space = False
            run_metrics = game_runtime.init_run_metrics(run_seed)

        state["player_invuln"] = max(0.0, state["player_invuln"] - dt)
        state["rope_boost_timer"] = max(0.0, state["rope_boost_timer"] - dt)
        sync_gate_locks(state.get("keys", 0))
        current_room = ROOMS[state.get("room_index", 0)]
        room_bounds = current_room["bounds"]

        run_metrics["wave_max"] = max(int(run_metrics.get("wave_max", 1)), int(state.get("wave", 1)))
        run_metrics["room_max"] = max(int(run_metrics.get("room_max", 0)), int(state.get("room_index", 0)))
        run_metrics["score_max"] = max(int(run_metrics.get("score_max", 0)), int(score))

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

            new_shots, new_hazards = game_systems.update_veggies(state["veggies"], state["px"], state["py"], dt, state["wave"], room_bounds)
            if new_shots:
                state["shots"].extend(new_shots)
                audio.play("spit")
            if new_hazards:
                state["hazards"].extend(new_hazards)

            hp_before_shots = state["hp"]
            state["shots"], state["hp"], state["player_invuln"] = game_systems.update_shots(
                state["shots"], dt, state["px"], state["py"], state["hp"], state["player_invuln"]
            )
            shot_damage = max(0, hp_before_shots - state["hp"])
            if shot_damage > 0:
                game_runtime.telemetry_add_damage(run_metrics, "spitter_projectile", shot_damage)
                audio.play("player_hit")

            hp_before_haz = state["hp"]
            state["hazards"], state["hp"], state["player_invuln"], hazard_hit = game_systems.update_hazards(
                state["hazards"], dt, state["px"], state["py"], state["hp"], state["player_invuln"]
            )
            hazard_damage = max(0, hp_before_haz - state["hp"])
            if hazard_damage > 0 or hazard_hit:
                if hazard_damage > 0:
                    game_runtime.telemetry_add_damage(run_metrics, "environment_hazard", hazard_damage)
                audio.play("player_hit")

            state["pickups"], state["hp"], state["rope_boost_timer"], picked_any, keys_found, picked_kinds = game_systems.update_pickups(
                state["pickups"], dt, state["px"], state["py"], state["hp"], state["rope_boost_timer"]
            )
            for pk, cnt in picked_kinds.items():
                game_runtime.telemetry_add_pickup(run_metrics, pk, cnt)
            if keys_found > 0:
                run_metrics["gate_keys_collected"] = int(run_metrics.get("gate_keys_collected", 0)) + keys_found
                state["keys"] = min(len(GATE_SEGMENTS), state.get("keys", 0) + keys_found)
                new_room_index = min(len(ROOMS) - 1, state["room_index"] + keys_found)
                if new_room_index != state["room_index"]:
                    state["room_index"] = new_room_index
                    sx, sy, sa = ROOMS[state["room_index"]]["spawn"]
                    state["px"], state["py"], state["angle"] = sx, sy, sa
                    state["room_wave"] = 1
                    state["wave"] += 1
                    nr_bounds = ROOMS[state["room_index"]]["bounds"]
                    state["veggies"] = game_systems.spawn_veggies(state["wave"], state["px"], state["py"], nr_bounds)
                    state["shots"] = []
                    state["hazards"] = []
                    state["pickups"].extend(game_systems.spawn_wave_pickups(state["wave"], state["px"], state["py"], nr_bounds))
                    state["wave_spawn_timer"] = 0.0
            if picked_any:
                audio.play("pickup")

            state["combo_timer"] -= dt
            if state["combo_timer"] <= 0:
                state["combo"] = 1

            if state["break_timer"] > 0:
                state["break_timer"] -= dt

            old_hp = state["hp"]
            hp_after_melee, inv_after_melee, melee_hit = game_systems.apply_enemy_melee(
                state["veggies"], state["px"], state["py"], state["hp"], state["player_invuln"]
            )
            melee_damage = max(0, old_hp - hp_after_melee)
            state["hp"], state["player_invuln"] = hp_after_melee, inv_after_melee
            if state["hp"] < old_hp or melee_hit:
                if melee_damage > 0:
                    # Approximate source: prioritize boss melee when boss is near player
                    boss_near = any(v.get("kind") == "boss" and not v.get("captured") and math.hypot(state["px"] - v.get("x", 0), state["py"] - v.get("y", 0)) < 2.2 for v in state["veggies"])
                    game_runtime.telemetry_add_damage(run_metrics, "boss_melee" if boss_near else "carrot_melee", melee_damage)
                audio.play("player_hit")

            if state["hp"] <= 0:
                state["round_state"] = "dead"
                if telemetry_enabled:
                    game_runtime.flush_run_metrics(telemetry_path, run_metrics, "death", state, score)
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
                target_idx, _ = game_systems.select_lasso_target(state["px"], state["py"], state["angle"], state["veggies"])
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
                                        run_metrics["boss_weakpoint_hits"] = int(run_metrics.get("boss_weakpoint_hits", 0)) + 1
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
                        run_metrics["waves_cleared"] = int(run_metrics.get("waves_cleared", 0)) + 1
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
                            state["veggies"] = game_systems.spawn_veggies(state["wave"], state["px"], state["py"], room_bounds)
                            state["hazards"] = []
                            state["pickups"].extend(game_systems.spawn_wave_pickups(state["wave"], state["px"], state["py"], room_bounds))
                            state["wave_spawn_timer"] = 0.0

        else:
            prev_space = keys[pygame.K_SPACE]

        game_rendering.draw_background(screen)
        game_rendering.cast_rays(screen, state["px"], state["py"], state["angle"], is_wall)
        game_rendering.draw_veggies(screen, state["px"], state["py"], state["angle"], state["veggies"])
        game_rendering.draw_pickups(screen, state["px"], state["py"], state["angle"], state["pickups"])
        game_rendering.draw_gates(screen, state["px"], state["py"], state["angle"], GATE_SEGMENTS, CURRENT_GATE_LOCKS)
        game_rendering.draw_hazards(screen, state["px"], state["py"], state["angle"], state["hazards"])
        game_rendering.draw_projectiles(screen, state["px"], state["py"], state["angle"], state["shots"])
        game_rendering.draw_minimap(
            screen,
            state["px"],
            state["py"],
            state["veggies"],
            state["shots"],
            state["pickups"],
            state["hazards"],
            WORLD_MAP,
            GATE_SEGMENTS,
            CURRENT_GATE_LOCKS,
        )

        if state["lasso_target"] is not None and state["lasso_target"] < len(state["veggies"]):
            target = state["veggies"][state["lasso_target"]]
            if not target["captured"]:
                proj = game_rendering.project_sprite(state["px"], state["py"], state["angle"], target["x"], target["y"])
                if proj is not None:
                    tx, ty, _, _ = proj
                    pygame.draw.line(screen, (245, 240, 170), (WIDTH // 2, HEIGHT // 2), (tx, ty), 2)

        if state["player_invuln"] > 0:
            flash = 130 if int(state["player_invuln"] * 20) % 2 == 0 else 0
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((255, 40, 40, flash // 3))
            screen.blit(overlay, (0, 0))

        pygame.draw.circle(screen, (255, 255, 255), (WIDTH // 2, HEIGHT // 2), 5, 1)
        boss_status = game_systems.get_boss_status(state["veggies"])
        game_rendering.draw_hud(
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

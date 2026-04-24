import math
import random
import sys
from array import array

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


def is_wall(x: float, y: float) -> bool:
    if y < 0 or y >= len(WORLD_MAP) or x < 0 or x >= len(WORLD_MAP[0]):
        return True
    return WORLD_MAP[int(y)][int(x)] == "#"


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


def random_open_position(min_dist_from_player=0.0, px=0.0, py=0.0):
    open_tiles = []
    for y, row in enumerate(WORLD_MAP):
        for x, ch in enumerate(row):
            if ch != "#":
                cx = x + 0.5
                cy = y + 0.5
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


def spawn_veggies(wave: int, px: float, py: float):
    wave = max(1, wave)
    total = min(10, 2 + wave)
    spitters = min(total - 1, max(1, wave // 2))
    carrots = total - spitters

    veggies = []
    for _ in range(carrots):
        x, y = random_open_position(3.0, px, py)
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
        x, y = random_open_position(3.0, px, py)
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
        else:
            col = (115, 170, 70)
            accent = (180, 230, 130)

        body = pygame.Rect(screen_x - size // 2, screen_y - size // 2, size, size)
        pygame.draw.rect(screen, col, body)
        pygame.draw.rect(screen, (35, 35, 35), body, 2)

        cap = pygame.Rect(screen_x - size // 4, screen_y - size // 2 - 4, size // 2, 5)
        pygame.draw.rect(screen, accent, cap)

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
        color = (255, 70, 70) if p["kind"] == "health" else (80, 180, 255)
        core = (250, 235, 235) if p["kind"] == "health" else (220, 240, 255)
        pygame.draw.circle(screen, color, (sx, sy), rad)
        pygame.draw.circle(screen, core, (sx, sy), max(2, rad // 2))


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


def draw_minimap(screen, px, py, veggies, shots, pickups):
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
        vc = (235, 120, 40) if v["kind"] == "carrot" else (120, 210, 80)
        pygame.draw.circle(screen, vc, (ox + int(v["x"] * tile), oy + int(v["y"] * tile)), 3)

    for s in shots:
        pygame.draw.circle(screen, (140, 255, 120), (ox + int(s["x"] * tile), oy + int(s["y"] * tile)), 2)

    for p in pickups:
        pc = (255, 90, 90) if p["kind"] == "health" else (80, 180, 255)
        pygame.draw.circle(screen, pc, (ox + int(p["x"] * tile), oy + int(p["y"] * tile)), 2)

    pygame.draw.circle(screen, (255, 230, 120), (ox + int(px * tile), oy + int(py * tile)), 4)


def spawn_wave_pickups(wave: int, px: float, py: float):
    pickups = []
    hx, hy = random_open_position(2.0, px, py)
    pickups.append({"kind": "health", "x": hx, "y": hy, "ttl": 22.0})

    if wave % 2 == 0:
        rx, ry = random_open_position(2.0, px, py)
        pickups.append({"kind": "rope", "x": rx, "y": ry, "ttl": 18.0})
    return pickups


def update_pickups(pickups, dt, px, py, hp, rope_boost_timer):
    kept = []
    picked_any = False

    for p in pickups:
        ttl = p["ttl"] - dt
        if ttl <= 0:
            continue

        if math.hypot(px - p["x"], py - p["y"]) < 0.55:
            picked_any = True
            if p["kind"] == "health":
                hp = min(MAX_HP, hp + 25)
            else:
                rope_boost_timer = max(rope_boost_timer, ROPE_BOOST_DURATION)
            continue

        p["ttl"] = ttl
        kept.append(p)

    return kept, hp, rope_boost_timer, picked_any


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


def update_veggies(veggies, px, py, dt, wave):
    spawned_shots = []
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

    return spawned_shots


def apply_enemy_melee(veggies, px, py, hp, player_invuln):
    if player_invuln > 0:
        return hp, player_invuln, False

    took_hit = False
    for v in veggies:
        if v["captured"] or v["latched"]:
            continue
        if v["kind"] != "carrot":
            continue
        if v["attack_cd"] > 0:
            continue

        dx = px - v["x"]
        dy = py - v["y"]
        dist = math.hypot(dx, dy)
        if dist < 1.35 and has_line_of_sight(v["x"], v["y"], px, py):
            hp -= 12
            player_invuln = 0.65
            v["attack_cd"] = 0.9
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


def draw_health_bar(screen, hp):
    x, y, w, h = 16, HEIGHT - 74, 320, 20
    pygame.draw.rect(screen, (35, 35, 35), (x - 2, y - 2, w + 4, h + 4))
    pygame.draw.rect(screen, (70, 18, 18), (x, y, w, h))
    fill = int((max(0, hp) / MAX_HP) * w)
    pygame.draw.rect(screen, (220, 50, 50), (x, y, fill, h))


def draw_hud(screen, font, score, combo, lasso_state, hp, round_state, wave, rope_boost_timer):
    boost = f" BOOST {rope_boost_timer:0.1f}s" if rope_boost_timer > 0 else ""
    text = f"WAVE {wave:02d}   SCORE {score:05d}   COMBO x{combo}   HP {hp:03d}   LASSO: {lasso_state.upper()}{boost}"
    surf = font.render(text, True, (250, 250, 250))
    shadow = font.render(text, True, (20, 20, 20))
    screen.blit(shadow, (18, HEIGHT - 38))
    screen.blit(surf, (16, HEIGHT - 40))
    draw_health_bar(screen, hp)

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
    return {
        "px": px,
        "py": py,
        "angle": angle,
        "wave": start_wave,
        "wave_spawn_timer": 0.0,
        "veggies": spawn_veggies(start_wave, px, py),
        "shots": [],
        "pickups": spawn_wave_pickups(start_wave, px, py),
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
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("SillyVeggiesRemix - prototype")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 24)

    audio = AudioBank()
    audio.init()

    state = reset_round()
    score = 0
    combo_window = 2.0
    prev_space = False

    while True:
        dt = clock.tick(60) / 1000
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)

        keys = pygame.key.get_pressed()

        if keys[pygame.K_ESCAPE]:
            pygame.quit()
            sys.exit(0)

        if keys[pygame.K_r] and state["round_state"] in ("dead", "win"):
            state = reset_round()

        state["player_invuln"] = max(0.0, state["player_invuln"] - dt)
        state["rope_boost_timer"] = max(0.0, state["rope_boost_timer"] - dt)

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

            new_shots = update_veggies(state["veggies"], state["px"], state["py"], dt, state["wave"])
            if new_shots:
                state["shots"].extend(new_shots)
                audio.play("spit")

            hp_before_shots = state["hp"]
            state["shots"], state["hp"], state["player_invuln"] = update_shots(
                state["shots"], dt, state["px"], state["py"], state["hp"], state["player_invuln"]
            )
            if state["hp"] < hp_before_shots:
                audio.play("player_hit")

            state["pickups"], state["hp"], state["rope_boost_timer"], picked_any = update_pickups(
                state["pickups"], dt, state["px"], state["py"], state["hp"], state["rope_boost_timer"]
            )
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
                        state["wave"] += 1
                        state["veggies"] = spawn_veggies(state["wave"], state["px"], state["py"])
                        state["pickups"].extend(spawn_wave_pickups(state["wave"], state["px"], state["py"]))
                        state["wave_spawn_timer"] = 0.0

        else:
            prev_space = keys[pygame.K_SPACE]

        draw_background(screen)
        cast_rays(screen, state["px"], state["py"], state["angle"])
        draw_veggies(screen, state["px"], state["py"], state["angle"], state["veggies"])
        draw_pickups(screen, state["px"], state["py"], state["angle"], state["pickups"])
        draw_projectiles(screen, state["px"], state["py"], state["angle"], state["shots"])
        draw_minimap(screen, state["px"], state["py"], state["veggies"], state["shots"], state["pickups"])

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
        )

        if state["wave_spawn_timer"] > 0:
            nxt = font.render(f"NEXT WAVE IN {state['wave_spawn_timer']:.1f}s", True, (255, 220, 120))
            screen.blit(nxt, (WIDTH // 2 - 130, 24))

        pygame.display.flip()


if __name__ == "__main__":
    main()

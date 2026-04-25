import math

import pygame

from .content import FOV, HALF_FOV, HALF_H, HEIGHT, MAX_DEPTH, MAX_HP, NUM_RAYS, SCALE, WIDTH


def draw_background(screen):
    for y in range(HALF_H):
        k = y / HALF_H
        r = int(55 + 35 * (1 - k))
        g = int(95 + 45 * (1 - k))
        b = int(145 + 35 * (1 - k))
        pygame.draw.line(screen, (r, g, b), (0, y), (WIDTH, y))

    for y in range(HALF_H, HEIGHT):
        k = (y - HALF_H) / HALF_H
        r = int(95 - 30 * k)
        g = int(65 - 25 * k)
        b = int(40 - 20 * k)
        pygame.draw.line(screen, (r, g, b), (0, y), (WIDTH, y))
        if y % 22 == 0:
            pygame.draw.line(screen, (70, 46, 30), (0, y), (WIDTH, y))


def cast_rays(screen, px, py, angle, is_wall_fn):
    start_angle = angle - HALF_FOV
    for ray in range(NUM_RAYS):
        ray_angle = start_angle + (FOV / NUM_RAYS) * ray
        sin_a = math.sin(ray_angle)
        cos_a = math.cos(ray_angle)

        depth = 0.01
        while depth < MAX_DEPTH:
            x = px + cos_a * depth
            y = py + sin_a * depth
            if is_wall_fn(x, y):
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
                pxx = screen_x - (pips * 7) // 2 + p * 7
                pyy = screen_y - size // 2 - 12
                pygame.draw.circle(screen, (255, 220, 255), (pxx, pyy), 3)

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


def draw_gates(screen, px, py, angle, gate_segments, gate_locks):
    for idx, g in enumerate(gate_segments):
        if idx >= len(gate_locks) or not gate_locks[idx]:
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


def draw_minimap(screen, px, py, veggies, shots, pickups, hazards, world_map, gate_segments, gate_locks):
    tile = 12
    ox, oy = 16, 16
    for j, row in enumerate(world_map):
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

    for idx, g in enumerate(gate_segments):
        if idx < len(gate_locks) and gate_locks[idx]:
            ymid = (g["y1"] + g["y2"]) / 2
            pygame.draw.rect(screen, (170, 120, 70), (ox + int(g["x"] * tile) - 1, oy + int(ymid * tile) - 16, 3, 32))

    pygame.draw.circle(screen, (255, 230, 120), (ox + int(px * tile), oy + int(py * tile)), 4)


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
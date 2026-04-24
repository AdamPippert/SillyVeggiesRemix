import math
import random
import sys

import pygame

WIDTH, HEIGHT = 1280, 720
HALF_H = HEIGHT // 2
FOV = math.pi / 3
HALF_FOV = FOV / 2
NUM_RAYS = 240
MAX_DEPTH = 20
SCALE = WIDTH // NUM_RAYS

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
        color = (shade // 2, shade // 2, shade // 3)
        pygame.draw.rect(
            screen,
            color,
            (ray * SCALE, HALF_H - wall_h // 2, SCALE + 1, wall_h),
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
        col = (235, 120, 40) if v["kind"] == "carrot" else (140, 210, 90)
        body = pygame.Rect(screen_x - size // 2, screen_y - size // 2, size, size)
        pygame.draw.rect(screen, col, body)
        pygame.draw.rect(screen, (35, 35, 35), body, 2)


def draw_minimap(screen, px, py, veggies):
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
        pygame.draw.circle(screen, (235, 120, 40), (ox + int(v["x"] * tile), oy + int(v["y"] * tile)), 3)

    pygame.draw.circle(screen, (255, 230, 120), (ox + int(px * tile), oy + int(py * tile)), 4)


def update_veggies(veggies, px, py, dt):
    for v in veggies:
        if v["captured"]:
            continue
        if v["latched"]:
            continue

        dx = px - v["x"]
        dy = py - v["y"]
        dist = math.hypot(dx, dy)

        if dist < 4.5 and has_line_of_sight(v["x"], v["y"], px, py):
            # chase mode
            speed = 1.0
            if dist > 0.001:
                nx, ny = dx / dist, dy / dist
            else:
                nx, ny = 0.0, 0.0
        else:
            # patrol mode
            v["wander_t"] -= dt
            if v["wander_t"] <= 0:
                a = random.random() * math.tau
                v["vx"], v["vy"] = math.cos(a), math.sin(a)
                v["wander_t"] = random.uniform(0.8, 2.0)
            nx, ny = v["vx"], v["vy"]
            speed = 0.55

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


def draw_hud(screen, font, score, combo, lasso_state):
    text = f"SCORE {score:05d}   COMBO x{combo}   LASSO: {lasso_state.upper()}"
    surf = font.render(text, True, (250, 250, 250))
    shadow = font.render(text, True, (20, 20, 20))
    screen.blit(shadow, (18, HEIGHT - 38))
    screen.blit(surf, (16, HEIGHT - 40))


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("SillyVeggiesRemix - prototype")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 24)

    px, py = 2.5, 2.5
    angle = 0.0

    veggies = [
        {"kind": "carrot", "x": 11.5, "y": 3.5, "vx": 1.0, "vy": 0.0, "wander_t": 1.0, "captured": False, "latched": False},
        {"kind": "carrot", "x": 12.5, "y": 8.5, "vx": -1.0, "vy": 0.0, "wander_t": 1.5, "captured": False, "latched": False},
        {"kind": "carrot", "x": 8.5, "y": 6.5, "vx": 0.0, "vy": 1.0, "wander_t": 1.2, "captured": False, "latched": False},
    ]

    lasso_state = "idle"
    lasso_target = None
    lasso_timer = 0.0
    break_timer = 0.0

    score = 0
    combo = 1
    combo_window = 2.0
    combo_timer = 0.0
    prev_space = False

    while True:
        dt = clock.tick(60) / 1000
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)

        keys = pygame.key.get_pressed()
        move_speed = 3.1 * dt
        rot_speed = 1.85 * dt

        if keys[pygame.K_LEFT]:
            angle -= rot_speed
        if keys[pygame.K_RIGHT]:
            angle += rot_speed

        dx = math.cos(angle)
        dy = math.sin(angle)

        next_x, next_y = px, py
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

        if not is_wall(next_x, py):
            px = next_x
        if not is_wall(px, next_y):
            py = next_y

        update_veggies(veggies, px, py, dt)

        combo_timer -= dt
        if combo_timer <= 0:
            combo = 1

        if break_timer > 0:
            break_timer -= dt

        space_down = keys[pygame.K_SPACE]
        pressed = space_down and not prev_space
        prev_space = space_down

        # Lasso state machine
        if lasso_state == "idle" and pressed and break_timer <= 0:
            lasso_state = "fired"
            lasso_timer = 0.12
            target_idx, _ = select_lasso_target(px, py, angle, veggies)
            if target_idx is not None:
                lasso_target = target_idx
                veggies[target_idx]["latched"] = True
                lasso_state = "latched"

        elif lasso_state == "fired":
            lasso_timer -= dt
            if lasso_timer <= 0:
                lasso_state = "idle"

        elif lasso_state in ("latched", "reeling"):
            if lasso_target is None or lasso_target >= len(veggies) or veggies[lasso_target]["captured"]:
                lasso_state = "idle"
                lasso_target = None
            else:
                target = veggies[lasso_target]
                tx, ty = target["x"], target["y"]
                tdx, tdy = tx - px, ty - py
                dist = math.hypot(tdx, tdy)

                if dist > 7.0 or not has_line_of_sight(px, py, tx, ty):
                    target["latched"] = False
                    lasso_state = "idle"
                    lasso_target = None
                    break_timer = 0.35
                else:
                    if space_down:
                        lasso_state = "reeling"
                        if dist > 0.001:
                            pull = min(2.6 * dt, dist)
                            nx, ny = tdx / dist, tdy / dist
                            nx_pos = target["x"] - nx * pull
                            ny_pos = target["y"] - ny * pull
                            if not is_wall(nx_pos, ny_pos):
                                target["x"] = nx_pos
                                target["y"] = ny_pos

                        if dist < 1.15:
                            target["captured"] = True
                            target["latched"] = False
                            lasso_target = None
                            lasso_state = "idle"

                            if combo_timer > 0:
                                combo += 1
                            else:
                                combo = 1
                            combo_timer = combo_window
                            score += 100 * combo
                    else:
                        lasso_state = "latched"

        # Draw sky/floor
        screen.fill((80, 120, 170), (0, 0, WIDTH, HALF_H))
        screen.fill((95, 65, 40), (0, HALF_H, WIDTH, HALF_H))

        cast_rays(screen, px, py, angle)
        draw_veggies(screen, px, py, angle, veggies)
        draw_minimap(screen, px, py, veggies)

        # Draw lasso cable on screen if latched/reeling
        if lasso_target is not None and lasso_target < len(veggies):
            target = veggies[lasso_target]
            if not target["captured"]:
                proj = project_sprite(px, py, angle, target["x"], target["y"])
                if proj is not None:
                    tx, ty, _, _ = proj
                    pygame.draw.line(screen, (245, 240, 170), (WIDTH // 2, HEIGHT // 2), (tx, ty), 2)

        pygame.draw.circle(screen, (255, 255, 255), (WIDTH // 2, HEIGHT // 2), 5, 1)
        draw_hud(screen, font, score, combo, lasso_state)

        if all(v["captured"] for v in veggies):
            win = font.render("ALL VEGGIES CAPTURED - PRESS ESC TO QUIT", True, (255, 255, 120))
            screen.blit(win, (WIDTH // 2 - 280, 24))
            if keys[pygame.K_ESCAPE]:
                pygame.quit()
                sys.exit(0)

        pygame.display.flip()


if __name__ == "__main__":
    main()

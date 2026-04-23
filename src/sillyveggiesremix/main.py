import math
import sys

import pygame

WIDTH, HEIGHT = 1280, 720
HALF_H = HEIGHT // 2
FOV = math.pi / 3
NUM_RAYS = 240
MAX_DEPTH = 20
SCALE = WIDTH // NUM_RAYS

WORLD_MAP = [
    "################",
    "#......T.......#",
    "#..####....P...#",
    "#..#..#........#",
    "#..#..####..G..#",
    "#...............",
    "#..R....####....",
    "#.......#..#....",
    "#..####.#..#....",
    "#......P....V...",
    "################",
]


def is_wall(x: float, y: float) -> bool:
    if y < 0 or y >= len(WORLD_MAP) or x < 0 or x >= len(WORLD_MAP[0]):
        return True
    c = WORLD_MAP[int(y)][int(x)]
    return c == "#"


def cast_rays(screen, px, py, angle):
    start_angle = angle - FOV / 2
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


def draw_minimap(screen, px, py):
    tile = 12
    ox, oy = 16, 16
    for j, row in enumerate(WORLD_MAP):
        for i, c in enumerate(row):
            color = (50, 50, 50)
            if c == "#":
                color = (130, 100, 70)  # pallet/tool wall
            elif c in "TRPGV":
                color = (80, 180, 80)  # veggies/props markers
            pygame.draw.rect(screen, color, (ox + i * tile, oy + j * tile, tile - 1, tile - 1))

    pygame.draw.circle(screen, (255, 230, 120), (ox + int(px * tile), oy + int(py * tile)), 4)


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("SillyVeggiesRemix - prototype")
    clock = pygame.time.Clock()

    px, py = 2.5, 2.5
    angle = 0.0

    while True:
        dt = clock.tick(60) / 1000
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)

        keys = pygame.key.get_pressed()
        move_speed = 3.0 * dt
        rot_speed = 1.8 * dt

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

        # sky and dirt floor
        screen.fill((80, 120, 170), (0, 0, WIDTH, HALF_H))
        screen.fill((95, 65, 40), (0, HALF_H, WIDTH, HALF_H))

        cast_rays(screen, px, py, angle)
        draw_minimap(screen, px, py)

        # center reticle (future lasso aim)
        pygame.draw.circle(screen, (255, 255, 255), (WIDTH // 2, HEIGHT // 2), 5, 1)

        pygame.display.flip()


if __name__ == "__main__":
    main()

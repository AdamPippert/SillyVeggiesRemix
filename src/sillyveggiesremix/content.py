import math

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

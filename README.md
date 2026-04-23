# SillyVeggiesRemix

SillyVeggiesRemix is a fast, Doom-inspired 3D lasso shooter where the "ammo" is a rapid-fire rope spit mechanic instead of bullets.

## Core fantasy
- Move through retro-style maze arenas built from farm clutter:
  - wood pallets
  - tractors
  - garden implements
- Hunt animated vegetables by snapping rope-lassos at high speed.
- Chain captures for combo score multipliers.

## Gameplay pillars
1. Doom-style movement and pacing (high speed, strafing, maze pressure)
2. Rope/lasso combat loop (shoot, latch, yank, capture)
3. Farm-dungeon visual identity (industrial agriculture as level geometry)
4. Arcade replayability (combos, time pressure, score chasing)

## Technical direction
- Engine target: Python + pygame prototype first, then evolve to lower-level engine path if needed.
- Visual style: pixelated retro textures, chunky silhouettes, readable color coding.

## Quickstart (prototype)
```bash
cd /Users/adam/Development/SillyVeggiesRemix
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m sillyveggiesremix.main
```

## Roadmap
- [x] Repository scaffold
- [x] Core concept and GDD draft
- [ ] Greybox level with farm obstacles
- [ ] Player movement + look controls
- [ ] Rope projectile + latch logic
- [ ] Vegetable AI + capture states
- [ ] HUD, combos, timer, score

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
# deterministic run seed
python -m sillyveggiesremix.main --seed 1337
# startup load from save file
python -m sillyveggiesremix.main --load-file ./run_save.json
# telemetry output (jsonl)
python -m sillyveggiesremix.main --telemetry-file ./run_telemetry.jsonl
```

## Current prototype controls
- Move: W/A/S/D
- Turn: Left/Right arrows
- Fire lasso: tap Space
- Reel target: hold Space when latched
- Save run: F5
- Load run: F9
- Restart round (after win/death): R
- Quit: Esc

## Current gameplay status
- Carrot enemies patrol/chase and melee attack when close
- Spitter Squash ranged class fires goo projectiles from mid-range
- Wave director scales enemy count/composition and projectile pressure over time
- Multi-room progression is live (Pallet Yard -> Tractor Bay -> Tool Depot)
- Gate-key loop: clear room waves, collect dropped key, unlock next gate
- Seedable deterministic runs and on-demand save/load are now available
- Telemetry log export now records per-run balancing metrics (damage sources, pickups, waves, room reached)
- Core logic now split into modules: `systems.py`, `entities.py`, `content.py`, `runtime.py`, and `rendering.py`
- Deterministic runtime smoke script added: `python scripts/smoke_runtime.py`
- Pickups spawn per wave: health canisters and rope-boost canisters
- Boss Turnip appears every 5th wave with lasso-only weak-point phases (exposed vs armored)
- Boss arena pressure patterns: radial burst phase + focused triple-shot phase
- Boss-transition environment traps now active:
  - armored transition -> tractor sweep lane + rake mine
  - exposed transition -> pallet crusher pulse zone
- Player has HP with brief invulnerability frames after taking damage
- Procedural texture pass added (sky/floor gradients + wall striping)
- Lightweight synthesized audio cues for fire/latch/capture/hit/spit/pickup
- Round states: alive -> dead -> restart loop

## Roadmap
- [x] Repository scaffold
- [x] Core concept and GDD draft
- [x] Greybox level with farm obstacles
- [x] Player movement + look controls
- [x] Rope projectile + latch logic
- [x] Vegetable AI + capture states
- [x] HUD, combos, timer, score
- [x] Add enemy attacks and player damage loop
- [x] Add death/win round restart flow
- [x] Add audio + texture pass
- [x] Add ranged veggie class (Spitter Squash)
- [x] Add wave director (timed waves + scaling)
- [x] Add pickup economy (health + rope boost)
- [x] Add boss veggie encounter
- [x] Add boss-specific environment hazards/traps
- [x] Add multi-room map progression and gate keys
- [x] Add save/load run state and seedable runs
- [x] Add telemetry log export for balancing
- [x] Modularize single-file prototype into systems/entities/content modules
- [x] Split runtime orchestration into dedicated module (`runtime.py`)
- [x] Split rendering orchestration into dedicated module (`rendering.py`)

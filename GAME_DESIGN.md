# SillyVeggiesRemix - Game Design Draft

## 1) High concept
A Doom-like 3D corridor shooter, except combat is non-ballistic: the player spits a rope tongue/lasso that latches onto hostile vegetables and yanks them into capture bins.

## 2) Core loop
1. Navigate maze-like farm dungeon.
2. Spot target veggie type.
3. Fire rope stream and maintain lock.
4. Pull target into capture range.
5. Bank combo by chaining captures quickly.

## 3) Player verbs
- Move: forward/back/strafe/sprint
- Aim: horizontal + vertical look
- Attack: rapid lasso spit (hitscan/projection hybrid)
- Pull: hold to reel in latched target
- Dodge: short burst sidestep

## 4) World grammar
Doom-like topology, farm-themed materials.

Blocking geometry examples:
- stacked wood pallets
- parked tractor bodies
- rakes/shovels as hazard fences
- wheelbarrow chokepoints
- irrigation pipes as low obstacles

## 5) Enemy classes (vegetables)
- Runner Radish: fast, low HP, breaks rope if ignored
- Tank Turnip: high mass, needs sustained reel force
- Spitter Squash: ranged goo attack, interrupts latch
- Swarm Pea Pod: split-unit behavior, combo farm

## 6) Combat model
Rope state machine:
- Idle -> Fired -> Latched -> Reeling -> Captured/Break

Break conditions:
- line-of-sight blocked by obstacle
- max tension exceeded
- player damaged during reel window

## 7) Scoring
- Base capture points per veggie class
- Combo multiplier increases with capture cadence
- Style bonus: long-range latch, no-damage streak, multi-capture window

## 8) MVP implementation order
1. Greybox level and collision
2. FPS movement + camera
3. Lasso fire/attach/reel logic
4. One veggie AI class
5. Score/combo HUD
6. Win/lose round loop

## 9) Art direction
- Clearly Doom-referential combat readability and speed
- Distinct farm-industrial palette: rust red, bale yellow, tool steel blue
- Strong silhouette contrast between obstacles and targets

## 10) Legal/brand note
Use "inspired by classic 90s corridor shooters" in outward-facing text. Keep branding and assets original.

import sys
from pathlib import Path

import pygame

from .entities import AudioBank as EntityAudioBank
from . import content as game_content
from . import rendering as game_rendering
from . import world as game_world
from . import runtime as game_runtime
from . import systems as game_systems
from . import gameplay as game_gameplay

WIDTH, HEIGHT = game_content.WIDTH, game_content.HEIGHT
PLAYER_START = game_content.PLAYER_START
MAX_HP = game_content.MAX_HP
ROPE_BASE_PULL = game_content.ROPE_BASE_PULL
ROPE_BOOST_MULT = game_content.ROPE_BOOST_MULT
ROPE_BOOST_DURATION = game_content.ROPE_BOOST_DURATION
BOSS_WAVE_INTERVAL = game_content.BOSS_WAVE_INTERVAL
ROOM_WAVES_REQUIRED = game_content.ROOM_WAVES_REQUIRED
ROOMS = game_content.ROOMS
SAVE_VERSION = 1
DEFAULT_SAVE_FILE = "run_save.json"
DEFAULT_TELEMETRY_FILE = "run_telemetry.jsonl"



def reset_round():
    px, py, angle = PLAYER_START
    start_wave = 1
    room_index = 0
    room_bounds = ROOMS[room_index]["bounds"]
    game_world.sync_gate_locks(0)
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
        game_world.is_wall,
        game_world.has_line_of_sight,
        game_world.random_open_position,
        {"BOSS_WAVE_INTERVAL": BOSS_WAVE_INTERVAL, "ROPE_BOOST_DURATION": ROPE_BOOST_DURATION},
    )

    combo_window = 2.0

    if args.load_file:
        try:
            state, score, prev_space, run_seed = game_runtime.load_run(Path(args.load_file), SAVE_VERSION, game_world.sync_gate_locks)
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
                        state, score, prev_space, run_seed = game_runtime.load_run(save_path, SAVE_VERSION, game_world.sync_gate_locks)
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
        game_world.sync_gate_locks(state.get("keys", 0))
        current_room = ROOMS[state.get("room_index", 0)]
        room_bounds = current_room["bounds"]

        run_metrics["wave_max"] = max(int(run_metrics.get("wave_max", 1)), int(state.get("wave", 1)))
        run_metrics["room_max"] = max(int(run_metrics.get("room_max", 0)), int(state.get("room_index", 0)))
        run_metrics["score_max"] = max(int(run_metrics.get("score_max", 0)), int(score))

        if state["round_state"] == "alive":
            key_state = {
                "left": keys[pygame.K_LEFT],
                "right": keys[pygame.K_RIGHT],
                "w": keys[pygame.K_w],
                "a": keys[pygame.K_a],
                "s": keys[pygame.K_s],
                "d": keys[pygame.K_d],
                "space": keys[pygame.K_SPACE],
            }
            score, prev_space = game_gameplay.update_alive_state(
                state=state,
                keys=key_state,
                dt=dt,
                room_bounds=room_bounds,
                rooms=ROOMS,
                room_waves_required=ROOM_WAVES_REQUIRED,
                combo_window=combo_window,
                rope_base_pull=ROPE_BASE_PULL,
                rope_boost_mult=ROPE_BOOST_MULT,
                audio=audio,
                run_metrics=run_metrics,
                score=score,
                prev_space=prev_space,
                telemetry_enabled=telemetry_enabled,
                telemetry_path=telemetry_path,
                systems=game_systems,
                runtime=game_runtime,
                world=game_world,
            )
        else:
            prev_space = keys[pygame.K_SPACE]

        game_rendering.draw_background(screen)
        game_rendering.cast_rays(screen, state["px"], state["py"], state["angle"], game_world.is_wall)
        game_rendering.draw_veggies(screen, state["px"], state["py"], state["angle"], state["veggies"])
        game_rendering.draw_pickups(screen, state["px"], state["py"], state["angle"], state["pickups"])
        game_rendering.draw_gates(screen, state["px"], state["py"], state["angle"], game_world.GATE_SEGMENTS, game_world.CURRENT_GATE_LOCKS)
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
            game_world.WORLD_MAP,
            game_world.GATE_SEGMENTS,
            game_world.CURRENT_GATE_LOCKS,
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

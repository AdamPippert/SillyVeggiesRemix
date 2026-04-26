import math


def update_alive_state(
    state,
    keys,
    dt,
    room_bounds,
    rooms,
    room_waves_required,
    combo_window,
    rope_base_pull,
    rope_boost_mult,
    audio,
    run_metrics,
    score,
    prev_space,
    telemetry_enabled,
    telemetry_path,
    systems,
    runtime,
    world,
):
    move_speed = 3.1 * dt
    rot_speed = 1.85 * dt

    if keys["left"]:
        state["angle"] -= rot_speed
    if keys["right"]:
        state["angle"] += rot_speed

    dx = math.cos(state["angle"])
    dy = math.sin(state["angle"])

    next_x, next_y = state["px"], state["py"]
    if keys["w"]:
        next_x += dx * move_speed
        next_y += dy * move_speed
    if keys["s"]:
        next_x -= dx * move_speed
        next_y -= dy * move_speed
    if keys["a"]:
        next_x += dy * move_speed
        next_y -= dx * move_speed
    if keys["d"]:
        next_x -= dy * move_speed
        next_y += dx * move_speed

    if not world.is_wall(next_x, state["py"]):
        state["px"] = next_x
    if not world.is_wall(state["px"], next_y):
        state["py"] = next_y

    new_shots, new_hazards = systems.update_veggies(state["veggies"], state["px"], state["py"], dt, state["wave"], room_bounds)
    if new_shots:
        state["shots"].extend(new_shots)
        audio.play("spit")
    if new_hazards:
        state["hazards"].extend(new_hazards)

    hp_before_shots = state["hp"]
    state["shots"], state["hp"], state["player_invuln"] = systems.update_shots(
        state["shots"], dt, state["px"], state["py"], state["hp"], state["player_invuln"]
    )
    shot_damage = max(0, hp_before_shots - state["hp"])
    if shot_damage > 0:
        runtime.telemetry_add_damage(run_metrics, "spitter_projectile", shot_damage)
        audio.play("player_hit")

    hp_before_haz = state["hp"]
    state["hazards"], state["hp"], state["player_invuln"], hazard_hit = systems.update_hazards(
        state["hazards"], dt, state["px"], state["py"], state["hp"], state["player_invuln"]
    )
    hazard_damage = max(0, hp_before_haz - state["hp"])
    if hazard_damage > 0 or hazard_hit:
        if hazard_damage > 0:
            runtime.telemetry_add_damage(run_metrics, "environment_hazard", hazard_damage)
        audio.play("player_hit")

    state["pickups"], state["hp"], state["rope_boost_timer"], picked_any, keys_found, picked_kinds = systems.update_pickups(
        state["pickups"], dt, state["px"], state["py"], state["hp"], state["rope_boost_timer"]
    )
    for pk, cnt in picked_kinds.items():
        runtime.telemetry_add_pickup(run_metrics, pk, cnt)
    if keys_found > 0:
        run_metrics["gate_keys_collected"] = int(run_metrics.get("gate_keys_collected", 0)) + keys_found
        state["keys"] = min(len(world.GATE_SEGMENTS), state.get("keys", 0) + keys_found)
        new_room_index = min(len(rooms) - 1, state["room_index"] + keys_found)
        if new_room_index != state["room_index"]:
            state["room_index"] = new_room_index
            sx, sy, sa = rooms[state["room_index"]]["spawn"]
            state["px"], state["py"], state["angle"] = sx, sy, sa
            state["room_wave"] = 1
            state["wave"] += 1
            nr_bounds = rooms[state["room_index"]]["bounds"]
            state["veggies"] = systems.spawn_veggies(state["wave"], state["px"], state["py"], nr_bounds)
            state["shots"] = []
            state["hazards"] = []
            state["pickups"].extend(systems.spawn_wave_pickups(state["wave"], state["px"], state["py"], nr_bounds))
            state["wave_spawn_timer"] = 0.0
    if picked_any:
        audio.play("pickup")

    state["combo_timer"] -= dt
    if state["combo_timer"] <= 0:
        state["combo"] = 1

    if state["break_timer"] > 0:
        state["break_timer"] -= dt

    old_hp = state["hp"]
    hp_after_melee, inv_after_melee, melee_hit = systems.apply_enemy_melee(
        state["veggies"], state["px"], state["py"], state["hp"], state["player_invuln"]
    )
    melee_damage = max(0, old_hp - hp_after_melee)
    state["hp"], state["player_invuln"] = hp_after_melee, inv_after_melee
    if state["hp"] < old_hp or melee_hit:
        if melee_damage > 0:
            boss_near = any(v.get("kind") == "boss" and not v.get("captured") and math.hypot(state["px"] - v.get("x", 0), state["py"] - v.get("y", 0)) < 2.2 for v in state["veggies"])
            runtime.telemetry_add_damage(run_metrics, "boss_melee" if boss_near else "carrot_melee", melee_damage)
        audio.play("player_hit")

    if state["hp"] <= 0:
        state["round_state"] = "dead"
        if telemetry_enabled:
            runtime.flush_run_metrics(telemetry_path, run_metrics, "death", state, score)
        if state["lasso_target"] is not None and state["lasso_target"] < len(state["veggies"]):
            state["veggies"][state["lasso_target"]]["latched"] = False
        state["lasso_state"] = "idle"
        state["lasso_target"] = None

    space_down = keys["space"]
    pressed = space_down and not prev_space
    prev_space = space_down

    if state["lasso_state"] == "idle" and pressed and state["break_timer"] <= 0:
        state["lasso_state"] = "fired"
        state["lasso_timer"] = 0.12
        audio.play("lasso_fire")
        target_idx, _ = systems.select_lasso_target(state["px"], state["py"], state["angle"], state["veggies"])
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

            if dist > 7.0 or not world.has_line_of_sight(state["px"], state["py"], tx, ty):
                target["latched"] = False
                state["lasso_state"] = "idle"
                state["lasso_target"] = None
                state["break_timer"] = 0.35
            else:
                if space_down:
                    state["lasso_state"] = "reeling"
                    if dist > 0.001:
                        pull_speed = rope_base_pull * (rope_boost_mult if state["rope_boost_timer"] > 0 else 1.0)
                        pull = min(pull_speed * dt, dist)
                        nx, ny = tdx / dist, tdy / dist
                        nx_pos = target["x"] - nx * pull
                        ny_pos = target["y"] - ny * pull
                        if not world.is_wall(nx_pos, ny_pos):
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
                last_room = len(rooms) - 1
                in_final_room = state["room_index"] >= last_room

                has_gate_key_drop = any(p.get("kind") == "gate_key" for p in state["pickups"])
                if (
                    not in_final_room
                    and state.get("room_wave", 1) >= room_waves_required
                    and not has_gate_key_drop
                ):
                    kx, ky = world.random_open_position(1.4, state["px"], state["py"], room_bounds)
                    state["pickups"].append({"kind": "gate_key", "x": kx, "y": ky, "ttl": 90.0})
                    state["wave_spawn_timer"] = 0.0
                else:
                    state["wave"] += 1
                    state["room_wave"] = state.get("room_wave", 1) + 1
                    state["veggies"] = systems.spawn_veggies(state["wave"], state["px"], state["py"], room_bounds)
                    state["hazards"] = []
                    state["pickups"].extend(systems.spawn_wave_pickups(state["wave"], state["px"], state["py"], room_bounds))
                    state["wave_spawn_timer"] = 0.0

    return score, prev_space

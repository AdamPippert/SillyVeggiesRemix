#!/usr/bin/env python3
import json
import random
import tempfile
from pathlib import Path

from sillyveggiesremix import main
from sillyveggiesremix import runtime
from sillyveggiesremix import world


def fail(msg: str):
    raise SystemExit(f"FAIL: {msg}")


def run():
    with tempfile.TemporaryDirectory(prefix="svr-smoke-") as td:
        root = Path(td)
        save_path = root / "run_save.json"
        telemetry_path = root / "run_telemetry.jsonl"

        seed = 1337
        main.game_systems.configure(
            world.is_wall,
            world.has_line_of_sight,
            world.random_open_position,
            {
                "BOSS_WAVE_INTERVAL": main.BOSS_WAVE_INTERVAL,
                "ROPE_BOOST_DURATION": main.ROPE_BOOST_DURATION,
            },
        )

        random.seed(seed)
        state = main.reset_round()
        score = 42
        prev_space = False

        runtime.save_run(save_path, state, score, prev_space, seed, main.SAVE_VERSION)
        if not save_path.exists():
            fail("save file was not created")

        state1, score1, prev1, seed1 = runtime.load_run(save_path, main.SAVE_VERSION, world.sync_gate_locks)
        r1 = random.random()
        state2, score2, prev2, seed2 = runtime.load_run(save_path, main.SAVE_VERSION, world.sync_gate_locks)
        r2 = random.random()

        if score1 != score or score2 != score:
            fail("score mismatch after load")
        if prev1 != prev_space or prev2 != prev_space:
            fail("prev_space mismatch after load")
        if seed1 != seed or seed2 != seed:
            fail("seed mismatch after load")
        if state1.get("wave") != state2.get("wave"):
            fail("state mismatch across deterministic reload")
        if abs(r1 - r2) > 1e-15:
            fail("RNG state was not restored deterministically")

        metrics = runtime.init_run_metrics(seed)
        runtime.telemetry_add_damage(metrics, "spitter_projectile", 7)
        runtime.telemetry_add_pickup(metrics, "health", 2)
        runtime.flush_run_metrics(telemetry_path, metrics, "smoke", state2, score2)

        lines = telemetry_path.read_text(encoding="utf-8").strip().splitlines()
        if len(lines) != 1:
            fail("telemetry write count mismatch")

        payload = json.loads(lines[0])
        if payload.get("outcome") != "smoke":
            fail("telemetry outcome mismatch")
        if payload.get("damage_taken", {}).get("spitter_projectile") != 7:
            fail("telemetry damage mismatch")
        if payload.get("pickup_counts", {}).get("health") != 2:
            fail("telemetry pickup mismatch")

    print("OK: runtime save/load/telemetry deterministic smoke passed")


if __name__ == "__main__":
    run()

import argparse
import base64
import json
import pickle
import random
import time
from pathlib import Path


def parse_cli_args(default_save_file: str, default_telemetry_file: str):
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--seed", type=str, default=None, help="Seed for deterministic run generation")
    parser.add_argument("--save-file", type=str, default=default_save_file, help="Path for save/load file")
    parser.add_argument("--load-file", type=str, default=None, help="Load this save file on startup")
    parser.add_argument("--fixed-dt", type=float, default=0.0, help="Optional fixed dt for deterministic simulation testing")
    parser.add_argument("--telemetry-file", type=str, default=default_telemetry_file, help="JSONL file to append run telemetry")
    parser.add_argument("--no-telemetry", action="store_true", help="Disable telemetry log writing")
    return parser.parse_args()


def normalize_seed(seed_text):
    if seed_text is None:
        return int(time.time() * 1000) % 1_000_000_000
    try:
        return int(seed_text)
    except ValueError:
        return int.from_bytes(seed_text.encode("utf-8"), "little") % 1_000_000_000


def new_run(reset_round_fn, seed_text=None):
    run_seed = normalize_seed(seed_text)
    random.seed(run_seed)
    state = reset_round_fn()
    return state, run_seed


def save_run(path: Path, state: dict, score: int, prev_space: bool, run_seed: int, save_version: int):
    payload = {
        "version": save_version,
        "game": "sillyveggiesremix",
        "seed": run_seed,
        "saved_at": int(time.time()),
        "score": score,
        "prev_space": prev_space,
        "state": state,
        "rng_state_b64": base64.b64encode(pickle.dumps(random.getstate())).decode("ascii"),
    }

    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")))
    tmp.replace(path)


def load_run(path: Path, save_version: int, sync_gate_locks_fn):
    path = path.expanduser()
    payload = json.loads(path.read_text())

    if payload.get("version") != save_version:
        raise ValueError(f"Unsupported save version: {payload.get('version')}")

    state = payload["state"]
    score = int(payload.get("score", 0))
    prev_space = bool(payload.get("prev_space", False))
    run_seed = int(payload.get("seed", 0))

    lasso_target = state.get("lasso_target")
    veggies = state.get("veggies", [])
    if lasso_target is not None and (not isinstance(lasso_target, int) or lasso_target < 0 or lasso_target >= len(veggies)):
        state["lasso_target"] = None
        state["lasso_state"] = "idle"

    rng_state_b64 = payload.get("rng_state_b64")
    if rng_state_b64:
        rng_state = pickle.loads(base64.b64decode(rng_state_b64.encode("ascii")))
        random.setstate(rng_state)
    else:
        random.seed(run_seed)

    sync_gate_locks_fn(state.get("keys", 0))
    return state, score, prev_space, run_seed


def init_run_metrics(run_seed: int, loaded_from=None):
    return {
        "run_id": f"run-{time.time_ns()}",
        "seed": int(run_seed),
        "loaded_from": loaded_from,
        "started_at": int(time.time()),
        "wave_max": 1,
        "room_max": 0,
        "score_max": 0,
        "damage_taken": {},
        "pickup_counts": {},
        "boss_weakpoint_hits": 0,
        "gate_keys_collected": 0,
        "waves_cleared": 0,
        "finalized": False,
    }


def telemetry_add_damage(metrics: dict, source: str, amount: int):
    if amount <= 0:
        return
    bucket = metrics.setdefault("damage_taken", {})
    bucket[source] = bucket.get(source, 0) + int(amount)


def telemetry_add_pickup(metrics: dict, kind: str, count: int = 1):
    if count <= 0:
        return
    bucket = metrics.setdefault("pickup_counts", {})
    bucket[kind] = bucket.get(kind, 0) + int(count)


def flush_run_metrics(path: Path, metrics: dict, outcome: str, state: dict, score: int):
    if metrics.get("finalized"):
        return

    metrics["finalized"] = True
    payload = {
        "run_id": metrics.get("run_id"),
        "seed": metrics.get("seed"),
        "loaded_from": metrics.get("loaded_from"),
        "started_at": metrics.get("started_at"),
        "ended_at": int(time.time()),
        "outcome": outcome,
        "wave_end": int(state.get("wave", 0)),
        "room_end": int(state.get("room_index", 0)),
        "score_end": int(score),
        "wave_max": int(metrics.get("wave_max", state.get("wave", 0))),
        "room_max": int(metrics.get("room_max", state.get("room_index", 0))),
        "score_max": int(metrics.get("score_max", score)),
        "damage_taken": metrics.get("damage_taken", {}),
        "pickup_counts": metrics.get("pickup_counts", {}),
        "boss_weakpoint_hits": int(metrics.get("boss_weakpoint_hits", 0)),
        "gate_keys_collected": int(metrics.get("gate_keys_collected", 0)),
        "waves_cleared": int(metrics.get("waves_cleared", 0)),
        "hp_end": int(state.get("hp", 0)),
    }

    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, separators=(",", ":")) + "\n")

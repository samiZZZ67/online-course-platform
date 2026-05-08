from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from shutil import copyfile
from threading import RLock
from typing import Any, Callable

from .utils import json_dumps


STORE_LOCK = RLock()


def get_data_dir() -> Path:
    return Path(__file__).resolve().parent / "data"


def get_seed_store_path() -> Path:
    override = os.environ.get("SKILLFORGE_STORE_SEED")
    if override:
        return Path(override)
    return get_data_dir() / "store.seed.json"


def get_store_path() -> Path:
    override = os.environ.get("SKILLFORGE_STORE_PATH")
    if override:
        return Path(override)
    return get_data_dir() / "store.json"


def ensure_store_file() -> Path:
    store_path = get_store_path()
    seed_path = get_seed_store_path()
    store_path.parent.mkdir(parents=True, exist_ok=True)
    if not store_path.exists():
        copyfile(seed_path, store_path)
    return store_path


def read_store() -> dict[str, Any]:
    store_path = ensure_store_file()
    with store_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_store(store: dict[str, Any]) -> None:
    store_path = ensure_store_file()
    temp_path = store_path.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        handle.write(json_dumps(store))
    temp_path.replace(store_path)


def update_store(mutator: Callable[[dict[str, Any]], Any]) -> Any:
    with STORE_LOCK:
        store = read_store()
        result = mutator(store)
        store.setdefault("meta", {})
        store["meta"]["updatedAt"] = datetime.utcnow().isoformat() + "Z"
        write_store(store)
        return result

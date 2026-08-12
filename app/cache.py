"""Disk cache — the most important piece of engineering in this project.

Venue wifi is the number one killer of live demos. Every verdict is keyed by
hash(kind|url|claim) and written to disk, so rehearsals and the real run both
hit cache and return instantly, burning no quota and needing no network.

Warm the cache at the hotel the night before. Together with MOCK=1 that gives
you two independent fallbacks.
"""

import hashlib
import json
import threading
from typing import Any, Optional

from .config import cfg

_lock = threading.Lock()


def key(kind: str, *parts: str) -> str:
    return hashlib.sha256("|".join([kind, *parts]).encode("utf-8")).hexdigest()[:24]


def _path(k: str):
    cfg.cache_dir.mkdir(parents=True, exist_ok=True)
    return cfg.cache_dir / f"{k}.json"


def get(k: str) -> Optional[Any]:
    p = _path(k)
    if not p.exists():
        return None
    try:
        with _lock:
            return json.loads(p.read_text("utf-8"))
    except Exception:
        return None


def put(k: str, value: Any) -> None:
    try:
        with _lock:
            _path(k).write_text(json.dumps(value, ensure_ascii=False), "utf-8")
    except Exception:
        pass  # a cache write must never break the main flow


def clear() -> int:
    n = 0
    if cfg.cache_dir.exists():
        for p in cfg.cache_dir.glob("*.json"):
            p.unlink()
            n += 1
    return n

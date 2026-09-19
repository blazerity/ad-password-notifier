"""Простой файловый lock для исключения параллельных прогонов."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from config import PROJECT_ROOT

DEFAULT_LOCK_PATH = PROJECT_ROOT / "data" / ".run.lock"


class RunInProgressError(RuntimeError):
    """Уже выполняется другой прогон."""


@contextmanager
def run_lock(path: Path | None = None, *, timeout_sec: float = 0) -> Iterator[None]:
    """Захватить exclusive lock. При timeout_sec=0 сразу падает, если занято."""
    lock_path = path or DEFAULT_LOCK_PATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + max(timeout_sec, 0)
    handle = None
    while True:
        try:
            handle = open(lock_path, "x", encoding="utf-8")
            handle.write(f"pid={os.getpid()}\n")
            handle.flush()
            break
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise RunInProgressError("Прогон уже выполняется") from exc
            time.sleep(0.2)
    try:
        yield
    finally:
        if handle is not None:
            handle.close()
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass

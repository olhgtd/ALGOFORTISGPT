"""Local cross-process claims for canonical importer targets.

The claim protects one already-resolved canonical destination.  It deliberately
does not attempt distributed or network-filesystem coordination.
"""

from __future__ import annotations

import hashlib
import os
import time
from contextlib import contextmanager
from pathlib import Path

from engine.data.feeds.path_safety import assert_within_root, path_within_root


CANONICAL_LOCK_DIRECTORY = ".canonical_locks"


def _lock_path_for_target(target: Path, authorized_root: Path) -> Path:
    """Return a safe, stable lock path derived from one canonical target."""
    assert_within_root(target, authorized_root)
    target_identity = str(target.resolve(strict=False)).encode("utf-8")
    digest = hashlib.sha256(target_identity).hexdigest()
    lock_directory = path_within_root(authorized_root, CANONICAL_LOCK_DIRECTORY)
    return path_within_root(lock_directory, f"{digest}.lock")


def _acquire_os_lock(lock_file) -> None:
    """Acquire one advisory OS byte-range lock, retrying while another importer owns it."""
    try:
        import msvcrt
    except ImportError:  # pragma: no cover - current supported local scope is Windows.
        import fcntl

        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        return

    lock_file.seek(0)
    while True:
        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            time.sleep(0.01)


def _release_os_lock(lock_file) -> None:
    try:
        import msvcrt
    except ImportError:  # pragma: no cover - current supported local scope is Windows.
        import fcntl

        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        return

    lock_file.seek(0)
    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)


@contextmanager
def canonical_target_claim(target: Path, authorized_root: Path):
    """Exclusively claim one canonical target for a complete merge-and-commit.

    The OS releases a held file lock when a process terminates.  The small lock
    file may remain as inert identity material; it is not a stale claim.
    """
    lock_path = _lock_path_for_target(target, authorized_root)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    assert_within_root(lock_path, authorized_root)
    with lock_path.open("a+b") as lock_file:
        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"\0")
            lock_file.flush()
            os.fsync(lock_file.fileno())
        _acquire_os_lock(lock_file)
        try:
            yield
        finally:
            _release_os_lock(lock_file)

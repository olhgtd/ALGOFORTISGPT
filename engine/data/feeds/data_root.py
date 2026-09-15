"""§129.8 — Configurable data-root abstraction.

All SentinelX data paths derive from DATA_ROOT.  The default is the
existing repository ``data/`` directory.  A future external root
(e.g. ``D:\\SentinelXData`` or VPS persistent storage) can be configured
by setting the ``SENTINELX_DATA_ROOT`` environment variable.

Path-safety contracts (assert_within_root, path_within_root) remain
authoritative and are unaffected by root relocation.
"""

from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_ROOT = Path("data")

_DATA_ROOT: Path | None = None


def get_data_root() -> Path:
    """Return the authoritative data root path.

    Resolution order:
    1. Explicit set_data_root() call (test injection / programmatic override)
    2. SENTINELX_DATA_ROOT environment variable
    3. Default: ``data/`` relative to the current working directory
    """
    global _DATA_ROOT
    if _DATA_ROOT is not None:
        return _DATA_ROOT
    env = os.environ.get("SENTINELX_DATA_ROOT")
    if env:
        return Path(env)
    return _DEFAULT_ROOT


def set_data_root(root: Path | None) -> None:
    """Set or reset the data root (for testing / programmatic configuration).

    Pass ``None`` to restore default resolution.
    """
    global _DATA_ROOT
    _DATA_ROOT = root


def data_path(*parts: str) -> Path:
    """Convenience: resolve a sub-path under the data root."""
    return get_data_root().joinpath(*parts)

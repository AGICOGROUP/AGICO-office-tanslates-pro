"""Resolve managed runtime executables without assuming one machine's directory layout.

Historical installs placed each runtime one level deeper than the managed runtime does:

    <root>/node/bin/node.exe        (historical)
    <root>/node/node.exe            (managed)

Code that derived a sibling runtime by walking a fixed number of levels from another executable
therefore produced a path that silently does not exist. The failure was invisible because a failed
spawn leaves stdout and stderr empty, so callers reported bare messages such as
``OOXML inspection failed: undefined``. Every adapter must resolve runtimes through this module
instead of rebuilding layout arithmetic; ``tests/test_skill_structure.py`` enforces that.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# Each entry lists every layout that has ever shipped, nearest-to-managed first, so a wrong guess
# degrades to the next candidate rather than to a missing file.
BUNDLED_LAYOUTS: dict[str, tuple[tuple[str, ...], ...]] = {
    "CODEX_NODE": (
        ("node", "node.exe"),
        ("node", "bin", "node.exe"),
        ("node", "node"),
        ("node", "bin", "node"),
    ),
    "CODEX_POWERSHELL": (
        ("pwsh", "pwsh.exe"),
        ("native", "powershell", "pwsh.exe"),
        ("pwsh", "pwsh"),
        ("native", "powershell", "pwsh"),
    ),
}

_LEGACY_DEPENDENCIES = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies"


def runtime_roots() -> list[Path]:
    """Directories that may hold sibling runtimes, ordered nearest first."""
    base = Path(sys.executable).resolve().parent
    roots = [base, *base.parents[:3]]
    if _LEGACY_DEPENDENCIES.is_dir():
        roots.append(_LEGACY_DEPENDENCIES)
    return list(dict.fromkeys(roots))


def find_bundled(env_name: str) -> str | None:
    for root in runtime_roots():
        for parts in BUNDLED_LAYOUTS.get(env_name, ()):
            candidate = root.joinpath(*parts)
            if candidate.is_file():
                return str(candidate)
    return None


def bundled_root() -> Path:
    """Return the runtime root that really holds the bundled sibling runtimes.

    Probing for one exact executable previously decided this, so a layout change made the probe
    fail and silently redirected callers to the legacy cache root, leaving NODE_PATH unset.
    Presence of a runtime directory is the stable signal.
    """
    for root in runtime_roots():
        if (root / "node").is_dir() or (root / "python").is_dir():
            return root
    return _LEGACY_DEPENDENCIES


def resolve_executable(explicit: str | None, env_name: str, fallback: str) -> str:
    """Resolve an executable from an option, its environment override, the bundle, then PATH."""
    candidate = explicit or os.environ.get(env_name)
    if not candidate:
        candidate = find_bundled(env_name) or shutil.which(fallback)
    if not candidate or not Path(candidate).exists():
        raise RuntimeError(f"executable not found; pass the corresponding option or set {env_name}")
    return str(Path(candidate).resolve())

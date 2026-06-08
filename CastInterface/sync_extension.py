#!/usr/bin/env python3
"""Copy CastInterface sources into a live Slicer extension tree (pw45 build).

Usage (from repo or any cwd):
    python CastInterface/sync_extension.py
    python CastInterface/sync_extension.py --dest "C:/path/to/pw45/pw45/CastInterface"

Also mirrors ``Lib/cast_client.py`` into ``cast_api/Lib/`` so the embedded hub
process uses the same chunk-aware client as resource servers.

Restart the Cast hub (Hub tab Stop/Start) and reconnect resource servers after sync.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

SKIP_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "volview-client",
    "vtkjs-worklist-client",
    "OHIF-client",
}
SKIP_FILE_NAMES = {"cast-hub.zip"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def _default_destinations() -> list[Path]:
    env = os.environ.get("SLICER_CAST_EXTENSION", "").strip()
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env))
    local = Path(os.path.expanduser("~")) / "AppData" / "Local" / "slicer.org"
    if local.is_dir():
        for child in sorted(local.iterdir()):
            pw45 = child / "pw45" / "pw45" / "CastInterface"
            if pw45.is_dir():
                candidates.append(pw45)
    return candidates


def _should_copy(rel: Path) -> bool:
    if rel.name in SKIP_FILE_NAMES:
        return False
    if rel.suffix.lower() in SKIP_SUFFIXES:
        return False
    if any(part in SKIP_DIR_NAMES for part in rel.parts):
        return False
    return True


def sync_tree(src: Path, dest: Path) -> int:
    """Copy changed files from ``src`` into ``dest`` (additive overwrite)."""
    count = 0
    for file_path in sorted(src.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(src)
        if not _should_copy(rel):
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file():
            if file_path.read_bytes() == target.read_bytes():
                continue
        shutil.copy2(file_path, target)
        count += 1
        print(f"  {rel}")
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest",
        type=Path,
        help="Slicer CastInterface extension directory (pw45 build output)",
    )
    parser.add_argument(
        "--src",
        type=Path,
        help="CastInterface source root (default: parent of this script)",
    )
    args = parser.parse_args()

    src_root = (args.src or Path(__file__).resolve().parent).resolve()
    if not (src_root / "Lib" / "cast_client.py").is_file():
        print(f"Source Lib not found under {src_root}", file=sys.stderr)
        return 1

    dest_root = args.dest
    if dest_root is None:
        for candidate in _default_destinations():
            if candidate.is_dir():
                dest_root = candidate
                break
    if dest_root is None or not dest_root.is_dir():
        print(
            "No destination found. Pass --dest or set SLICER_CAST_EXTENSION.",
            file=sys.stderr,
        )
        return 1

    dest_root = dest_root.resolve()
    print(f"Sync {src_root} -> {dest_root}")

    copied = 0
    for sub in ("Lib", "cast_api", "Resources"):
        sub_src = src_root / sub
        if not sub_src.is_dir():
            continue
        print(f"[{sub}/]")
        copied += sync_tree(sub_src, dest_root / sub)

    hub_client_src = src_root / "Lib" / "cast_client.py"
    hub_client_dest = src_root / "cast_api" / "Lib" / "cast_client.py"
    hub_client_dest.parent.mkdir(parents=True, exist_ok=True)
    if hub_client_src.read_bytes() != hub_client_dest.read_bytes():
        shutil.copy2(hub_client_src, hub_client_dest)
        copied += 1
        print("  cast_api/Lib/cast_client.py (from Lib/)")

    hub_client_live = dest_root / "cast_api" / "Lib" / "cast_client.py"
    hub_client_live.parent.mkdir(parents=True, exist_ok=True)
    if hub_client_src.read_bytes() != hub_client_live.read_bytes():
        shutil.copy2(hub_client_src, hub_client_live)
        copied += 1
        print("  -> cast_api/Lib/cast_client.py")

    print(f"Done ({copied} file(s) updated). Restart Cast hub + reconnect resource servers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

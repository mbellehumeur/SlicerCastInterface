#!/usr/bin/env python3
"""Create a deployment zip for Cast Hub (zip deploy, no Docker).

Syncs production builds from sibling repos into cast_api client folders, then
packages everything under cast_api/:

- volview-client/  <- VolView/dist  (served at /volview-client/)
- vtkjs-worklist-client/  <- vtk-js/Documentation/.vitepress/dist  (/worklist-client/)
- OHIF-client/  <- Viewers/platform/app/dist  (/ohif-client/)

Run from any directory:
    python CastInterface/cast_api/make_zip.py

Optional:
    python CastInterface/cast_api/make_zip.py --output cast-hub.zip
    python CastInterface/cast_api/make_zip.py --skip-sync

OHIF (Viewers/platform/app): yarn build:cast-hub
    (PUBLIC_URL=/ohif-client/, APP_CONFIG=config/cast.js)

vtk-js docs for hub: VITEPRESS_BASE=/worklist-client/ npm run docs:build
    (or npm run docs:build:cast-hub)
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

EXCLUDED_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
EXCLUDED_FILE_NAMES = {".DS_Store", "cast-hub.zip"}

# (dest folder under cast_api, CLI dest name for --*-dist override key)
CLIENT_SYNC_SPECS = (
    ("volview-client", "volview"),
    ("vtkjs-worklist-client", "vtk"),
    ("OHIF-client", "ohif"),
)

# URL mount path in cast_api.py (may differ from folder name)
MOUNT_PATH_BY_DEST = {
    "volview-client": "/volview-client/",
    "vtkjs-worklist-client": "/worklist-client/",
    "OHIF-client": "/ohif-client/",
}

# Repo folder names and dist paths under each repo (workspace / ProjectWeek45 layout).
REPO_NAMES = {
    "volview": "VolView",
    "vtk": "vtk-js",
    "ohif": "Viewers",
}
DIST_PARTS_UNDER_REPO = {
    "volview": ("dist",),
    "vtk": ("Documentation", ".vitepress", "dist"),
    "ohif": ("platform", "app", "dist"),
}


def find_repo_root(script_dir: Path, repo_name: str) -> Path | None:
    """Locate VolView, vtk-js, or Viewers from cast_api upward (workspace roots)."""
    for base in (script_dir, *script_dir.parents):
        direct = base / repo_name
        if direct.is_dir():
            return direct.resolve()
        under_pw = base / "ProjectWeek45" / repo_name
        if under_pw.is_dir():
            return under_pw.resolve()
    return None


def default_dist_path(script_dir: Path, key: str) -> Path:
    repo_name = REPO_NAMES[key]
    repo_root = find_repo_root(script_dir, repo_name)
    if repo_root is None:
        raise FileNotFoundError(
            f"Could not find {repo_name} repo in workspace "
            f"(searched from {script_dir})"
        )
    return (repo_root / Path(*DIST_PARTS_UNDER_REPO[key])).resolve()


def should_include(path: Path) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDED_DIR_NAMES:
        return False
    if path.name in EXCLUDED_FILE_NAMES:
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    return True


def sync_dist_tree(src: Path, dest: Path) -> int:
    """Replace dest with a copy of src; require src/index.html. Returns file count."""
    index = src / "index.html"
    if not src.is_dir():
        raise FileNotFoundError(f"Source dist not found: {src}")
    if not index.is_file():
        raise FileNotFoundError(f"Source dist missing index.html: {index}")

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    file_count = 0
    for file_path in src.rglob("*"):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(src)
        if not should_include(rel):
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, target)
        file_count += 1
    return file_count


def build_zip(source_dir: Path, output_zip: Path) -> tuple[int, dict[str, int]]:
    file_count = 0
    client_counts: dict[str, int] = {name: 0 for name, _ in CLIENT_SYNC_SPECS}
    with ZipFile(output_zip, "w", ZIP_DEFLATED) as zf:
        for file_path in sorted(source_dir.rglob("*")):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(source_dir)
            if not should_include(rel):
                continue
            arcname = rel.as_posix()
            zf.write(file_path, arcname)
            file_count += 1
            for client_name, _ in CLIENT_SYNC_SPECS:
                prefix = f"{client_name}/"
                if arcname.startswith(prefix):
                    client_counts[client_name] += 1
                    break
    return file_count, client_counts


def resolve_dist_arg(
    script_dir: Path,
    key: str,
    override: str | None,
) -> Path:
    if override:
        path = Path(override).expanduser()
        if path.is_absolute():
            return path.resolve()
        return (script_dir / path).resolve()
    return default_dist_path(script_dir, key)


def main() -> int:
    script_dir = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(
        description="Sync hub SPA clients and create cast_api zip deployment package"
    )
    parser.add_argument(
        "--output",
        default=str(script_dir / "cast-hub.zip"),
        help="Output zip path (default: cast_api/cast-hub.zip)",
    )
    parser.add_argument(
        "--volview-dist",
        default=None,
        help="VolView production dist (default: <VolView>/dist in workspace)",
    )
    parser.add_argument(
        "--vtk-dist",
        default=None,
        help=(
            "vtk-js worklist dist (default: "
            "<vtk-js>/Documentation/.vitepress/dist)"
        ),
    )
    parser.add_argument(
        "--ohif-dist",
        default=None,
        help="OHIF viewer dist (default: Viewers/platform/app/dist)",
    )
    parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="Zip cast_api as-is without copying dist folders",
    )
    args = parser.parse_args()

    dist_overrides = {
        "volview": args.volview_dist,
        "vtk": args.vtk_dist,
        "ohif": args.ohif_dist,
    }

    output_zip = Path(args.output).resolve()
    output_zip.parent.mkdir(parents=True, exist_ok=True)

    if not args.skip_sync:
        for dest_name, key in CLIENT_SYNC_SPECS:
            src = resolve_dist_arg(script_dir, key, dist_overrides[key])
            dest = script_dir / dest_name
            try:
                count = sync_dist_tree(src, dest)
                print(f"Synced {src} -> {dest_name}/ ({count} files)")
            except FileNotFoundError as err:
                print(f"Warning: {err}; skipping {dest_name}/", file=sys.stderr)

    if output_zip.exists():
        output_zip.unlink()

    for dest_name, _ in CLIENT_SYNC_SPECS:
        index = script_dir / dest_name / "index.html"
        if not index.is_file():
            mount = MOUNT_PATH_BY_DEST.get(dest_name, f"/{dest_name}/")
            print(
                f"Warning: {dest_name}/index.html not found; "
                f"hub will not serve {mount}",
                file=sys.stderr,
            )

    file_count, client_counts = build_zip(script_dir, output_zip)
    summary = ", ".join(
        f"{name}={client_counts[name]}" for name, _ in CLIENT_SYNC_SPECS
    )
    print(f"Created {output_zip} ({file_count} files; {summary})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

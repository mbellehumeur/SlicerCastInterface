#!/usr/bin/env python3
"""Create a deployment zip for Cast Hub (zip deploy, no Docker).

Packages everything under cast_api/, including ``volview-client/`` when present
(VolView SPA served at ``/volview-client/``).

Run from any directory:
    python CastInterface/cast_api/make_zip.py

Optional output path:
    python CastInterface/cast_api/make_zip.py --output cast-hub.zip
"""

from __future__ import annotations

import argparse
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
VOLVIEW_CLIENT_DIR = "volview-client"
VOLVIEW_INDEX = Path(VOLVIEW_CLIENT_DIR) / "index.html"


def should_include(path: Path) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDED_DIR_NAMES:
        return False
    if path.name in EXCLUDED_FILE_NAMES:
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    return True


def build_zip(source_dir: Path, output_zip: Path) -> tuple[int, int]:
    file_count = 0
    volview_count = 0
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
            if arcname.startswith(f"{VOLVIEW_CLIENT_DIR}/"):
                volview_count += 1
    return file_count, volview_count


def main() -> int:
    script_dir = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(description="Create cast_api zip deployment package")
    parser.add_argument(
        "--output",
        default=str(script_dir / "cast-hub.zip"),
        help="Output zip path (default: cast_api/cast-hub.zip)",
    )
    args = parser.parse_args()

    output_zip = Path(args.output).resolve()
    output_zip.parent.mkdir(parents=True, exist_ok=True)

    if output_zip.exists():
        output_zip.unlink()

    volview_index = script_dir / VOLVIEW_INDEX
    if not volview_index.is_file():
        print(
            f"Warning: {VOLVIEW_INDEX.as_posix()} not found; "
            "zip will not include VolView (copy build output into volview-client/ first)."
        )

    file_count, volview_count = build_zip(script_dir, output_zip)
    print(f"Created {output_zip} ({file_count} files, {volview_count} under volview-client/)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

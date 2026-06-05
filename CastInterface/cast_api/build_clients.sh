#!/usr/bin/env bash
set -euo pipefail

WS="$(cd "$(dirname "$0")/../../.." && pwd)"

cd "$WS/ProjectWeek45/vtk-js" && npm run buildCast
cd "$WS/ProjectWeek45/VolView" && npm run build
cd "$WS/ProjectWeek45/Viewers/platform/app" && yarn build:cast-hub
cd "$WS/SlicerCastInterface/CastInterface/cast_api" && python make_zip.py

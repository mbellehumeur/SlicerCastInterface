# Cast Hub on Azure Web App

This guide deploys the Cast hub from this repo's `CastInterface/cast_api/cast_api.py`
to Azure App Service. It includes both Linux custom container and zip deploy options.

## Prerequisites

- Azure subscription
- Azure CLI (`az`) logged in (`az login`)
- Docker installed locally
- Files present in `CastInterface/cast_api/`:
  - `cast_api.py`
  - `requirements.txt`
  - `Dockerfile`
  - `start-azure.sh`
  - (optional) bundled SPAs: OHIF at hub root `/`, VolView at `/volview-client/`, worklist at `/worklist-client/`

## 1) Build and push container image to ACR

Run commands from `CastInterface/cast_api/`.

```bash
RG="rg-cast-hub"
LOC="westeurope"
ACR="casthubacr$RANDOM"   # must be globally unique
IMAGE="cast-hub"
TAG="v1"
```

```bash
az group create -n "$RG" -l "$LOC"
az acr create -n "$ACR" -g "$RG" --sku Basic
az acr login -n "$ACR"
docker build -t "$ACR.azurecr.io/$IMAGE:$TAG" .
docker push "$ACR.azurecr.io/$IMAGE:$TAG"
```

## 2) Create Linux App Service and wire image

```bash
PLAN="plan-cast-hub"
APP="cast-hub-$RANDOM"   # must be globally unique
```

```bash
az appservice plan create -g "$RG" -n "$PLAN" --is-linux --sku B1
az webapp create -g "$RG" -p "$PLAN" -n "$APP" \
  --deployment-container-image-name "$ACR.azurecr.io/$IMAGE:$TAG"
```

Grant the web app identity permission to pull from ACR:

```bash
ACR_ID=$(az acr show -n "$ACR" -g "$RG" --query id -o tsv)
WEBAPP_PRINCIPAL_ID=$(az webapp identity assign -g "$RG" -n "$APP" --query principalId -o tsv)
az role assignment create --assignee "$WEBAPP_PRINCIPAL_ID" --scope "$ACR_ID" --role AcrPull
```

Set container source:

```bash
az webapp config container set -g "$RG" -n "$APP" \
  --container-image-name "$ACR.azurecr.io/$IMAGE:$TAG" \
  --container-registry-url "https://$ACR.azurecr.io"
```

## 3) Configure app settings (environment variables)

`start-azure.sh` reads these (and has defaults), but setting them in Azure keeps behavior explicit.

```bash
az webapp config appsettings set -g "$RG" -n "$APP" --settings \
  WEBSITES_PORT=8000 \
  CAST_HUB_WS_KEEPALIVE=true \
  CAST_HUB_WS_KEEPALIVE_INTERVAL_SECONDS=30 \
  CAST_HUB_UVICORN_WS_PING_INTERVAL_SECONDS=20 \
  CAST_HUB_UVICORN_WS_PING_TIMEOUT_SECONDS=20 \
  CAST_HUB_HTTP_PAYLOAD_TTL_SECONDS=300 \
  CAST_HUB_HTTP_PAYLOAD_MAX_TOTAL_BYTES=2147483648 \
  CAST_HUB_FILENAME_POLICY=on
```

If you need a custom file allowlist:

```bash
az webapp config appsettings set -g "$RG" -n "$APP" --settings \
  CAST_HUB_ALLOWED_EXTENSIONS=".dcm,.dicom,.dic,.nii,.nii.gz,.nrrd,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.zip,.tar,.tar.gz,.gz"
```

## 4) Verify deployment

```bash
az webapp log config -g "$RG" -n "$APP" --docker-container-logging filesystem
az webapp log tail -g "$RG" -n "$APP"
```

Get URL:

```bash
echo "https://$APP.azurewebsites.net"
```

Quick checks:

- `GET /api/hub/admin`
- `POST /oauth/authorize`
- WebSocket bind path: `/bind/{endpoint}`

## 5) Update to a new version

```bash
NEW_TAG="v2"
docker build -t "$ACR.azurecr.io/$IMAGE:$NEW_TAG" .
docker push "$ACR.azurecr.io/$IMAGE:$NEW_TAG"

az webapp config container set -g "$RG" -n "$APP" \
  --container-image-name "$ACR.azurecr.io/$IMAGE:$NEW_TAG" \
  --container-registry-url "https://$ACR.azurecr.io"
```

## Notes

- This deployment is for the new cloud Cast hub in this repo (`CastInterface/cast_api`), not VolView.
- To serve VolView, the vtk-js worklist example, and OHIF from the same app, run `make_zip.py` (see Zip deploy) so `volview-client/`, `vtkjs-worklist-client/`, and `OHIF-client/` are populated before packaging.
- For production, add auth hardening, monitoring, and backup/restore strategy.

---

## Zip deploy (no Docker)

Use this path when you want Azure Web App to run Python directly from uploaded files.

### A) Create Linux Python Web App

```bash
RG="rg-cast-hub-zip"
LOC="westeurope"
PLAN="plan-cast-hub-zip"
APP="cast-hub-zip-$RANDOM"   # globally unique

az group create -n "$RG" -l "$LOC"
az appservice plan create -g "$RG" -n "$PLAN" --is-linux --sku B1
az webapp create -g "$RG" -p "$PLAN" -n "$APP" --runtime "PYTHON:3.11"
```

### B) Build frontends and create zip

From each repo (sibling folders under `src/` next to `SlicerCastInterface`):

```bash
# VolView (Cast hubs in config/cast-hubs.json — cloud uses SLICER-HUB-CLOUD)
cd ProjectWeek45/VolView && npm run build

# vtk-js — worklist example (VitePress; synced to vtkjs-worklist-client/)
cd ProjectWeek45/vtk-js
npm run build
npm run docs:generate-api
npm run docs:generate-examples
npm run docs:generate-sidebar
npm run docs:generate-gallery
cross-env VITEPRESS_BASE=/worklist-client/ npm run docs:build
# or: npm run docs:build:cast-hub
npm run docs:build-examples

# OHIF (Viewers) — hub root / + cast.js (routerBasename null, PUBLIC_URL=/)
cd ProjectWeek45/Viewers/platform/app
yarn build:cast-hub
# or: cross-env NODE_ENV=production PUBLIC_URL=/ APP_CONFIG=config/cast.js yarn build
```

From `CastInterface/cast_api`, sync dist folders into client directories and zip:

```bash
cd CastInterface/cast_api
python make_zip.py
```

This copies:

| Source | Into `cast_api/` | Hub URL |
|--------|------------------|---------|
| `VolView/dist` | `volview-client/` | `/volview-client/` |
| `vtk-js/Documentation/.vitepress/dist` | `vtkjs-worklist-client/` | `/worklist-client/` |
| `Viewers/platform/app/dist` | `OHIF-client/` | `/` (hub root) |

Use `--skip-sync` to zip without copying (e.g. clients already synced). Override paths with `--volview-dist`, `--vtk-dist`, or `--ohif-dist`. Defaults locate `VolView`, `vtk-js`, and `Viewers` from the workspace (sibling `ProjectWeek45/` folders or direct repo roots).

### C) Upload zip

```bash
az webapp deploy -g "$RG" -n "$APP" --src-path cast-hub.zip --type zip
```

### D) Configure startup command + app settings

```bash
az webapp config set -g "$RG" -n "$APP" \
  --startup-file "python cast_api.py --host 0.0.0.0 --port \$PORT"

az webapp config appsettings set -g "$RG" -n "$APP" --settings \
  WEBSITES_PORT=8000 \
  CAST_HUB_WS_KEEPALIVE=true \
  CAST_HUB_WS_KEEPALIVE_INTERVAL_SECONDS=30 \
  CAST_HUB_UVICORN_WS_PING_INTERVAL_SECONDS=20 \
  CAST_HUB_UVICORN_WS_PING_TIMEOUT_SECONDS=20 \
  CAST_HUB_HTTP_PAYLOAD_TTL_SECONDS=300 \
  CAST_HUB_HTTP_PAYLOAD_MAX_TOTAL_BYTES=2147483648 \
  CAST_HUB_FILENAME_POLICY=on
```

### E) Verify

```bash
az webapp log tail -g "$RG" -n "$APP"
echo "https://$APP.azurewebsites.net/api/hub/admin"
```

Local smoke-test (after `python cast_api.py` from `cast_api/`):

- `http://127.0.0.1:2018/volview-client/`
- `http://127.0.0.1:2018/worklist-client/`
- `http://127.0.0.1:2018/` (OHIF)

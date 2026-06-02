# TotalSegmentator Cast resource server

## Cast Interface setup

In **Resource Servers**, add or edit a row:

| Field | Value |
|-------|--------|
| Product | `TOTALSEG` |
| Version | `1.0` |
| Description | e.g. Total Segmentator CT segmentation |
| Hub | `SLICER-HUB` or `SLICER-HUB-CLOUD` |
| onMessage script | `CastInterface/Resources/scripts/total_segmentator.py` |

Click **Connect**. The subscriber name (`TOTALSEG-XXXXXX`) appears only in the **hub admin portal**. Hub events subscribed for `TOTALSEG`: `dicom-send`, `nifti-send`.

**Disconnect the AIBRAIN resource server** while testing TotalSegmentator. If both are connected, AIBRAIN immediately publishes the demo `ai-results-mrbrain.dcm` on every `dicom-send` (the Cast module now skips that when multiple resource servers are connected, but using one resource server avoids confusion).

Requires the **TotalSegmentator** Slicer extension (Python package `totalsegmentator`) and `rt_utils` for DICOM RT Struct output.

Inference runs in a **separate `PythonSlicer` process** (TotalSegmentator CLI), matching the Slicer extension. This avoids Windows nnU-Net multiprocessing failures inside the live Slicer GUI process.

## Input expectations

### `dicom-send` (VolView STOW batch)

- VolView sends one **`dicom-send`** per study/series (or slice selection) with **`context.files[]`** and one DICOM body per file (`multipart/related` on `POST /api/hub/`).
- The hub fans out metadata with **`payloadId`** per file; this script calls **`fetch_all_payloads`** before handling.
- All files in the batch are staged under the **`hub.topic`** temp folder, then TotalSegmentator runs once (same pattern as `nifti-send`).
- Send a **complete CT series** (many slices); a single slice is unlikely to work.

### `nifti-send` (e.g. from VolView)

- One compressed NIfTI volume (`.nii.gz`) per message — whole study in one file.
- Segmentation runs when the NIfTI file is received.
- VolView publishes with `target.product.name` = `TOTALSEG`.
- VolView uploads via **multipart `POST /api/hub`**; subscribers download via `GET /api/hub/payloads/{payloadId}`.

## Output

- Uses TotalSegmentator `output_type="dicom"` (DICOM **RT Struct**), typically `segmentations.dcm`.
- Publishes that file back on the **same hub topic** as a `dicom-send` event.

## Logs

Logger name: `CastInterface.TotalSegmentator` (Slicer Python console / log).

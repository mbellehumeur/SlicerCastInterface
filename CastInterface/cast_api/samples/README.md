# Hub sample studies

The Cast hub serves worklist sample studies from this directory. Each immediate
subfolder is one study and must contain:

- `study.json` — catalog metadata (required)
- One or more imaging files referenced by `study.json`

The worklist client loads the catalog from `GET /api/hub/samples` and lists
entries under organization **Hub samples**.

## Example: Test Pattern

```
samples/
  TestPattern/
    study.json
    TG18-CT-1k-01.dcm
    TG18-LN-1k-09.dcm
    TG18-LN-1k-18.dcm
```

`study.json`:

```json
{
  "id": "TestPattern",
  "name": "Test Pattern",
  "description": "TG-18 contrast and luminance test patterns",
  "openMode": "dicom-url",
  "size": "6 MB",
  "files": [
    {
      "fileName": "TG18-CT-1k-01.dcm",
      "mimeType": "application/dicom",
      "label": "TG-18 Contrast (CT)"
    },
    {
      "fileName": "TG18-LN-1k-09.dcm",
      "mimeType": "application/dicom",
      "label": "TG-18 Luminance 09 (LN)"
    },
    {
      "fileName": "TG18-LN-1k-18.dcm",
      "mimeType": "application/dicom",
      "label": "TG-18 Luminance 18 (LN)"
    }
  ]
}
```

For a zip of DICOM instances (e.g. `MyStudy/series.zip`), set
`"openMode": "dicom-url"` so VolView and OHIF expand the archive and ingest
DICOM rather than treating the zip as a generic volume file.

## Rules

- Folder name must match `"id"` in `study.json`.
- Every `files[].fileName` must exist in that folder (no `..` or path segments).
- Optional `openMode`: `dicom-url` for remote `.dcm` or `.zip` DICOM archives;
  omit for NIfTI / generic `files` open (default worklist behavior).
- Optional per-file fields: `mimeType`, `label`, `role` (multi-file volumes).
- Override the samples root with env `CAST_HUB_SAMPLES_DIR`.

Files are downloaded at:

`GET /api/hub/samples/files/{studyId}/{fileName}`

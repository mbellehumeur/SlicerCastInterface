"""IDC Claude Cast resource server — NL prompt to IDC worklist manifest.

Plain Python script (no Qt). Wired via Resource Servers + resource_server_hub
``idc-claude-request`` dispatch. Uses Anthropic API + idc-index locally.

Cast UI: product ``IDCCLAUDE``, script path to this file, Connect.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

LOGGER = logging.getLogger("CastInterface.IDCCLAUDE")

DEFAULT_PRODUCT_NAME = "IDCCLAUDE"
_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR / "idc_skill"

IDC_CITATION = (
    "Fedorov A, et al. National cancer institute imaging data commons. "
    "Radiographics 43 (2023). https://doi.org/10.1148/rg.230180"
)

MAX_STUDIES_DEFAULT = 20
MAX_SLICES_DEFAULT = 300
MAX_SIZE_MB_DEFAULT = 20.0
SOURCE_BUCKET_DEFAULT = "aws"

_job_busy = False


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _read_skill_excerpt() -> str:
    parts: List[str] = []
    for name in ("system_prompt.md", "sql_rules.md"):
        path = _SKILL_DIR / name
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8").strip())
    return "\n\n".join(parts)


def _read_windows_user_env(name: str) -> str:
    """Read a User-level Windows env var from the registry (HKCU\\Environment)."""
    if os.name != "nt":
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value or "").strip()
    except OSError:
        return ""


def _read_anthropic_api_key_file() -> str:
    """Optional fallback: ``%USERPROFILE%\\.cast\\anthropic_api_key`` (one line, not in git)."""
    path = Path.home() / ".cast" / "anthropic_api_key"
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _resolve_anthropic_api_key() -> str:
    """Process env, then Windows User registry, then ``~/.cast/anthropic_api_key``."""
    for candidate in (
        (os.getenv("ANTHROPIC_API_KEY") or "").strip(),
        _read_windows_user_env("ANTHROPIC_API_KEY"),
        _read_anthropic_api_key_file(),
    ):
        if candidate:
            return candidate
    return ""


def build_status_response(provider: Any) -> Dict[str, Any]:
    product_name = getattr(provider, "product_name", "") or DEFAULT_PRODUCT_NAME
    items: List[Dict[str, str]] = [{"key": "availability", "value": "online"}]
    if _job_busy:
        items.append({"key": "job", "value": "running"})
    return {
        "source": "status",
        "product": product_name,
        "items": items,
    }


def s3_uri_to_public_https(url: str) -> str:
    if not url.startswith("s3://"):
        return url
    without_scheme = url[5:]
    bucket, _, key = without_scheme.partition("/")
    if not bucket or not key:
        return url
    encoded_key = "/".join(quote(segment, safe="") for segment in key.split("/"))
    return f"https://{bucket}.s3.amazonaws.com/{encoded_key}"


def format_size_mb(value: float) -> str:
    if value < 1:
        return f"{value:.1f} MB"
    return f"{int(round(value))} MB"


def _strip_sql_comments(sql: str) -> str:
    lines: List[str] = []
    for line in sql.splitlines():
        if "--" in line:
            line = line.split("--", 1)[0]
        lines.append(line)
    text = "\n".join(lines)
    return re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL).strip()


def _extract_sql(text: str) -> str:
    raw = text.strip()
    block = re.search(r"```(?:sql)?\s*(.*?)```", raw, re.IGNORECASE | re.DOTALL)
    if block:
        return block.group(1).strip().rstrip(";")

    for line in raw.splitlines():
        stripped = line.strip()
        if re.match(r"^(WITH|SELECT)\b", stripped, re.IGNORECASE):
            idx = raw.find(line)
            return raw[idx:].strip().rstrip(";")

    match = re.search(r"((?:WITH|SELECT)\b[\s\S]*)", raw, re.IGNORECASE)
    if match:
        return match.group(1).strip().rstrip(";")
    return raw.rstrip(";")


def _validate_sql(sql: str) -> Optional[str]:
    cleaned = _strip_sql_comments(sql)
    normalized = " ".join(cleaned.split())
    upper = normalized.upper()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        return "Generated SQL must be a SELECT query (or WITH ... SELECT)"
    if not re.search(r"\bSELECT\b", upper):
        return "Generated SQL must include a SELECT clause"
    forbidden = ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "CREATE ")
    for token in forbidden:
        if token in upper:
            return f"Forbidden SQL operation: {token.strip()}"
    if not re.search(r"\bLIMIT\b", upper):
        return "Generated SQL must include a LIMIT clause"
    return None


def _call_anthropic_for_sql(prompt: str, max_studies: int) -> str:
    api_key = _resolve_anthropic_api_key()
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Create a key at console.anthropic.com, "
            "then set a Windows User environment variable, or save the key as one line in "
            f"{Path.home() / '.cast' / 'anthropic_api_key'}"
        )
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "anthropic package is not installed. Run: pip install anthropic"
        ) from exc

    model = (os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-6").strip()
    skill_text = _read_skill_excerpt()
    system = (
        f"{skill_text}\n\n"
        "You write DuckDB SQL for idc-index against the `index` table and related "
        "index tables. Return ONLY one DuckDB SQL statement, optionally wrapped in "
        "```sql fences. Use WITH ... SELECT CTEs when helpful. Do not add prose "
        "before or after the SQL. "
        f"The query must return one row per series with StudyInstanceUID, "
        f"SeriesInstanceUID, PatientID, instanceCount, series_size_MB, and "
        f"SeriesDescription when available. Use LIMIT {max_studies} or less at the "
        "outermost query. Prefer joins to volume_geometry_index for 3D CT/MR volumes."
    )
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": prompt.strip()}],
    )
    parts: List[str] = []
    for block in message.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    if not parts:
        raise RuntimeError("Anthropic returned an empty response")
    raw_reply = "\n".join(parts)
    sql = _extract_sql(raw_reply)
    err = _validate_sql(sql)
    if err:
        preview = " ".join(sql.split())[:240]
        LOGGER.warning("IDC Claude SQL validation failed: %s preview=%s", err, preview)
        raise RuntimeError(f"{err}. SQL preview: {preview}")
    LOGGER.info("IDC Claude SQL: %s", " ".join(sql.split())[:500])
    return sql


def _post_process_rows(df, max_studies: int, max_slices: int, max_size_mb: float):
    if df is None or df.empty:
        return df
    work = df.copy()
    if "instanceCount" in work.columns:
        work = work[work["instanceCount"] <= max_slices]
    if "series_size_MB" in work.columns:
        work = work[work["series_size_MB"] < max_size_mb]
    if "StudyInstanceUID" not in work.columns or "SeriesInstanceUID" not in work.columns:
        raise RuntimeError(
            "SQL result must include StudyInstanceUID and SeriesInstanceUID columns"
        )
    sort_cols = [c for c in ("instanceCount", "series_size_MB", "SeriesInstanceUID") if c in work.columns]
    if sort_cols:
        ascending = [False if c == "instanceCount" else True for c in sort_cols]
        work = work.sort_values(sort_cols, ascending=ascending)
    work = work.drop_duplicates(subset=["StudyInstanceUID"], keep="first")
    return work.head(max_studies)


def _build_study_entry(client, row, org_id: str, index: int, source_bucket: str) -> dict:
    series_uid = str(row["SeriesInstanceUID"])
    study_uid = str(row["StudyInstanceUID"])
    patient_id = str(row.get("PatientID") or "").strip()
    slice_count = int(row.get("instanceCount") or 0)
    size_mb = float(row.get("series_size_MB") or 0)
    description_raw = str(row.get("SeriesDescription") or "").strip()
    collection = str(row.get("collection_id") or "").strip()
    label_parts = [p for p in (collection, patient_id, description_raw) if p]
    description = " — ".join(label_parts) if label_parts else f"IDC study {index}"

    urls = client.get_series_file_URLs(
        seriesInstanceUID=series_uid,
        source_bucket_location=source_bucket,
    )
    if slice_count and len(urls) != slice_count:
        LOGGER.warning(
            "idc %s: URL count %d != instanceCount %d",
            org_id,
            len(urls),
            slice_count,
        )
    max_slices = _env_int("IDC_CLAUDE_MAX_SLICES", MAX_SLICES_DEFAULT)
    if len(urls) > max_slices:
        raise ValueError(f"Series {series_uid} has {len(urls)} files (max {max_slices})")

    study_id = f"{org_id}-{index:02d}"
    return {
        "id": study_id,
        "name": f"IDC {index}",
        "description": description,
        "size": format_size_mb(size_mb) if size_mb else f"{len(urls)} DICOM",
        "format": "DICOM",
        "studyInstanceUID": study_uid,
        "seriesInstanceUID": series_uid,
        "sourceBucket": source_bucket,
        "instanceCount": slice_count or len(urls),
        "files": [
            {
                "url": s3_uri_to_public_https(url),
                "fileName": url.rsplit("/", 1)[-1],
            }
            for url in urls
        ],
    }


def _organization_id(prompt: str) -> str:
    digest = hashlib.sha256(f"{prompt}:{time.time()}".encode("utf-8")).hexdigest()
    return f"idc-custom-{digest[:6]}"


def build_idc_claude_response(request_context: Dict[str, Any], provider: Any) -> Dict[str, Any]:
    global _job_busy
    prompt = str(request_context.get("prompt") or "").strip()
    if not prompt:
        return {"source": "idc-claude", "error": "Missing prompt in request context"}

    max_studies = _env_int("IDC_CLAUDE_MAX_STUDIES", MAX_STUDIES_DEFAULT)
    raw_max = request_context.get("maxStudies")
    if raw_max is not None:
        try:
            max_studies = max(1, min(int(raw_max), max_studies))
        except (TypeError, ValueError):
            pass

    organization_label = str(request_context.get("organizationLabel") or "").strip()
    if not organization_label:
        organization_label = prompt[:60] + ("…" if len(prompt) > 60 else "")

    max_slices = _env_int("IDC_CLAUDE_MAX_SLICES", MAX_SLICES_DEFAULT)
    max_size_mb = _env_float("IDC_CLAUDE_MAX_SIZE_MB", MAX_SIZE_MB_DEFAULT)
    source_bucket = (os.getenv("IDC_CLAUDE_SOURCE_BUCKET") or SOURCE_BUCKET_DEFAULT).strip()

    _job_busy = True
    try:
        sql = _call_anthropic_for_sql(prompt, max_studies)
        LOGGER.info("IDC Claude SQL: %s", sql[:500])

        try:
            from idc_index import IDCClient
        except ImportError as exc:
            raise RuntimeError(
                "idc-index is not installed. Run: pip install idc-index"
            ) from exc

        client = IDCClient()
        client.fetch_index("volume_geometry_index")
        rows = client.sql_query(sql)
        rows = _post_process_rows(rows, max_studies, max_slices, max_size_mb)
        if rows is None or rows.empty:
            return {
                "source": "idc-claude",
                "error": "No IDC series matched the query after size filters",
                "prompt": prompt,
                "sql": sql,
            }

        org_id = _organization_id(prompt)
        studies: List[dict] = []
        for index, (_, row) in enumerate(rows.iterrows(), start=1):
            studies.append(_build_study_entry(client, row, org_id, index, source_bucket))

        return {
            "source": "idc-claude",
            "organization": org_id,
            "organizationLabel": organization_label,
            "prompt": prompt,
            "sql": sql,
            "citation": IDC_CITATION,
            "studies": studies,
        }
    except Exception as exc:
        LOGGER.exception("IDC Claude build failed: %s", exc)
        return {
            "source": "idc-claude",
            "error": str(exc),
            "prompt": prompt,
        }
    finally:
        _job_busy = False

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
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

LOGGER = logging.getLogger("CastInterface.IDCCLAUDE")
_LOG_PREFIX = "IDCCLAUDE"


def _format_log_message(message: str, *args: Any) -> str:
    return message % args if args else message


def _idc_log(message: str, *args: Any) -> None:
    text = _format_log_message(message, *args).rstrip()
    if not text:
        return
    line = f"{_LOG_PREFIX}: {text}"
    print(line, flush=True)
    LOGGER.info(text)


def _idc_log_error(message: str, *args: Any) -> None:
    text = _format_log_message(message, *args).rstrip()
    if not text:
        return
    line = f"{_LOG_PREFIX}: {text}"
    print(line, file=sys.stderr, flush=True)
    LOGGER.warning(text)


def _configure_idc_claude_logging() -> None:
    LOGGER.setLevel(logging.INFO)
    if LOGGER.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(f"{_LOG_PREFIX}: %(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.propagate = False


_configure_idc_claude_logging()

DEFAULT_PRODUCT_NAME = "IDCCLAUDE"
_SCRIPT_DIR = Path(__file__).resolve().parent
_CAST_INTERFACE_ROOT = _SCRIPT_DIR.parent.parent
_REPO_ROOT = _CAST_INTERFACE_ROOT.parent
_SKILL_DIR = _SCRIPT_DIR / "idc_skill"

_env_local_cache: Optional[Dict[str, str]] = None

IDC_CITATION = (
    "Fedorov A, et al. National cancer institute imaging data commons. "
    "Radiographics 43 (2023). https://doi.org/10.1148/rg.230180"
)

MAX_STUDIES_DEFAULT = 20
MAX_SLICES_DEFAULT = 300
MAX_SIZE_MB_DEFAULT = 20.0
SOURCE_BUCKET_DEFAULT = "aws"

ACTION_SEARCH = "search"
ACTION_ADD_STUDY = "addStudy"

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


def _env_local_candidate_paths() -> List[Path]:
    paths: List[Path] = []
    for candidate in (_REPO_ROOT / ".env.local", _CAST_INTERFACE_ROOT / ".env.local"):
        if candidate not in paths:
            paths.append(candidate)
    return paths


def _parse_dotenv_text(text: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values


def _read_env_local() -> Dict[str, str]:
    global _env_local_cache
    if _env_local_cache is not None:
        return _env_local_cache

    merged: Dict[str, str] = {}
    loaded_from: List[str] = []
    for path in _env_local_candidate_paths():
        if not path.is_file():
            continue
        try:
            merged.update(_parse_dotenv_text(path.read_text(encoding="utf-8")))
            loaded_from.append(str(path))
        except OSError as exc:
            _idc_log_error("Could not read %s: %s", path, exc)

    _env_local_cache = merged
    if loaded_from:
        _idc_log("Loaded .env.local from %s", ", ".join(loaded_from))
    return merged


def _env_local_value(name: str) -> str:
    return (_read_env_local().get(name) or "").strip()


def _env_local_source_label() -> str:
    for path in _env_local_candidate_paths():
        if path.is_file() and (_env_local_value("ANTHROPIC_API_KEY")):
            return str(path)
    return ".env.local"


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
    """``.env.local``, process env, Windows User registry, then ``~/.cast/anthropic_api_key``."""
    key, _source = _resolve_anthropic_api_key_with_source()
    return key


def _resolve_anthropic_api_key_with_source() -> tuple[str, str]:
    """Return ``(api_key, source_label)`` for logging (never log the key itself).

    Local dev: ``.env.local`` at repo root (same ``ANTHROPIC_API_KEY`` name as Azure).
    Azure / shells: process environment when no ``.env.local`` key is set.
    """
    local_key = _env_local_value("ANTHROPIC_API_KEY")
    if local_key:
        return local_key, _env_local_source_label()

    process_env = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if process_env:
        return process_env, "process environment"

    registry_env = _read_windows_user_env("ANTHROPIC_API_KEY")
    if registry_env:
        return registry_env, "Windows User registry"

    file_env = _read_anthropic_api_key_file()
    if file_env:
        return file_env, str(Path.home() / ".cast" / "anthropic_api_key")
    return "", ""


def _anthropic_api_key_hint() -> str:
    example = _REPO_ROOT / ".env.local.example"
    return (
        "Set ANTHROPIC_API_KEY in .env.local (copy from .env.local.example), "
        "Azure App Service application settings, or Windows User environment variables."
        f" Example template: {example}"
    )


def _resolve_anthropic_model() -> str:
    for candidate in (
        _env_local_value("ANTHROPIC_MODEL"),
        (os.getenv("ANTHROPIC_MODEL") or "").strip(),
    ):
        if candidate:
            return candidate
    return "claude-sonnet-4-6"


def _log_text_preview(label: str, text: str, max_chars: int = 240) -> None:
    compact = " ".join(str(text or "").split())
    if len(compact) <= max_chars:
        _idc_log("%s: %s", label, compact)
        return
    _idc_log("%s (%d chars): %s…", label, len(compact), compact[:max_chars])


def _runtime_error_from_anthropic(exc: BaseException) -> RuntimeError:
    name = exc.__class__.__name__
    message = str(exc).lower()
    if name == "AuthenticationError" or "authentication_error" in message or "401" in message:
        return RuntimeError(
            f"Anthropic API key is missing or invalid. {_anthropic_api_key_hint()}"
        )
    return RuntimeError(f"Anthropic request failed: {exc}")


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
    api_key, key_source = _resolve_anthropic_api_key_with_source()
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Create a key at console.anthropic.com, "
            f"then {_anthropic_api_key_hint()}"
        )
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "anthropic package is not installed. Run: pip install anthropic"
        ) from exc

    model = _resolve_anthropic_model()
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
    user_message = prompt.strip()
    _idc_log(
        "Anthropic request model=%s max_tokens=%d key_source=%s key_len=%d "
        "user_chars=%d system_chars=%d",
        model,
        2048,
        key_source,
        len(api_key),
        len(user_message),
        len(system),
    )
    _log_text_preview("Anthropic user message", user_message)
    try:
        message = client.messages.create(
            model=model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as exc:
        raise _runtime_error_from_anthropic(exc) from exc
    parts: List[str] = []
    for block in message.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    if not parts:
        raise RuntimeError("Anthropic returned an empty response")
    raw_reply = "\n".join(parts)
    _log_text_preview("Anthropic raw reply", raw_reply, max_chars=500)
    sql = _extract_sql(raw_reply)
    err = _validate_sql(sql)
    if err:
        preview = " ".join(sql.split())[:240]
        _idc_log_error("SQL validation failed: %s preview=%s", err, preview)
        raise RuntimeError(f"{err}. SQL preview: {preview}")
    _idc_log("Extracted SQL: %s", " ".join(sql.split())[:500])
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


def _study_metadata_from_row(row, org_id: str, index: int, source_bucket: str) -> dict:
    series_uid = str(row["SeriesInstanceUID"])
    study_uid = str(row["StudyInstanceUID"])
    patient_id = str(row.get("PatientID") or "").strip()
    slice_count = int(row.get("instanceCount") or 0)
    size_mb = float(row.get("series_size_MB") or 0)
    description_raw = str(row.get("SeriesDescription") or "").strip()
    collection = str(row.get("collection_id") or "").strip()
    label_parts = [p for p in (collection, patient_id, description_raw) if p]
    description = " — ".join(label_parts) if label_parts else f"IDC study {index}"

    study_id = f"{org_id}-{index:02d}"
    return {
        "id": study_id,
        "name": f"IDC {index}",
        "description": description,
        "size": format_size_mb(size_mb) if size_mb else f"{slice_count or '?'} DICOM",
        "format": "DICOM",
        "studyInstanceUID": study_uid,
        "seriesInstanceUID": series_uid,
        "sourceBucket": source_bucket,
        "instanceCount": slice_count,
        "organization": org_id,
    }


def _attach_series_urls(client, study: Dict[str, Any], source_bucket: str) -> dict:
    series_uid = str(study.get("seriesInstanceUID") or "").strip()
    if not series_uid:
        raise ValueError("Missing seriesInstanceUID")

    slice_count = int(study.get("instanceCount") or 0)
    size_mb_raw = study.get("size")
    size_mb = 0.0
    if isinstance(size_mb_raw, (int, float)):
        size_mb = float(size_mb_raw)
    elif isinstance(size_mb_raw, str) and size_mb_raw.endswith(" MB"):
        try:
            size_mb = float(size_mb_raw.replace(" MB", "").strip())
        except ValueError:
            size_mb = 0.0

    urls = client.get_series_file_URLs(
        seriesInstanceUID=series_uid,
        source_bucket_location=source_bucket,
    )
    if slice_count and len(urls) != slice_count:
        _idc_log_error(
            "idc %s: URL count %d != instanceCount %d",
            study.get("id") or series_uid,
            len(urls),
            slice_count,
        )
    max_slices = _env_int("IDC_CLAUDE_MAX_SLICES", MAX_SLICES_DEFAULT)
    if len(urls) > max_slices:
        raise ValueError(f"Series {series_uid} has {len(urls)} files (max {max_slices})")

    files = [
        {
            "url": s3_uri_to_public_https(url),
            "fileName": url.rsplit("/", 1)[-1],
        }
        for url in urls
    ]
    return {
        **study,
        "instanceCount": slice_count or len(urls),
        "size": format_size_mb(size_mb) if size_mb else f"{len(urls)} DICOM",
        "files": files,
    }



def _resolve_idc_client():
    try:
        from idc_index import IDCClient
    except ImportError as exc:
        raise RuntimeError(
            "idc-index is not installed. Run: pip install idc-index"
        ) from exc
    return IDCClient()


def _search_idc_studies(
    request_context: Dict[str, Any],
    max_studies: int,
    max_slices: int,
    max_size_mb: float,
    source_bucket: str,
) -> Dict[str, Any]:
    prompt = str(request_context.get("prompt") or "").strip()
    if not prompt:
        return {"source": "idc-claude", "error": "Missing prompt in request context"}

    organization_label = str(request_context.get("organizationLabel") or "").strip()
    if not organization_label:
        organization_label = prompt[:60] + ("…" if len(prompt) > 60 else "")

    _idc_log(
        "search start prompt=%r max_studies=%d label=%r",
        prompt,
        max_studies,
        organization_label,
    )
    sql = _call_anthropic_for_sql(prompt, max_studies)

    client = _resolve_idc_client()
    client.fetch_index("volume_geometry_index")
    rows = client.sql_query(sql)
    rows = _post_process_rows(rows, max_studies, max_slices, max_size_mb)
    if rows is None or rows.empty:
        _idc_log("search matched 0 series after filters")
        return {
            "source": "idc-claude",
            "action": ACTION_SEARCH,
            "error": "No IDC series matched the query after size filters",
            "prompt": prompt,
            "sql": sql,
        }

    org_id = _organization_id(prompt)
    studies: List[dict] = []
    for index, (_, row) in enumerate(rows.iterrows(), start=1):
        studies.append(_study_metadata_from_row(row, org_id, index, source_bucket))

    _idc_log("search done organization=%s studies=%d", org_id, len(studies))
    return {
        "source": "idc-claude",
        "action": ACTION_SEARCH,
        "organization": org_id,
        "organizationLabel": organization_label,
        "prompt": prompt,
        "sql": sql,
        "citation": IDC_CITATION,
        "studies": studies,
    }


def _add_idc_study_with_urls(
    request_context: Dict[str, Any],
    source_bucket: str,
) -> Dict[str, Any]:
    study_in = request_context.get("study")
    if not isinstance(study_in, dict):
        return {"source": "idc-claude", "error": "Missing study in request context"}

    series_uid = str(study_in.get("seriesInstanceUID") or "").strip()
    if not series_uid:
        return {"source": "idc-claude", "error": "Missing seriesInstanceUID in study"}

    bucket = str(study_in.get("sourceBucket") or source_bucket).strip() or source_bucket
    organization = str(
        request_context.get("organization") or study_in.get("organization") or ""
    ).strip()

    _idc_log(
        "addStudy start organization=%s series=%s study_id=%s",
        organization,
        series_uid,
        study_in.get("id") or "",
    )
    client = _resolve_idc_client()
    study = _attach_series_urls(client, dict(study_in), bucket)
    if organization:
        study["organization"] = organization

    file_count = len(study.get("files") or [])
    _idc_log(
        "addStudy done study_id=%s files=%d",
        study.get("id") or series_uid,
        file_count,
    )
    return {
        "source": "idc-claude",
        "action": ACTION_ADD_STUDY,
        "organization": organization,
        "study": study,
    }


def _organization_id(prompt: str) -> str:
    digest = hashlib.sha256(f"{prompt}:{time.time()}".encode("utf-8")).hexdigest()
    return f"idc-custom-{digest[:6]}"


def build_idc_claude_response(request_context: Dict[str, Any], provider: Any) -> Dict[str, Any]:
    global _job_busy, _env_local_cache
    _env_local_cache = None
    action = str(request_context.get("action") or ACTION_SEARCH).strip() or ACTION_SEARCH

    max_studies = _env_int("IDC_CLAUDE_MAX_STUDIES", MAX_STUDIES_DEFAULT)
    raw_max = request_context.get("maxStudies")
    if raw_max is not None:
        try:
            max_studies = max(1, min(int(raw_max), max_studies))
        except (TypeError, ValueError):
            pass

    max_slices = _env_int("IDC_CLAUDE_MAX_SLICES", MAX_SLICES_DEFAULT)
    max_size_mb = _env_float("IDC_CLAUDE_MAX_SIZE_MB", MAX_SIZE_MB_DEFAULT)
    source_bucket = (os.getenv("IDC_CLAUDE_SOURCE_BUCKET") or SOURCE_BUCKET_DEFAULT).strip()

    prompt = str(request_context.get("prompt") or "").strip()
    _idc_log(
        "idc-claude-request action=%s max_studies=%d context_keys=%s",
        action,
        max_studies,
        sorted(request_context.keys()),
    )
    _job_busy = True
    try:
        if action == ACTION_ADD_STUDY:
            return _add_idc_study_with_urls(request_context, source_bucket)
        return _search_idc_studies(
            request_context,
            max_studies,
            max_slices,
            max_size_mb,
            source_bucket,
        )
    except Exception as exc:
        _idc_log_error("build failed: %s", exc)
        payload: Dict[str, Any] = {
            "source": "idc-claude",
            "error": str(exc),
        }
        if prompt:
            payload["prompt"] = prompt
        if action:
            payload["action"] = action
        return payload
    finally:
        _job_busy = False

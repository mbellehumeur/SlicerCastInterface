"""TotalSegmentator Cast onMessage - single-threaded variant.

Functionally equivalent to ``total_segmentator.py`` but with no thread spawn
and no module-level staging lock. Mirrors the simple shape of
``aibrain_on_message.py``: ``onMessage`` stages, runs TotalSegmentator
inline, publishes, and returns.

Why this is safe (cross-references to ``Lib/resource_server_hub.py``):

- For ``dicom-send`` and ``nifti-send``, ``_dispatch_resource_server_on_message``
  already invokes the handler via ``asyncio.to_thread`` (one worker thread),
  off both the hub asyncio loop and the Slicer Qt UI thread.
- The hub does **not** call ``fetch_all_payloads`` before those events; bytes are
  streamed in parallel (25 concurrent GETs by default) directly into the job
  ``input/`` directory via ``extract_all_*_send_files_to_dir`` (PNG/JPG
  ``*-request`` handling is unchanged).
- The hub message loop ``await``s one handler at a time per provider, so
  ``onMessage`` calls for one provider are naturally serialized.
- The WebSocket reader runs as a separate asyncio task on the hub thread
  and keeps draining frames into ``message_queue`` while the worker is
  busy; WS receive is not blocked by TotalSegmentator subprocess execution.

Behavior differences vs ``total_segmentator.py``:

- A second ``nifti-send`` for the same topic that arrives while a previous
  job is still running is **queued and run** sequentially instead of being
  skipped (the old code dropped it via ``processing=True``). Messages are
  no longer dropped.

Cast UI (Resource Servers): point the script path at this file.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from Lib.cast_provider_runtime import (
    CastPayloadTruncatedError,
    extract_all_dicom_send_files_to_dir,
    extract_all_nifti_send_files_to_dir,
    get_active_resource_server_products,
    publish_dicom_send_file,
    publish_nifti_send_file,
    record_dicom_send_received,
    record_nifti_send_received,
)

_LOG_PREFIX = "TotalSegmentator"


def _format_message(message: str, *args: Any) -> str:
    return message % args if args else message


def _on_slicer_main_thread(fn: Any) -> None:
    """Run ``fn`` on the Qt GUI thread (safe for ``showConsoleMessage``)."""
    try:
        import qt

        qt.QTimer.singleShot(0, fn)
    except ImportError:
        fn()


def _console_log(message: str, *args: Any) -> None:
    """Normal output in the Slicer Python console (default/white text)."""
    text = _format_message(message, *args).rstrip()
    if not text:
        return
    print(f"{_LOG_PREFIX}: {text}")


def _console_error(message: str, *args: Any) -> None:
    """Errors in the Slicer Python console (red text)."""
    text = _format_message(message, *args).rstrip()
    if not text:
        return
    line = f"{_LOG_PREFIX}: {text}"

    def _show_red() -> None:
        try:
            import slicer

            slicer.app.showConsoleMessage(line, True)
        except ImportError:
            print(line, file=sys.stderr)

    try:
        import slicer  # noqa: F401

        _on_slicer_main_thread(_show_red)
    except ImportError:
        print(line, file=sys.stderr)


def _console_exception(message: str, *args: Any) -> None:
    _console_error(message, *args)
    for exc_line in traceback.format_exc().splitlines():
        _console_error(exc_line)


DEFAULT_PRODUCT_NAME = "TOTALSEG"
_DICOM_SEND_EVENT = "dicom-send"
_NIFTI_SEND_EVENT = "nifti-send"
TS_TASK = "total"
# ``--fast`` breaks DICOM RT Struct export (mask z vs series slice count).
TS_FAST = False
TS_MULTILABEL = True
OUTPUT_DICOM_NAME = "segmentations.dcm"
OUTPUT_NIFTI_NAME = "segmentations.nii.gz"


def _safe_topic_dir_name(topic: str) -> str:
    safe = re.sub(r"[^\w.\-]+", "_", topic.strip())
    return safe or "topic"


def _allocate_job_dirs(topic: str) -> Tuple[Path, Path, Path]:
    """Create ``cast-totalseg-jobs/<topic>-<stamp>/{input,output}``."""
    stamp = int(time.time() * 1000)
    job_dir = (
        Path(tempfile.gettempdir())
        / "cast-totalseg-jobs"
        / f"{_safe_topic_dir_name(topic)}-{stamp}"
    )
    job_input = job_dir / "input"
    job_output = job_dir / "output"
    job_input.mkdir(parents=True, exist_ok=True)
    job_output.mkdir(parents=True, exist_ok=True)
    return job_dir, job_input, job_output


def _redact_message_for_log(message: Dict[str, Any]) -> Dict[str, Any]:
    """Copy a Cast message for logging with inline byte/base64 fields redacted."""

    def _redact_value(value: Any) -> Any:
        if isinstance(value, (bytes, bytearray, memoryview)):
            return f"<bytes len={len(value)}>"
        if isinstance(value, dict):
            out: Dict[str, Any] = {}
            for key, item in value.items():
                if key == "data" and item is not None:
                    if isinstance(item, str):
                        out[key] = f"<base64 len={len(item)}>"
                    else:
                        out[key] = _redact_value(item)
                else:
                    out[key] = _redact_value(item)
            return out
        if isinstance(value, list):
            return [_redact_value(item) for item in value]
        return value

    return _redact_value(message)


def onMessage(message: Dict[str, Any], provider: Any) -> None:
    _console_log(
        "onMessage: received %s",
        json.dumps(_redact_message_for_log(message), default=str),
    )
    event = message.get("event") or {}
    hub_event = event.get("hub.event")
    if hub_event == _NIFTI_SEND_EVENT:
        _on_nifti_send(message, event, provider)
        return
    if hub_event != _DICOM_SEND_EVENT:
        return
    _on_dicom_send(message, event, provider)


def _on_dicom_send(
    message: Dict[str, Any], event: Dict[str, Any], provider: Any
) -> None:
    topic = (event.get("hub.topic") or "").strip()
    if not topic:
        _console_error("onMessage: dicom-send missing hub.topic")
        return

    product_name = getattr(provider, "product_name", "") or DEFAULT_PRODUCT_NAME
    files = (event.get("context") or {}).get("files") or []
    if isinstance(files, list):
        url_count = sum(
            1
            for entry in files
            if isinstance(entry, dict)
            and isinstance(entry.get("url"), str)
            and entry["url"].strip()
        )
        payload_count = sum(
            1
            for entry in files
            if isinstance(entry, dict)
            and isinstance(entry.get("payloadId"), str)
            and entry["payloadId"].strip()
            and entry.get("data") is None
        )
        _console_log(
            "onMessage: dicom-send download start id=%s topic=%s files=%d "
            "url=%d payloadId=%d product=%s",
            message.get("id", ""),
            topic,
            len(files),
            url_count,
            payload_count,
            product_name,
        )

    job_dir, job_input, job_output = _allocate_job_dirs(topic)
    _console_log(
        "onMessage: streaming download to %s id=%s topic=%s",
        job_input,
        message.get("id", ""),
        topic,
    )
    try:
        file_count, total_bytes = extract_all_dicom_send_files_to_dir(
            message, job_input, product_name
        )
    except CastPayloadTruncatedError as exc:
        _console_error(
            "onMessage: dicom-send download failed id=%s topic=%s: %s",
            message.get("id", ""),
            topic,
            exc,
        )
        shutil.rmtree(job_dir, ignore_errors=True)
        return
    if file_count < 1:
        _console_error(
            "onMessage: no DICOM payload id=%s topic=%s",
            message.get("id", ""),
            topic,
        )
        shutil.rmtree(job_dir, ignore_errors=True)
        return
    record_dicom_send_received(topic, total_bytes)
    _console_log(
        "onMessage: dicom-send id=%s topic=%s files=%d bytes=%d",
        message.get("id", ""),
        topic,
        file_count,
        total_bytes,
    )

    _run_segmentation_job_body(
        topic, product_name, job_input, job_output, job_dir, _DICOM_SEND_EVENT
    )


def _on_nifti_send(
    message: Dict[str, Any], event: Dict[str, Any], provider: Any
) -> None:
    topic = (event.get("hub.topic") or "").strip()
    if not topic:
        _console_error("onMessage: nifti-send missing hub.topic")
        return

    product_name = getattr(provider, "product_name", "") or DEFAULT_PRODUCT_NAME
    files = (event.get("context") or {}).get("files") or []
    if isinstance(files, list):
        url_count = sum(
            1
            for entry in files
            if isinstance(entry, dict)
            and isinstance(entry.get("url"), str)
            and entry["url"].strip()
        )
        payload_count = sum(
            1
            for entry in files
            if isinstance(entry, dict)
            and isinstance(entry.get("payloadId"), str)
            and entry["payloadId"].strip()
            and entry.get("data") is None
        )
        _console_log(
            "onMessage: nifti-send download start id=%s topic=%s files=%d "
            "url=%d payloadId=%d product=%s",
            message.get("id", ""),
            topic,
            len(files),
            url_count,
            payload_count,
            product_name,
        )

    job_dir, job_input, job_output = _allocate_job_dirs(topic)
    _console_log(
        "onMessage: streaming download to %s id=%s topic=%s",
        job_input,
        message.get("id", ""),
        topic,
    )
    try:
        file_count, total_bytes = extract_all_nifti_send_files_to_dir(
            message, job_input, product_name
        )
    except CastPayloadTruncatedError as exc:
        _console_error(
            "onMessage: nifti-send download failed id=%s topic=%s: %s",
            message.get("id", ""),
            topic,
            exc,
        )
        shutil.rmtree(job_dir, ignore_errors=True)
        return
    if file_count < 1:
        _console_error(
            "onMessage: no NIfTI payload id=%s topic=%s",
            message.get("id", ""),
            topic,
        )
        shutil.rmtree(job_dir, ignore_errors=True)
        return
    record_nifti_send_received(topic, total_bytes)
    _console_log(
        "onMessage: nifti-send id=%s topic=%s files=%d bytes=%d",
        message.get("id", ""),
        topic,
        file_count,
        total_bytes,
    )

    _run_segmentation_job_body(
        topic, product_name, job_input, job_output, job_dir, _NIFTI_SEND_EVENT
    )


def _run_segmentation_job_body(
    topic: str,
    product_name: str,
    job_input: Path,
    job_output: Path,
    job_dir: Path,
    hub_event: str,
) -> None:
    output_file: Optional[Path] = None
    try:
        staged_count = _count_input_files(job_input)
        if staged_count < 1:
            _console_error(
                "no input files for topic=%s in %s",
                topic,
                job_input,
            )
            return

        _console_log(
            "starting segmentation topic=%s input=%s files=%d",
            topic,
            job_input,
            staged_count,
        )
        cli_input = _cli_input_path(job_input, hub_event)

        output_file = _run_totalsegmentator(cli_input, job_output, hub_event)
        if not output_file:
            _console_error(
                "no output for hub.event=%s topic=%s (job dir kept: %s)",
                hub_event,
                topic,
                job_dir,
            )
            return

        _console_log(
            "output hub.event=%s topic=%s: %s",
            hub_event,
            topic,
            output_file,
        )
        if hub_event == _NIFTI_SEND_EVENT:
            published = publish_nifti_send_file(
                product_name, topic, str(output_file)
            )
        else:
            published = publish_dicom_send_file(
                product_name, topic, str(output_file)
            )
        if published:
            _console_log(
                "published %s to topic=%s product=%s",
                output_file,
                topic,
                product_name,
            )
        else:
            _console_error(
                "failed to publish %s topic=%s product=%s (active: %s)",
                output_file,
                topic,
                product_name,
                ", ".join(get_active_resource_server_products()) or "(none)",
            )
    except Exception as exc:
        _console_exception("job failed topic=%s: %s", topic, exc)
    finally:
        if job_dir and job_dir.is_dir():
            if output_file and output_file.is_file():
                try:
                    shutil.rmtree(job_dir)
                except OSError as exc:
                    _console_error("cleanup failed: %s", exc)
            else:
                _console_log(
                    "keeping job dir for inspection: %s", job_dir
                )


def _count_input_files(input_dir: Path) -> int:
    if not input_dir.is_dir():
        return 0
    return sum(
        1
        for path in input_dir.rglob("*")
        if path.is_file() and not path.name.startswith(".")
    )


def _cli_input_path(input_dir: Path, hub_event: str) -> Path:
    """Resolve TotalSegmentator ``-i`` from Cast ``hub.event``."""
    if hub_event == _NIFTI_SEND_EVENT:
        for pattern in ("*.nii.gz", "*.nii", "*.nhdr", "*.nrrd"):
            matches = sorted(input_dir.glob(pattern))
            if matches:
                if len(matches) > 1:
                    _console_log(
                        "multiple volume files under %s, using %s",
                        input_dir,
                        matches[0],
                    )
                return matches[0]
        raise FileNotFoundError(f"No NIfTI/volume file under {input_dir}")
    if hub_event == _DICOM_SEND_EVENT:
        return input_dir
    raise ValueError(f"Unsupported hub.event for segmentation: {hub_event!r}")


def _cli_output_path(output_dir: Path, hub_event: str) -> Path:
    """Resolve TotalSegmentator ``-o`` from Cast ``hub.event``."""
    if hub_event == _NIFTI_SEND_EVENT:
        return output_dir / OUTPUT_NIFTI_NAME
    if hub_event == _DICOM_SEND_EVENT:
        return output_dir / OUTPUT_DICOM_NAME
    raise ValueError(f"Unsupported hub.event for segmentation: {hub_event!r}")


def _ts_executable_name(name: str) -> str:
    return name + ".exe" if os.name == "nt" else name


def _total_segmentator_launch_command() -> Optional[list[str]]:
    """PythonSlicer + TotalSegmentator CLI (same pattern as Slicer extension)."""
    python_slicer = shutil.which("PythonSlicer")
    if not python_slicer:
        _console_error("PythonSlicer not found on PATH")
        return None

    scripts_dir = sysconfig.get_path("scripts")
    ts_script = os.path.join(
        scripts_dir, _ts_executable_name("TotalSegmentator")
    )
    if not os.path.isfile(ts_script):
        _console_error(
            "CLI not found at %s (install TotalSegmentator extension)",
            ts_script,
        )
        return None

    return [python_slicer, ts_script]


def _total_segmentator_cli_options(
    input_path: Path, output_path: Path, device: str, hub_event: str
) -> list[str]:
    options = [
        "-i",
        str(input_path.resolve()),
        "-o",
        str(output_path.resolve()),
        "--task",
        TS_TASK,
        "-d",
        device,
        "-nr",
        "1",
        "-ns",
        "1",
    ]
    if hub_event == _DICOM_SEND_EVENT:
        options.extend(["-ot", "dicom"])
    if TS_MULTILABEL:
        options.append("--ml")
    if TS_FAST:
        options.append("--fast")
    return options


def _log_subprocess_output(proc: Any) -> None:
    while True:
        try:
            line = proc.stdout.readline()
        except UnicodeDecodeError:
            continue
        if not line:
            break
        text = line.rstrip() if isinstance(line, str) else line.decode(
            "utf-8", errors="replace"
        ).rstrip()
        if text:
            print(text)


def _run_totalsegmentator_subprocess(
    command: list[str], options: list[str]
) -> bool:
    from subprocess import CalledProcessError

    cmd = command + options
    _console_log("launch: %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    _log_subprocess_output(proc)
    proc.wait()
    if proc.returncode != 0:
        raise CalledProcessError(proc.returncode, cmd)
    return True


def _run_totalsegmentator(
    input_path: Path, output_dir: Path, hub_event: str
) -> Optional[Path]:
    command = _total_segmentator_launch_command()
    if not command:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = _cli_output_path(output_dir, hub_event)

    for device in ("gpu", "cpu"):
        try:
            started = time.monotonic()
            options = _total_segmentator_cli_options(
                input_path, output_path, device, hub_event
            )
            _run_totalsegmentator_subprocess(command, options)
            elapsed = time.monotonic() - started
            _console_log(
                "finished device=%s in %.1fs hub.event=%s output=%s",
                device,
                elapsed,
                hub_event,
                output_path,
            )
            result = _find_segmentation_output(output_dir, hub_event, output_path)
            if result:
                return result
            _console_error(
                "exited OK but no output for hub.event=%s under %s",
                hub_event,
                output_dir,
            )
        except Exception as exc:
            _console_error("failed device=%s: %s", device, exc)
            if output_dir.is_dir():
                for entry in output_dir.iterdir():
                    if entry.is_file():
                        entry.unlink()
                    elif entry.is_dir():
                        shutil.rmtree(entry, ignore_errors=True)
    return None


def _find_segmentation_output(
    output_dir: Path, hub_event: str, expected_path: Path
) -> Optional[Path]:
    if expected_path.is_file():
        return expected_path
    if hub_event == _NIFTI_SEND_EVENT:
        return _find_output_nifti(output_dir)
    return _find_output_dicom(output_dir)


def _find_output_nifti(output_dir: Path) -> Optional[Path]:
    primary = output_dir / OUTPUT_NIFTI_NAME
    if primary.is_file():
        return primary
    candidates = sorted(
        path
        for path in output_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in (".gz", ".nii", ".nhdr", ".nrrd")
        and "input" not in path.parts
    )
    if not candidates:
        _console_error(
            "no NIfTI under %s (contents: %s)",
            output_dir,
            list(output_dir.rglob("*"))[:20],
        )
        return None
    if len(candidates) > 1:
        _console_log(
            "multiple NIfTI outputs, using %s (all: %s)",
            candidates[0],
            [str(p) for p in candidates],
        )
    return candidates[0]


def _find_output_dicom(output_dir: Path) -> Optional[Path]:
    primary = output_dir / OUTPUT_DICOM_NAME
    if primary.is_file():
        return primary
    candidates = [
        path
        for path in output_dir.rglob("*.dcm")
        if path.is_file() and "input" not in path.parts
    ]
    if not candidates:
        _console_error(
            "no .dcm under %s (contents: %s)",
            output_dir,
            list(output_dir.rglob("*"))[:20],
        )
        return None
    if len(candidates) > 1:
        _console_log(
            "multiple .dcm outputs, using %s (all: %s)",
            candidates[0],
            [str(p) for p in candidates],
        )
    return candidates[0]

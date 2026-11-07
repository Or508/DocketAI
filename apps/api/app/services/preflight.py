"""Run the file check in a short-lived process with a minimal environment."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sys
from pathlib import Path

from app.core.config import Settings
from app.core.exceptions import BadRequestError
from app.core.paths import API_ROOT

logger = logging.getLogger(__name__)

WORKER_MODULE = "app.services.preflight_worker"

_MESSAGES = {
    "encrypted": "{filename} is password-protected.",
    "too_many_pages": "{filename} has too many pages.",
    "page_too_large": "{filename} has a page that is too large.",
    "too_large_decompressed": "{filename} is too large to accept.",
    "embedded_file": "{filename} contains embedded files or actions, which are not accepted.",
    "launch_action": "{filename} contains embedded files or actions, which are not accepted.",
    "rich_media": "{filename} contains embedded files or actions, which are not accepted.",
    "javascript": "{filename} contains embedded files or actions, which are not accepted.",
    "image_too_large": "{filename} is too large.",
    "unreadable": "{filename} could not be read.",
}


class _WorkerFailed(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _hash_prefix(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:12]


def _log(reason: str, path: Path) -> None:
    try:
        prefix = _hash_prefix(path)
    except OSError:
        prefix = "unread"
    logger.info("preflight reason=%s hash=%s", reason, prefix)


def _environment(settings: Settings) -> dict[str, str]:
    env: dict[str, str] = {}
    path = os.environ.get("PATH")
    if path:
        env["PATH"] = path
    pythonpath = [str(API_ROOT)]
    inherited = os.environ.get("PYTHONPATH")
    if inherited:
        pythonpath.append(inherited)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)
    if os.name == "nt":
        system_root = os.environ.get("SYSTEMROOT")
        if system_root:
            env["SYSTEMROOT"] = system_root
    env["PREFLIGHT_MAX_PAGES"] = str(settings.preflight_max_pages)
    env["PREFLIGHT_MAX_PAGE_INCHES"] = str(settings.preflight_max_page_inches)
    env["PREFLIGHT_MAX_DECOMPRESSED_MB"] = str(settings.preflight_max_decompressed_mb)
    env["PREFLIGHT_MAX_IMAGE_PIXELS"] = str(settings.preflight_max_image_pixels)
    env["PREFLIGHT_REJECT_PDF_JAVASCRIPT"] = "true" if settings.preflight_reject_pdf_javascript else "false"
    # The worker applies these to itself on POSIX before it opens the file.
    env["PREFLIGHT_MEMORY_MB"] = str(settings.preflight_memory_mb)
    env["PREFLIGHT_CPU_SECONDS"] = str(max(settings.preflight_timeout_seconds, 1))
    return env


async def _run_worker(path: Path, mime: str, settings: Settings) -> str:
    kwargs: dict[str, object] = {
        "cwd": str(API_ROOT),
        "env": _environment(settings),
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        WORKER_MODULE,
        str(path),
        mime,
        **kwargs,
    )
    try:
        stdout, _stderr = await asyncio.wait_for(process.communicate(), settings.preflight_timeout_seconds)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise _WorkerFailed("timeout") from None
    if process.returncode != 0:
        raise _WorkerFailed("exit")
    return stdout.decode("utf-8", errors="replace").strip()


async def preflight(path: Path, mime: str, settings: Settings, filename: str) -> int:
    """Return the page or frame count, or raise a user-facing BadRequestError."""
    try:
        line = await _run_worker(path, mime, settings)
        payload = json.loads(line)
    except (TimeoutError, _WorkerFailed, json.JSONDecodeError, OSError):
        _log("unsafe", path)
        raise BadRequestError(f"{filename} could not be checked safely.") from None
    if not isinstance(payload, dict):
        _log("unsafe", path)
        raise BadRequestError(f"{filename} could not be checked safely.")
    if payload.get("ok") is True and isinstance(payload.get("pages"), int) and payload["pages"] >= 0:
        return payload["pages"]
    reason = payload.get("reason")
    message = _MESSAGES.get(reason) if isinstance(reason, str) else None
    if message is None:
        _log("unsafe", path)
        raise BadRequestError(f"{filename} could not be checked safely.")
    _log(reason, path)
    return _reject(message, filename)


def _reject(message: str, filename: str) -> int:
    raise BadRequestError(message.replace("{filename}", filename))

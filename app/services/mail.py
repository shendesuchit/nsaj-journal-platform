from __future__ import annotations

import json
import os
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import get_settings


def capture_local_message(*, recipient: str, subject: str, link: str) -> None:
    settings = get_settings()
    if settings.app_env.casefold() not in {"development", "test"}:
        raise RuntimeError("Local mail capture is available only in development")
    destination = settings.mail_capture_path.resolve()
    allowed_root = (Path(__file__).resolve().parents[2] / ".local").resolve()
    if allowed_root != destination and allowed_root not in destination.parents:
        raise RuntimeError(
            "Local mail capture must remain under the ignored .local directory"
        )
    destination.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        identity = (
            subprocess.run(
                ["whoami", "/user", "/fo", "csv", "/nh"],
                capture_output=True,
                text=True,
                check=True,
            )
            .stdout.strip()
            .strip('"')
            .split('","')
        )
        user_sid = identity[-1]
        subprocess.run(
            [
                "icacls",
                str(destination),
                "/inheritance:r",
                "/grant:r",
                f"*{user_sid}:(OI)(CI)F",
                "*S-1-5-32-544:(OI)(CI)F",
            ],
            capture_output=True,
            check=True,
        )
    else:
        destination.chmod(0o700)
    message = {
        "to": recipient,
        "subject": subject,
        "created_at": datetime.now(UTC).isoformat(),
        "link": link,
    }
    filename = destination / f"{uuid.uuid4().hex}.json"
    descriptor = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(message, output, ensure_ascii=False)
        if os.name != "nt":
            filename.chmod(0o600)
    except Exception:
        filename.unlink(missing_ok=True)
        raise


def list_local_messages() -> list[Path]:
    settings = get_settings()
    if settings.app_env.casefold() not in {"development", "test"}:
        raise RuntimeError("Local mail capture is available only in development")
    root = settings.mail_capture_path.resolve()
    if not root.exists():
        return []
    return sorted(path for path in root.glob("*.json") if path.is_file())

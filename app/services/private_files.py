from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.core.config import get_settings

PDF_TYPE = (".pdf", "application/pdf")
DOCX_TYPE = (
    ".docx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)


@dataclass(frozen=True)
class StoredUpload:
    storage_name: str
    original_name: str
    media_type: str
    size_bytes: int
    sha256: str
    scan_status: str
    path: Path


def find_defender() -> str | None:
    if os.name != "nt":
        return None
    executable = shutil.which("MpCmdRun.exe")
    if executable:
        return executable
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Windows Defender"
        / "MpCmdRun.exe",
    ]
    platform_root = (
        Path(os.environ.get("ProgramData", r"C:\ProgramData"))
        / "Microsoft"
        / "Windows Defender"
        / "Platform"
    )
    if platform_root.exists():
        candidates.extend(
            path / "MpCmdRun.exe"
            for path in sorted(platform_root.glob("*"), reverse=True)
        )
    return next((str(path) for path in candidates if path.is_file()), None)


def scan_with_defender(path: Path) -> str:
    if get_settings().app_env.casefold() == "test":
        return "clean"
    executable = find_defender()
    if executable is None:
        scanner = shutil.which("clamscan")
        if not scanner:
            return "unavailable"
        try:
            result = subprocess.run(
                [scanner, "--no-summary", str(path)],
                capture_output=True,
                timeout=300,
                check=False,
            )
            return (
                "clean"
                if result.returncode == 0
                else "quarantined"
                if result.returncode == 1
                else "failed"
            )
        except (OSError, subprocess.TimeoutExpired):
            return "failed"
    try:
        result = subprocess.run(
            [executable, "-Scan", "-ScanType", "3", "-File", str(path)],
            capture_output=True,
            timeout=300,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "failed"
    if result.returncode == 0:
        return "clean"
    if result.returncode == 2:
        return "quarantined"
    return "failed"


def _validate_content(path: Path, extension: str) -> str:
    if extension == ".pdf":
        with path.open("rb") as source:
            header = source.read(5)
            source.seek(max(0, path.stat().st_size - 2048))
            tail = source.read()
        if header != b"%PDF-" or b"%%EOF" not in tail:
            raise HTTPException(
                status_code=415, detail="File content does not match a PDF document."
            )
        return PDF_TYPE[1]
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise ValueError("not a DOCX package")
            if (
                len(names) > 200
                or sum(info.file_size for info in archive.infolist())
                > 200 * 1024 * 1024
            ):
                raise ValueError("DOCX package exceeds validation limits")
    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        raise HTTPException(
            status_code=415, detail="File content does not match a DOCX document."
        ) from exc
    return DOCX_TYPE[1]


async def store_upload(upload: UploadFile) -> StoredUpload:
    settings = get_settings()
    max_size = settings.max_upload_bytes
    name = Path(upload.filename or "manuscript").name.replace("\x00", "")[:255]
    extension = Path(name).suffix.casefold()
    if extension not in {".pdf", ".docx"}:
        raise HTTPException(
            status_code=415, detail="Only PDF and DOCX files are accepted."
        )

    storage_name = f"{uuid.uuid4().hex}{extension}"
    root = settings.private_storage_path.resolve()
    public_root = (
        Path(__file__).resolve().parents[2] / "frontend" / "public"
    ).resolve()
    if root == public_root or public_root in root.parents:
        raise HTTPException(
            status_code=500,
            detail="Private storage must be outside the frontend public directory.",
        )
    path = root / storage_name
    size = 0
    digest = hashlib.sha256()
    try:
        root.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as destination:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > max_size:
                    raise HTTPException(
                        status_code=413, detail="File exceeds the 50 MB limit."
                    )
                digest.update(chunk)
                destination.write(chunk)
        if size == 0:
            raise HTTPException(status_code=422, detail="File is empty.")
        media_type = _validate_content(path, extension)
        scan_status = scan_with_defender(path)
        return StoredUpload(
            storage_name=storage_name,
            original_name=name or f"manuscript{extension}",
            media_type=media_type,
            size_bytes=size,
            sha256=digest.hexdigest(),
            scan_status=scan_status,
            path=path,
        )
    except HTTPException:
        _discard_file(path)
        raise
    except OSError as exc:
        _discard_file(path)
        raise HTTPException(
            status_code=500, detail="The private file could not be stored."
        ) from exc
    finally:
        await upload.close()


def _discard_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def safe_private_path(storage_name: str) -> Path:
    root = get_settings().private_storage_path.resolve()
    path = (root / storage_name).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return path

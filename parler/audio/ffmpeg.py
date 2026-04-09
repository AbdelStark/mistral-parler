"""FFmpeg/ffprobe wrappers."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def convert_with_ffmpeg(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-acodec",
            "pcm_s16le",
            str(destination),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return destination


def probe_audio(path: Path) -> dict[str, float | int]:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout or "{}")
    stream: dict[str, Any] = next(
        (item for item in payload.get("streams", []) if item.get("codec_type") == "audio"),
        {},
    )
    format_data = payload.get("format", {})
    duration = float(stream.get("duration") or format_data.get("duration") or 0.0)
    return {
        "duration": duration,
        "sample_rate": int(stream.get("sample_rate") or 0),
        "channels": int(stream.get("channels") or 0),
    }

"""Audio chunking, reference clip extraction, and duration probing via ffmpeg."""

from __future__ import annotations

import csv
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings

MAX_CHUNK_BYTES = 24 * 1024 * 1024  # 24 MiB safety margin under OpenAI's 25 MB limit
_ALLOWED_BINARIES = frozenset({"ffmpeg", "ffprobe"})


@dataclass
class AudioChunk:
    """One encoded audio segment ready for transcription."""

    path: Path
    offset: float
    duration: float = 0.0


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Execute an ffmpeg/ffprobe command without a shell (mockable in tests)."""
    if not cmd or cmd[0] not in _ALLOWED_BINARIES:
        raise ValueError(f"Unsupported audio command: {cmd[:1]}")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required for audio processing but was not found on PATH")
    binary = shutil.which(cmd[0])
    if binary is None:
        raise RuntimeError(f"{cmd[0]} is required for audio processing but was not found on PATH")
    try:
        return subprocess.run(
            [binary, *cmd[1:]],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip() or str(exc)
        raise RuntimeError(f"{cmd[0]} failed: {detail}") from exc


def probe_duration(path: Path) -> float:
    """Return the duration of an audio file in seconds using ffprobe."""
    res = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    raw = (res.stdout or "").strip()
    if not raw:
        raise RuntimeError(f"ffprobe returned empty duration for {path}")
    return float(raw)


def cut_clip(src: Path, start: float, end: float, dst: Path) -> Path:
    """Extract a mono 16 kHz MP3 clip [start, end] from src into dst."""
    clip_start = max(0.0, float(start))
    clip_dur = max(0.1, float(end) - clip_start)
    dst.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{clip_start:.3f}",
            "-t",
            f"{clip_dur:.3f}",
            "-i",
            str(src),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "32k",
            str(dst),
        ]
    )
    return dst


def prepare_chunks(
    src: Path,
    workdir: Path,
    chunk_seconds: int | None = None,
    bitrate_kbps: int | None = None,
) -> list[AudioChunk]:
    """Re-encode src to mono 16 kHz MP3 and split into <= 24 MB segments."""
    settings = get_settings()
    seconds = chunk_seconds if chunk_seconds is not None else settings.audio_chunk_seconds
    bitrate = bitrate_kbps if bitrate_kbps is not None else settings.audio_bitrate_kbps

    workdir.mkdir(parents=True, exist_ok=True)
    for old in workdir.glob("chunk_*.mp3"):
        old.unlink(missing_ok=True)
    list_path = workdir / "chunks.csv"
    list_path.unlink(missing_ok=True)
    pattern = workdir / "chunk_%04d.mp3"

    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            f"{bitrate}k",
            "-f",
            "segment",
            "-segment_time",
            str(seconds),
            "-segment_list",
            str(list_path),
            "-segment_list_type",
            "csv",
            str(pattern),
        ]
    )

    chunks: list[AudioChunk] = []
    if list_path.is_file():
        with list_path.open(encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) < 3:
                    continue
                chunk_path = workdir / Path(row[0]).name
                if not chunk_path.is_file():
                    continue
                start_t = float(row[1])
                end_t = float(row[2])
                chunks.append(
                    AudioChunk(
                        path=chunk_path,
                        offset=start_t,
                        duration=max(0.0, end_t - start_t),
                    )
                )
    else:
        offset = 0.0
        for chunk_path in sorted(workdir.glob("chunk_*.mp3")):
            try:
                dur = probe_duration(chunk_path)
            except (RuntimeError, ValueError):
                dur = float(seconds)
            chunks.append(AudioChunk(path=chunk_path, offset=offset, duration=dur))
            offset += dur

    if not chunks:
        raise RuntimeError(f"ffmpeg produced no audio chunks from {src}")

    for chunk in chunks:
        size = chunk.path.stat().st_size
        if size > MAX_CHUNK_BYTES:
            raise ValueError(
                f"Audio chunk {chunk.path.name} is {size} bytes, exceeding 24 MB limit"
            )

    return chunks

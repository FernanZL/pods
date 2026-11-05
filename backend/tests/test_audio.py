"""Tests for ffmpeg/ffprobe audio helpers (mocked run + optional lavfi test)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.services import audio


def test_prepare_chunks_cut_clip_and_probe_with_mocked_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        if cmd[0] == "ffprobe":
            return subprocess.CompletedProcess(cmd, 0, stdout="42.5\n", stderr="")
        if "-f" in cmd and "segment" in cmd:
            list_idx = cmd.index("-segment_list") + 1
            csv_path = Path(cmd[list_idx])
            workdir = csv_path.parent
            c0 = workdir / "chunk_0000.mp3"
            c1 = workdir / "chunk_0001.mp3"
            c0.write_bytes(b"mp3-chunk-0")
            c1.write_bytes(b"mp3-chunk-1")
            csv_path.write_text(
                "chunk_0000.mp3,0.000000,600.000000\nchunk_0001.mp3,600.000000,920.500000\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        out_path = Path(cmd[-1])
        out_path.write_bytes(b"clip-bytes")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(audio, "run", fake_run)

    src = tmp_path / "input.mp3"
    src.write_bytes(b"source")

    assert audio.probe_duration(src) == pytest.approx(42.5)

    workdir = tmp_path / "work"
    chunks = audio.prepare_chunks(src, workdir, chunk_seconds=600, bitrate_kbps=32)
    assert len(chunks) == 2
    assert chunks[0].offset == 0.0
    assert chunks[0].duration == 600.0
    assert chunks[1].offset == 600.0
    assert chunks[1].duration == 320.5

    seg_cmd = calls[1]
    assert "-ac" in seg_cmd and seg_cmd[seg_cmd.index("-ac") + 1] == "1"
    assert "-ar" in seg_cmd and seg_cmd[seg_cmd.index("-ar") + 1] == "16000"
    assert "-b:a" in seg_cmd and seg_cmd[seg_cmd.index("-b:a") + 1] == "32k"

    clip_dst = tmp_path / "ref_A.mp3"
    res_clip = audio.cut_clip(src, 1.5, 6.5, clip_dst)
    assert res_clip == clip_dst
    assert clip_dst.read_bytes() == b"clip-bytes"


def test_prepare_chunks_rejects_chunk_above_24mb(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        csv_path = Path(cmd[cmd.index("-segment_list") + 1])
        big = csv_path.parent / "chunk_0000.mp3"
        with big.open("wb") as f:
            f.seek(audio.MAX_CHUNK_BYTES + 10)
            f.write(b"\x00")
        csv_path.write_text("chunk_0000.mp3,0.0,600.0\n", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(audio, "run", fake_run)
    src = tmp_path / "src.mp3"
    src.write_bytes(b"src")

    with pytest.raises(ValueError, match="24 MB"):
        audio.prepare_chunks(src, tmp_path / "work", chunk_seconds=600, bitrate_kbps=32)


def test_missing_ffmpeg_raises_runtime_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    src = tmp_path / "src.mp3"
    src.write_bytes(b"src")

    with pytest.raises(RuntimeError, match="ffmpeg"):
        audio.prepare_chunks(src, tmp_path / "work", chunk_seconds=60, bitrate_kbps=32)


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)
def test_real_ffmpeg_with_generated_lavfi_sine_wave(tmp_path: Path) -> None:
    ffmpeg_bin = shutil.which("ffmpeg")
    assert ffmpeg_bin is not None
    wav_path = tmp_path / "sine.wav"
    subprocess.run(
        [
            ffmpeg_bin,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=3",
            str(wav_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    dur = audio.probe_duration(wav_path)
    assert dur == pytest.approx(3.0, abs=0.3)

    chunks = audio.prepare_chunks(wav_path, tmp_path / "work", chunk_seconds=2, bitrate_kbps=32)
    assert len(chunks) >= 2
    assert chunks[0].offset == pytest.approx(0.0, abs=0.05)
    assert chunks[1].offset > 1.0
    assert all(c.path.is_file() and c.path.stat().st_size > 0 for c in chunks)

    clip = audio.cut_clip(wav_path, 0.5, 2.0, tmp_path / "clip.mp3")
    assert clip.is_file()
    assert audio.probe_duration(clip) == pytest.approx(1.5, abs=0.3)

"""On-disk layout helpers shared by ingestion and RAG. CONTRACT FILE.

data/podcasts/<podcast.slug>/<episode.slug>/
    audio.mp3        original download
    transcript.json  app.domain.Transcript as JSON
    transcript.md    human-readable "**Name** [mm:ss] text" lines
    summary.md       optional LLM summary
    work/            temporary chunks / reference clips (deleted after use)
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict
from pathlib import Path

from app.config import get_settings
from app.domain import Segment, Transcript
from app.models import Episode, Podcast


def sanitize_filename(name: str) -> str:
    """Ported from the notebook's PodcastDownloader.sanitize_filename."""
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip()


def slugify(text: str, max_len: int = 80) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:max_len].strip("-") or "untitled"


def episode_slug(number: int, title: str) -> str:
    return f"{number:04d}-{slugify(title, 70)}"


def episode_dir(podcast: Podcast, episode: Episode) -> Path:
    d = get_settings().podcasts_dir / podcast.slug / episode.slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def to_rel(path: Path) -> str:
    return str(path.resolve().relative_to(get_settings().data_dir.resolve()))


def to_abs(rel: str) -> Path:
    return get_settings().data_dir / rel


def fmt_ts(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def write_transcript(path: Path, transcript: Transcript) -> None:
    path.write_text(json.dumps(asdict(transcript), ensure_ascii=False, indent=1), "utf-8")
    md_lines = []
    for seg in transcript.segments:
        name = transcript.speakers.get(seg.speaker, f"Speaker {seg.speaker}")
        md_lines.append(f"**{name}** [{fmt_ts(seg.start)}] {seg.text.strip()}")
    path.with_suffix(".md").write_text("\n\n".join(md_lines) + "\n", "utf-8")


def read_transcript(path: Path) -> Transcript:
    raw = json.loads(path.read_text("utf-8"))
    return Transcript(
        episode_id=raw["episode_id"],
        model=raw.get("model", ""),
        speakers=raw.get("speakers", {}),
        segments=[Segment(**s) for s in raw.get("segments", [])],
    )

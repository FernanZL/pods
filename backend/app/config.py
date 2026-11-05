"""Application settings, loaded from environment / .env.

CONTRACT FILE — shared by every module. Do not change field names without
updating docs/architecture.md.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProvider = Literal["openai", "openrouter", "fake"]
TranscriberName = Literal["openai_diarize", "openai_text", "fake"]
EmbeddingsProvider = Literal["openai", "fake"]
DownloadMode = Literal["real", "fake"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    # --- Storage ---------------------------------------------------------
    data_dir: Path = Path("./data")

    # --- API keys --------------------------------------------------------
    openai_api_key: str = ""
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # --- Chat / summaries LLM -------------------------------------------
    llm_provider: LLMProvider = "openai"
    # OpenAI id. When llm_provider == "openrouter" and this has no "/", the
    # factory prefixes "openai/" automatically.
    llm_model: str = "gpt-6-luna"
    llm_reasoning_effort: Literal["none", "low", "medium", "high"] = "low"
    summary_max_tokens: int = 8000

    # --- Transcription ---------------------------------------------------
    transcriber: TranscriberName = "openai_diarize"
    diarize_model: str = "gpt-4o-transcribe-diarize"  # sunsets 2027-02-26
    text_transcribe_model: str = "gpt-transcribe"
    # Audio is re-encoded (mono, low bitrate) and split before upload; the
    # API limit is 25 MB per request.
    audio_chunk_seconds: int = 600
    audio_bitrate_kbps: int = 32
    max_known_speakers: int = 4

    # --- Embeddings / retrieval -----------------------------------------
    embeddings_provider: EmbeddingsProvider = "openai"
    embedding_model: str = "text-embedding-3-small"
    chunk_chars: int = 1000
    chunk_overlap_chars: int = 200
    retrieval_k: int = 12
    max_passages_per_episode: int = 3

    # --- Downloads / jobs -----------------------------------------------
    download_mode: DownloadMode = "real"
    job_concurrency: int = 2
    default_feeds: list[str] = ["https://feeds.megaphone.fm/hubermanlab"]

    # --- Cost estimate (USD). Verify against current OpenAI pricing. ----
    price_diarize_per_min: float = 0.006
    price_text_transcribe_per_min: float = 0.0045
    price_embedding_per_mtok: float = 0.02
    price_llm_input_per_mtok: float = 0.10
    price_llm_output_per_mtok: float = 0.50

    # ---------------------------------------------------------------------
    @property
    def podcasts_dir(self) -> Path:
        return self.data_dir / "podcasts"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def embedding_id(self) -> str:
        """Identifies the embedding space; used to name the Chroma collection
        so fake and real vectors never mix."""
        if self.embeddings_provider == "fake":
            return "fake-hash-256"
        return self.embedding_model

    @property
    def fake_mode(self) -> bool:
        return "fake" in (self.llm_provider, self.transcriber, self.embeddings_provider)

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.podcasts_dir, self.chroma_dir):
            try:
                d.mkdir(parents=True, exist_ok=True)
            except PermissionError as exc:
                raise PermissionError(
                    f"Cannot write to {d}. If running in Docker, the host ./data folder is "
                    "probably owned by root: run `sudo chown -R $(id -u):$(id -g) data` "
                    "(or start with ./dev up, which creates it with your user)."
                ) from exc


@lru_cache
def get_settings() -> Settings:
    return Settings()

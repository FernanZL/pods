"""Health + public config. (Owned by integrator.)"""

from fastapi import APIRouter

from app.config import get_settings
from app.schemas import AppConfigOut, Prices

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/config", response_model=AppConfigOut)
def config() -> AppConfigOut:
    s = get_settings()
    diarize = s.transcriber == "openai_diarize"
    return AppConfigOut(
        llm_provider=s.llm_provider,
        llm_model=s.llm_model,
        transcriber=s.transcriber,
        transcription_model=(
            "fake"
            if s.transcriber == "fake"
            else s.diarize_model
            if diarize
            else s.text_transcribe_model
        ),
        embedding_model=s.embedding_id,
        fake_mode=s.fake_mode,
        has_openai_key=bool(s.openai_api_key),
        has_openrouter_key=bool(s.openrouter_api_key),
        prices=Prices(
            transcription_per_min=(
                s.price_diarize_per_min if diarize else s.price_text_transcribe_per_min
            ),
            embedding_per_mtok=s.price_embedding_per_mtok,
            llm_input_per_mtok=s.price_llm_input_per_mtok,
            llm_output_per_mtok=s.price_llm_output_per_mtok,
        ),
    )

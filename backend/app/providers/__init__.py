"""Provider factories. CONTRACT FILE.

Implementations (class names are part of the contract):
  providers/llm.py          OpenAICompatibleLLM(api_key, model, base_url=None,
                                                reasoning_effort="low")
  providers/embeddings.py   OpenAIEmbedder(api_key, model)
  providers/fake.py         FakeLLM(), FakeEmbedder(dimensions=256)
  providers/transcription/openai_diarize.py      OpenAIDiarizeTranscriber(api_key, model)
  providers/transcription/openai_text_attrib.py  OpenAITextTranscriber(api_key, model, llm)
  providers/transcription/fake.py                FakeTranscriber()
"""

from functools import lru_cache

from app.config import get_settings
from app.domain import Embedder, LLMClient, Transcriber


class ProviderNotConfigured(RuntimeError):
    """Raised when a real provider is selected but its API key is missing."""


@lru_cache
def get_llm() -> LLMClient:
    s = get_settings()
    if s.llm_provider == "fake":
        from app.providers.fake import FakeLLM

        return FakeLLM()
    from app.providers.llm import OpenAICompatibleLLM

    if s.llm_provider == "openrouter":
        if not s.openrouter_api_key:
            raise ProviderNotConfigured("OPENROUTER_API_KEY is not set")
        model = s.llm_model if "/" in s.llm_model else f"openai/{s.llm_model}"
        return OpenAICompatibleLLM(
            api_key=s.openrouter_api_key,
            model=model,
            base_url=s.openrouter_base_url,
            reasoning_effort=s.llm_reasoning_effort,
        )
    if not s.openai_api_key:
        raise ProviderNotConfigured("OPENAI_API_KEY is not set")
    return OpenAICompatibleLLM(
        api_key=s.openai_api_key, model=s.llm_model, reasoning_effort=s.llm_reasoning_effort
    )


@lru_cache
def get_embedder() -> Embedder:
    s = get_settings()
    if s.embeddings_provider == "fake":
        from app.providers.fake import FakeEmbedder

        return FakeEmbedder(dimensions=256)
    from app.providers.embeddings import OpenAIEmbedder

    if not s.openai_api_key:
        raise ProviderNotConfigured("OPENAI_API_KEY is not set (needed for embeddings)")
    return OpenAIEmbedder(api_key=s.openai_api_key, model=s.embedding_model)


@lru_cache
def get_transcriber() -> Transcriber:
    s = get_settings()
    if s.transcriber == "fake":
        from app.providers.transcription.fake import FakeTranscriber

        return FakeTranscriber()
    if not s.openai_api_key:
        raise ProviderNotConfigured("OPENAI_API_KEY is not set (needed for transcription)")
    if s.transcriber == "openai_text":
        from app.providers.transcription.openai_text_attrib import OpenAITextTranscriber

        return OpenAITextTranscriber(
            api_key=s.openai_api_key, model=s.text_transcribe_model, llm=get_llm()
        )
    from app.providers.transcription.openai_diarize import OpenAIDiarizeTranscriber

    return OpenAIDiarizeTranscriber(api_key=s.openai_api_key, model=s.diarize_model)


def reset_providers() -> None:
    """Tests: clear cached providers after changing settings."""
    get_llm.cache_clear()
    get_embedder.cache_clear()
    get_transcriber.cache_clear()

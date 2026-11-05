"""ChromaDB persistent vector store implementation."""

from __future__ import annotations

from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from app import storage
from app.config import get_settings
from app.domain import Passage, ScoredPassage, VectorStore

_UPSERT_BATCH = 500


class ChromaVectorStore:
    """Persistent ChromaDB collection implementing ``app.domain.VectorStore``."""

    def __init__(self) -> None:
        settings = get_settings()
        settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(settings.chroma_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        collection_name = f"passages__{storage.slugify(settings.embedding_id)}"
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(self, passages: list[Passage], embeddings: list[list[float]]) -> None:
        """Upsert passages and their embeddings into the collection."""
        if not passages:
            return
        if len(passages) != len(embeddings):
            raise ValueError("passages and embeddings must have the same length")

        for start in range(0, len(passages), _UPSERT_BATCH):
            batch_p = passages[start : start + _UPSERT_BATCH]
            batch_e = embeddings[start : start + _UPSERT_BATCH]
            self._collection.upsert(
                ids=[p.id for p in batch_p],
                documents=[p.text for p in batch_p],
                embeddings=batch_e,
                metadatas=[{k: v for k, v in p.metadata.items() if v is not None} for p in batch_p],
            )

    def delete_episode(self, episode_id: int) -> int:
        """Remove all passages belonging to ``episode_id`` and return count removed."""
        existing = self._collection.get(where={"episode_id": episode_id}, include=[])
        ids = existing.get("ids") or []
        if not ids:
            return 0
        self._collection.delete(ids=ids)
        return len(ids)

    def delete_episode_source(self, episode_id: int, source: str) -> int:
        """Remove passages for a single ``(episode_id, source)`` pair."""
        where_filter: dict[str, Any] = {
            "$and": [{"episode_id": episode_id}, {"source": source}],
        }
        existing = self._collection.get(where=where_filter, include=[])
        ids = existing.get("ids") or []
        if not ids:
            return 0
        self._collection.delete(ids=ids)
        return len(ids)

    def count_episode(self, episode_id: int) -> int:
        """Return total stored passages for ``episode_id``."""
        existing = self._collection.get(where={"episode_id": episode_id}, include=[])
        return len(existing.get("ids") or [])

    def query(
        self,
        embedding: list[float],
        *,
        k: int,
        where: dict[str, Any] | None = None,
    ) -> list[ScoredPassage]:
        """Return up to ``k`` nearest passages matching optional ``where`` filter."""
        if k <= 0:
            return []
        total = self._collection.count()
        if total == 0:
            return []

        kwargs: dict[str, Any] = {
            "query_embeddings": [embedding],
            "n_results": min(k, total),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        res = self._collection.query(**kwargs)
        ids = (res.get("ids") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]

        scored: list[ScoredPassage] = []
        for pid, doc, meta, dist in zip(ids, docs, metas, dists, strict=True):
            scored.append(
                ScoredPassage(
                    passage=Passage(
                        id=pid,
                        text=doc or "",
                        metadata=dict(meta) if meta else {},
                    ),
                    distance=float(dist),
                )
            )
        return scored

    def count(self) -> int:
        """Return total number of passages in the active collection."""
        return self._collection.count()

    def episode_ids(self) -> set[int]:
        """Return distinct ``episode_id`` values stored in the active collection."""
        if self._collection.count() == 0:
            return set()
        res = self._collection.get(include=["metadatas"])
        metas = res.get("metadatas") or []
        return {
            int(m["episode_id"])
            for m in metas
            if m and "episode_id" in m and m["episode_id"] is not None
        }


_store: ChromaVectorStore | None = None
_store_key: tuple[str, str] | None = None


def get_vector_store() -> VectorStore:
    """Return cached ``ChromaVectorStore`` for current data_dir and embedding_id."""
    global _store, _store_key
    settings = get_settings()
    key = (str(settings.chroma_dir.resolve()), settings.embedding_id)
    if _store is None or _store_key != key:
        _store = ChromaVectorStore()
        _store_key = key
    return _store


def reset_vector_store() -> None:
    """Clear cached vector store instance (used by test fixtures)."""
    global _store, _store_key
    _store = None
    _store_key = None

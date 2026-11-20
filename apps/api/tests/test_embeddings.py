"""The label memory asks for vectors of its own size and never mixes two embedding models in one collection."""

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("google.genai")

from app.core.config import Settings
from app.services.gemini_client import GoogleGeminiClient
from app.services.learning_store import QdrantLearningStore, collection_name


class _Models:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def embed_content(self, **kwargs):
        self.calls.append(kwargs)
        size = kwargs["config"].output_dimensionality
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[0.5] * size)])


def _settings(**overrides) -> Settings:
    return Settings(gemini_api_key="test-key", qdrant_url="", **overrides)


def test_the_default_model_is_not_the_retired_one() -> None:
    assert Settings.model_fields["embedding_model"].default == "gemini-embedding-001"


def test_embed_asks_for_the_configured_size() -> None:
    settings = _settings(embedding_model="gemini-embedding-001", embedding_dimensions=768)
    client = GoogleGeminiClient(settings)
    models = _Models()
    client._sdk = SimpleNamespace(models=models)
    vector = asyncio.run(client.embed("חשבון ארנונה"))
    assert len(vector) == 768
    assert models.calls[0]["model"] == "gemini-embedding-001"
    assert models.calls[0]["config"].output_dimensionality == 768


def test_each_model_and_size_has_its_own_collection() -> None:
    assert collection_name("gemini-embedding-001", 768) == "docket_labels__gemini_embedding_001_768"
    names = {
        collection_name("text-embedding-004", 768),
        collection_name("gemini-embedding-001", 768),
        collection_name("gemini-embedding-001", 1536),
    }
    assert len(names) == 3


def test_the_store_uses_the_collection_of_its_model() -> None:
    settings = _settings(embedding_model="gemini-embedding-001", embedding_dimensions=768)
    store = QdrantLearningStore(settings, GoogleGeminiClient(settings))
    assert store._collection == collection_name("gemini-embedding-001", 768)

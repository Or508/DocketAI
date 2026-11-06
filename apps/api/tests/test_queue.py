import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.core.config import get_settings
from app.workers.queue import enqueue_case_processing


def _settings(monkeypatch) -> None:
    monkeypatch.setenv("QUEUE_ENABLED", "true")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    get_settings.cache_clear()


def test_missing_worker_health_key_does_not_enqueue(monkeypatch) -> None:
    _settings(monkeypatch)
    calls: list[tuple] = []

    class Pool:
        async def exists(self, key: str) -> bool:
            return False

        async def enqueue_job(self, *args, **kwargs):
            calls.append(args)
            return SimpleNamespace(job_id="should-not-run")

        async def close(self) -> None:
            return None

    async def create_pool(*args, **kwargs):
        return Pool()

    monkeypatch.setattr("arq.create_pool", create_pool)
    result = asyncio.run(enqueue_case_processing(uuid4()))
    assert result is None
    assert calls == []
    get_settings.cache_clear()


def test_worker_health_key_enqueues(monkeypatch) -> None:
    _settings(monkeypatch)

    class Pool:
        async def exists(self, key: str) -> bool:
            assert key == "arq:queue:health-check"
            return True

        async def enqueue_job(self, *args, **kwargs):
            return SimpleNamespace(job_id="job-1")

        async def close(self) -> None:
            return None

    async def create_pool(*args, **kwargs):
        return Pool()

    monkeypatch.setattr("arq.create_pool", create_pool)
    result = asyncio.run(enqueue_case_processing(uuid4()))
    assert result == "job-1"
    get_settings.cache_clear()

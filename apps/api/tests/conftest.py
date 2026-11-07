import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "local_storage: reads case files directly from the local storage directory",
    )


def _apply_s3_env() -> str | None:
    endpoint = os.environ.get("TEST_S3_ENDPOINT")
    if not endpoint:
        return None
    mapping = {
        "TEST_S3_ENDPOINT": "S3_ENDPOINT_URL",
        "TEST_S3_BUCKET": "S3_BUCKET",
        "TEST_S3_REGION": "S3_REGION",
        "TEST_S3_ACCESS_KEY_ID": "S3_ACCESS_KEY_ID",
        "TEST_S3_SECRET_ACCESS_KEY": "S3_SECRET_ACCESS_KEY",
        "TEST_S3_FORCE_PATH_STYLE": "S3_FORCE_PATH_STYLE",
    }
    os.environ["STORAGE_BACKEND"] = "s3"
    for source, target in mapping.items():
        if source in os.environ:
            os.environ[target] = os.environ[source]
    return endpoint


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    if _apply_s3_env() and item.get_closest_marker("local_storage"):
        pytest.skip("This test reads the local storage directory.")


@pytest.fixture(autouse=True)
def object_storage_backend(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    endpoint = os.environ.get("TEST_S3_ENDPOINT")
    if not endpoint:
        return
    if request.node.get_closest_marker("local_storage"):
        pytest.skip("This test reads the local storage directory.")
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    for source, target in {
        "TEST_S3_ENDPOINT": "S3_ENDPOINT_URL",
        "TEST_S3_BUCKET": "S3_BUCKET",
        "TEST_S3_REGION": "S3_REGION",
        "TEST_S3_ACCESS_KEY_ID": "S3_ACCESS_KEY_ID",
        "TEST_S3_SECRET_ACCESS_KEY": "S3_SECRET_ACCESS_KEY",
        "TEST_S3_FORCE_PATH_STYLE": "S3_FORCE_PATH_STYLE",
    }.items():
        if source in os.environ:
            monkeypatch.setenv(target, os.environ[source])

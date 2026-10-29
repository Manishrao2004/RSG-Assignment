import pytest
from fastapi.testclient import TestClient

from app.config import ROOT, Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(
        groq_api_key="",
        langsmith_tracing=False,
        langsmith_api_key="",
        db_path=tmp_path / "sales.sqlite3",
        csv_path=ROOT / "data" / "sales.csv",
        _env_file=None,
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client

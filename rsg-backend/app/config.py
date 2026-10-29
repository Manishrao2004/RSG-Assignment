from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "rsg-sales-assistant"
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    db_path: Path = ROOT / "data" / "sales.sqlite3"
    csv_path: Path = ROOT / "data" / "sales.csv"

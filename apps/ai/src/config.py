from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[
            Path(__file__).resolve().parents[3] / ".env",
            Path(__file__).resolve().parents[2] / ".env",
        ],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str
    anthropic_model: str = "claude-opus-4-7"
    max_tokens: int = 4096

    rag_enabled: bool = True
    rag_top_k: int = 5
    database_url: str = "postgresql://legal_ai:legal_ai_password@localhost:5432/legal_ai"
    egov_api_base: str = "https://laws.e-gov.go.jp/api/2"
    embedding_model: str = "voyage-3"
    embedding_dim: int = 1024
    voyage_api_key: str = ""


settings = Settings()  # type: ignore[call-arg]

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AI-RAG"
    api_cors_origins: str = "http://localhost:5173"
    database_url: str = "postgresql://app:app@localhost:5432/app"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    openai_api_key: str = ""
    jwt_secret: str = "change-me"

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.api_cors_origins.split(",") if item.strip()]


def load_settings() -> Settings:
    return Settings()

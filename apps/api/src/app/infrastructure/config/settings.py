from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AI-RAG"
    api_cors_origins: str = "http://localhost:5173"
    database_url: str = "postgresql://app:app@localhost:5432/app"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    openai_api_key: str = ""
    openai_embed_model: str = "text-embedding-3-small"
    rag_top_k: int = 5
    rag_score_threshold: float = 0.70
    jwt_secret: str = "change-me"
    bootstrap_tenant_name: str = ""
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""
    max_document_size_mb: int = 20
    max_document_pages: int = 100
    max_concurrent_ingestions_per_tenant: int = 2
    s3_endpoint_url: str = ""
    s3_region: str = "garage"
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_use_path_style: bool = True

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.api_cors_origins.split(",") if item.strip()]

    @property
    def max_document_size_bytes(self) -> int:
        return self.max_document_size_mb * 1024 * 1024


def load_settings() -> Settings:
    return Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_password: str
    secret_key: str

    openrouter_api_key: str
    github_token: str = ""
    github_repo: str = "ServiceNow/ServiceNowDocs"

    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_api_key: str = ""

    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dimension: int = 1536
    embedding_batch_size: int = 100

    repos_dir: str = "/data/repos"
    db_path: str = "/data/state.db"

    ingest_limit: int = 0  # 0 = no limit; set to a small number for testing

    sync_cron_hour: int = 2
    session_max_age: int = 28800
    log_level: str = "INFO"


settings = Settings()

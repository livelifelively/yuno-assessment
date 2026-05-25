from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    log_level: str = "info"

    database_url: str = Field(
        default="postgresql+psycopg://yuno:yuno@localhost:5432/yuno",
        description="SQLAlchemy URL for the application database.",
    )

    gemini_api_key: str | None = None
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    telegram_bot_token: str | None = None


settings = Settings()

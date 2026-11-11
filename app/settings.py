from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Telegram
    telegram_bot_token: SecretStr = Field(..., alias="TELEGRAM_BOT_TOKEN")

    # --- Notion
    notion_token: SecretStr = Field(..., alias="NOTION_TOKEN")
    notion_db_id: str = Field(..., alias="NOTION_DB_ID")

    # --- LLM
    llm_model: str = Field("gpt-6-luna", alias="LLM_MODEL")
    openai_api_key: SecretStr | None = Field(None, alias="OPENAI_API_KEY")
    groq_api_key: SecretStr | None = Field(None, alias="GROQ_API_KEY")

    # --- Runtime
    timezone: str = Field("Europe/Rome", alias="TIMEZONE")
    environment: Literal["local", "prod"] = Field("local", alias="ENVIRONMENT")
    rule_parser_mode: Literal["conservative", "balanced"] = Field(
        "conservative",
        alias="RULE_PARSER_MODE",
    )

    @field_validator("timezone")
    @classmethod
    def _tz_valid(cls, v: str) -> str:
        from zoneinfo import ZoneInfo

        try:
            ZoneInfo(v)
        except Exception as e:
            raise ValueError(f"Invalid IANA timezone: {v}") from e
        return v

    @model_validator(mode="after")
    def _check_llm_api_key(self) -> "Settings":
        import os

        if not (
            self.openai_api_key
            or self.groq_api_key
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("GROQ_API_KEY")
        ):
            raise ValueError("Missing LLM API key: set OPENAI_API_KEY or GROQ_API_KEY")
        return self

    def export_llm_env(self) -> None:
        """Propaga le chiavi in os.environ per litellm (utile in dev/docker)."""
        import os

        if self.openai_api_key:
            os.environ.setdefault("OPENAI_API_KEY", self.openai_api_key.get_secret_value())
        if self.groq_api_key:
            os.environ.setdefault("GROQ_API_KEY", self.groq_api_key.get_secret_value())


settings = Settings()
settings.export_llm_env()

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
    llm_model: str = Field("gpt-4o-mini-2024-07-18", alias="LLM_MODEL")
    openai_api_key: SecretStr | None = Field(None, alias="OPENAI_API_KEY")
    groq_api_key: SecretStr | None = Field(None, alias="GROQ_API_KEY")

    # --- Runtime
    timezone: str = Field("Europe/Rome", alias="TIMEZONE")
    environment: Literal["local", "prod"] = Field("local", alias="ENVIRONMENT")

    # --- Liste configurabili da .env
    accounts: list[str] = Field(
        default_factory=lambda: ["Hype", "Revolut", "Contanti"],
        alias="ACCOUNTS",
    )
    outcome_categories: list[str] = Field(
        default_factory=lambda: [
            "Food",
            "Groceries",
            "Transport",
            "Bills",
            "Shopping",
            "Entertainment",
            "Other",
        ],
        alias="OUTCOME_CATEGORIES",
    )
    income_categories: list[str] = Field(
        default_factory=lambda: ["Salary", "Bonus", "Refund", "Other"],
        alias="INCOME_CATEGORIES",
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

    @field_validator("accounts", "outcome_categories", "income_categories", mode="before")
    @classmethod
    def _parse_csv(cls, v: object) -> list[str]:
        # Accetta JSON list (consigliato in .env) o CSV o list[str]
        if v is None:
            return []
        if isinstance(v, str):
            # Se è JSON valido, pydantic_settings lo passa già come list.
            # Se arriva qui, assumiamo CSV.
            items = [s.strip() for s in v.split(",") if s.strip()]
        elif isinstance(v, list):
            items = [str(s).strip() for s in v if str(s).strip()]
        else:
            raise ValueError("must be JSON array, CSV string or list[str]")
        # dedup preservando ordine
        seen: set[str] = set()
        out: list[str] = []
        for it in items:
            if it not in seen:
                seen.add(it)
                out.append(it)
        return out

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

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+psycopg://warden:warden@localhost:5432/warden",
        alias="DATABASE_URL",
    )
    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")

    razorpay_key_id: str = Field(default="", alias="RAZORPAY_KEY_ID")
    razorpay_key_secret: str = Field(default="", alias="RAZORPAY_KEY_SECRET")
    razorpay_mode: str = Field(default="auto", alias="RAZORPAY_MODE")  # auto|live|mock

    # LLM
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    llm_mode: str = Field(default="auto", alias="WARDEN_LLM_MODE")  # auto|live|mock
    llm_model: str = Field(
        default="claude-haiku-4-5-20251001", alias="WARDEN_LLM_MODEL"
    )

    # Agent confidence threshold — below this the agent asks for human approval
    # even when Warden itself would ALLOW.
    agent_confidence_threshold: float = Field(
        default=0.7, alias="AGENT_CONFIDENCE_THRESHOLD"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

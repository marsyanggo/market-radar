from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    alpaca_data_feed: str = "iex"

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"

    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "market-radar/0.1"

    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'radar.db'}"

    log_level: str = "INFO"
    log_dir: Path = Field(default=PROJECT_ROOT / "logs")
    reports_dir: Path = Field(default=PROJECT_ROOT / "reports")

    aitrader_data_dir: Path = Field(default=Path("/Users/marsyang/workspace/AI_trader/data"))

    @property
    def is_paper(self) -> bool:
        return "paper" in self.alpaca_base_url


settings = Settings()

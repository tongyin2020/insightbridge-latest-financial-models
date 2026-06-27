"""
Application configuration loaded from .env file with sensible defaults.
Compatible with Python 3.9+.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv(Path(__file__).parent / ".env")


class Settings:
    def __init__(self):
        # Market Data
        self.twelve_data_api_key: str = os.getenv("TWELVE_DATA_API_KEY", "")

        # Telegram Alerts
        self.telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

        # Broker APIs
        self.dukascopy_api_url: str = os.getenv("DUKASCOPY_API_URL", "http://localhost:9090")
        self.ib_tws_host: str = os.getenv("IB_TWS_HOST", "127.0.0.1")
        self.ib_tws_port: int = int(os.getenv("IB_TWS_PORT", "7497"))
        self.ib_tws_client_id: int = int(os.getenv("IB_TWS_CLIENT_ID", "1"))

        # Server
        self.host: str = os.getenv("HOST", "0.0.0.0")
        self.port: int = int(os.getenv("PORT", "8000"))

        # Database
        self.database_path: str = os.getenv("DATABASE_PATH", "fx_trading.db")

        # Trading pairs
        self.pairs: list = ["AUD/USD", "NZD/USD"]

        # Polling intervals (seconds)
        self.api_poll_interval: int = 60  # For real Twelve Data API (free tier)
        self.sim_poll_interval: int = 2   # For simulated data

    @property
    def use_simulated_data(self) -> bool:
        return not self.twelve_data_api_key or self.twelve_data_api_key == "your_twelve_data_key_here"

    @property
    def telegram_configured(self) -> bool:
        return (
            bool(self.telegram_bot_token)
            and self.telegram_bot_token != "your_telegram_bot_token_here"
            and bool(self.telegram_chat_id)
            and self.telegram_chat_id != "your_chat_id_here"
        )


settings = Settings()

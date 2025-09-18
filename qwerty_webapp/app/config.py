from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    api_base_url: str = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")


settings = Settings()

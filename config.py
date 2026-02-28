"""Configuration management for Newsletter Digest Agent."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent
load_dotenv(PROJECT_ROOT / ".env")


class Config:
    # Gmail
    GMAIL_CREDENTIALS_PATH = PROJECT_ROOT / os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json")
    GMAIL_TOKEN_PATH = PROJECT_ROOT / os.getenv("GMAIL_TOKEN_PATH", "token.json")
    GMAIL_LABEL = os.getenv("GMAIL_LABEL", "Newsletter")

    # Anthropic
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    MODEL = "claude-haiku-4-5-20251001"

    # Notion
    NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
    NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")

    # Limits
    MAX_NEWSLETTERS = int(os.getenv("MAX_NEWSLETTERS", "30"))
    # Max tokens to send per LLM call (~75K leaves room for response)
    MAX_INPUT_TOKENS = 75000
    # Approx chars per token for estimation
    CHARS_PER_TOKEN = 4

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def validate(cls):
        """Validate all required config is present."""
        errors = []
        if not cls.ANTHROPIC_API_KEY:
            errors.append("ANTHROPIC_API_KEY not set")
        if not cls.NOTION_API_KEY:
            errors.append("NOTION_API_KEY not set")
        if not cls.NOTION_DATABASE_ID:
            errors.append("NOTION_DATABASE_ID not set")
        if not cls.GMAIL_CREDENTIALS_PATH.exists():
            errors.append(f"Gmail credentials not found at {cls.GMAIL_CREDENTIALS_PATH}")
        if errors:
            raise EnvironmentError("Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))

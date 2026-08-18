"""Runtime configuration for RevenueOS.

All secrets are read from the environment. Nothing here is ever serialised to the
frontend: `public_config()` deliberately exposes only booleans and non-sensitive
metadata so the browser can adapt its UI without ever seeing a key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = BASE_DIR / "var"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str | None
    anthropic_model: str
    anthropic_max_tokens: int
    data_dir: Path
    db_path: Path
    currency: str
    locale: str
    # GDPR: when True, direct identifiers (email/phone/full address) are never
    # included in any payload sent to the LLM.
    minimise_pii: bool
    cors_origins: list[str]

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


def load_settings() -> Settings:
    data_dir = Path(os.getenv("REVENUEOS_DATA_DIR", str(DEFAULT_DATA_DIR)))
    data_dir.mkdir(parents=True, exist_ok=True)
    origins_raw = os.getenv(
        "REVENUEOS_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    return Settings(
        anthropic_api_key=(os.getenv("ANTHROPIC_API_KEY") or "").strip() or None,
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929"),
        anthropic_max_tokens=_env_int("ANTHROPIC_MAX_TOKENS", 2000),
        data_dir=data_dir,
        db_path=data_dir / os.getenv("REVENUEOS_DB_NAME", "revenueos.db"),
        currency=os.getenv("REVENUEOS_CURRENCY", "EUR"),
        locale=os.getenv("REVENUEOS_LOCALE", "it-IT"),
        minimise_pii=_env_bool("REVENUEOS_MINIMISE_PII", True),
        cors_origins=[o.strip() for o in origins_raw.split(",") if o.strip()],
    )


settings = load_settings()


def public_config() -> dict:
    """Non-sensitive configuration safe to hand to the browser."""
    return {
        "aiEnabled": settings.ai_enabled,
        "aiModel": settings.anthropic_model if settings.ai_enabled else None,
        "currency": settings.currency,
        "locale": settings.locale,
        "minimisePii": settings.minimise_pii,
    }

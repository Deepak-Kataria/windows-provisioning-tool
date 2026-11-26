"""Server settings, read from environment variables (prefix ITOPS_) or a .env file."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# web/server/app/config.py -> repo root is three levels up from web/
WEB_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = WEB_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ITOPS_", env_file=".env", extra="ignore")

    # Postgres in production, e.g. postgresql+psycopg://itops:pw@db:5432/itops
    # SQLite is fine for local dev and tests.
    database_url: str = "sqlite:///./itops-dev.db"

    # Long random string. Used to encrypt TOTP secrets at rest. Never commit the real one.
    secret_key: str = "dev-only-change-me"

    # Public base URL, used in the TOTP issuer and enrollment instructions.
    base_url: str = "http://localhost:8000"
    totp_issuer: str = "IT Provisioning"

    # Cookies. Must be True behind TLS in production.
    cookie_secure: bool = False
    session_cookie: str = "itops_session"
    session_idle_minutes: int = 30
    session_max_hours: int = 12
    pending_mfa_minutes: int = 5

    # Login protection
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    login_rate_per_minute: int = 10  # per client IP

    # Agents
    enrollment_code_hours: int = 24
    heartbeat_seconds: int = 30
    offline_after_seconds: int = 90
    last_seen_write_seconds: int = 60  # throttle DB writes from heartbeats

    # Directory holding action definitions (*.json)
    actions_dir: Path = WEB_DIR / "actions"

    # Trust X-Forwarded-For from the reverse proxy (Caddy). Only enable behind the proxy.
    trust_proxy: bool = False

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()

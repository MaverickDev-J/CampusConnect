"""Application settings – reads from env vars / .env with sensible defaults."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── MongoDB ──────────────────────────────────────────────────────
    # Full URI (includes auth when using Docker with auth enabled)
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB: str = "campusmind"

    # ── JWT ──────────────────────────────────────────────────────────
    JWT_SECRET: str = "super-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 10080       # 7 days

    # ── Superadmin seed ──────────────────────────────────────────────
    SUPERADMIN_EMAIL: str = "superadmin@campusconnect.local"
    SUPERADMIN_PASSWORD: str = "changeme-in-production"

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
    }


settings = Settings()

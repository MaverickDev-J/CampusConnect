"""Application settings – reads from env vars / .env with sensible defaults."""

from dotenv import load_dotenv
load_dotenv()

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

    SUPERADMIN_EMAIL: str = "superadmin@campusconnect.local"
    SUPERADMIN_PASSWORD: str = "changeme-in-production"

    # ── Redis ────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://127.0.0.1:6380/0"
    CELERY_BROKER_URL: str = "redis://127.0.0.1:6380/0"
    CELERY_RESULT_BACKEND: str = "redis://127.0.0.1:6380/0"

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
    }


settings = Settings()

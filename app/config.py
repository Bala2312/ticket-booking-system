from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/ticket_db"
    REDIS_URL: str = "redis://localhost:6379"
    SMTP_HOST: str = "smtp.mailtrap.io"
    SMTP_PORT: int = 2525
    SMTP_USER: str = "demo_user"
    SMTP_PASS: str = "demo_pass"
    FRONTEND_URL: str = "http://localhost:3000"


settings = Settings()
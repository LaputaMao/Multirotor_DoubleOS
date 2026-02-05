import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "Drone_win"
    VERSION: str = "0.9"
    API_V1_STR: str = "/api/v1"

    # 数据库配置 (PostgreSQL)
    # 格式: postgresql+asyncpg://user:password@host:port/dbname
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:123456@localhost:5432/multirotor"
    )

    class Config:
        env_file = ".env"


settings = Settings()

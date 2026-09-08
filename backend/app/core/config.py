from functools import cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    database_uri: str
    sql_echo: bool = False


@cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

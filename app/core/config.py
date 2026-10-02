from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Food Delivery & Logistics API"
    app_env: str = "development"
    debug: bool = False
    database_url: str = "sqlite:///./food_delivery.db"
    secret_key: str = "replace-with-a-long-random-secret-before-production"
    access_token_expire_minutes: int = 30
    jwt_algorithm: str = "HS256"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value: object) -> object:
        if isinstance(value, str) and value.lower() in {"release", "production", "prod"}:
            return False
        return value

    @model_validator(mode="after")
    def validate_security(self) -> "Settings":
        if self.access_token_expire_minutes <= 0:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be positive")
        if self.jwt_algorithm != "HS256":
            raise ValueError("Only HS256 is supported")
        if self.app_env.lower() in {"production", "prod"} and (
            self.secret_key == "replace-with-a-long-random-secret-before-production"
            or len(self.secret_key) < 32
        ):
            raise ValueError("Production requires a unique SECRET_KEY of at least 32 characters")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

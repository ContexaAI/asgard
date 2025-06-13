from typing import Optional, List

from pydantic_settings import BaseSettings, SettingsConfigDict


class ThorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="THOR_",
        env_file=".env",
        env_nested_delimiter="__",
        nested_model_default_partial_update=True,
        extra="ignore",
    )
    
    
    # debugging
    DEBUG: Optional[bool] = False
    
    
    
    # authentication and streaming
    USER_INFO_TOKEN: Optional[str] = "x-userinfo"
    ORGANIZATION_HEADER: Optional[str] = "x-organization"
    
    
    # hermod streaming
    HERMOD_STREAMING_HEADER: Optional[str] = "x-hermod-stream"
    HERMOD_STREAMING_TOKEN_SECRET: Optional[str] = "secret"
    HERMOD_STREAMING_ZERO_MQ_URLS: Optional[List[str]] = ["tcp://localhost:5562"]
    HERMOD_STREAMING_KEEP_ALIVE_TIMEOUT: Optional[int] = 10
    
    
    
    # celery settngs
    CELERY_BROKER: Optional[str] = "redis://localhost:6379/0"
    CELERY_BACKEND: Optional[str] = "redis://localhost:6379/0"
    
settings = ThorSettings()
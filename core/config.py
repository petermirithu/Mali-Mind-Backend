from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str 
    app_version: str

    supabase_url: str
    supabase_key: str

    huggingface_api_key: str
    openrouter_api_key: str
    open_exchange_rates_app_id: str

    cron_secret: str

    class Config:
        env_file = ".env"


settings = Settings()
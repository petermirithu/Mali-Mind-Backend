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

    azure_foundry_api_key: str
    azure_foundry_project_url: str
    azure_foundry_project_model_name: str

    class Config:
        env_file = ".env"


settings = Settings()
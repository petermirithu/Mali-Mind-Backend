from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    app_env: str 
    app_version: str

    supabase_url: str
    supabase_key: str

    huggingface_api_key: str
    openrouter_api_key: str
    open_exchange_rates_app_id: str

    cron_secret: str
    
    firebase_service_account_json: Optional[str] = None  # Firebase service account JSON (for production)

    azure_foundry_api_key: str
    azure_foundry_project_url: str
    azure_foundry_project_model_name: str
    azure_foundry_project_api_version: str

    smtp_host: str
    smtp_port: str
    smtp_username: str
    smtp_password: str
    from_email: str
    from_name: str

    allowed_origins: str  
    api_base_url:str

    model_config = SettingsConfigDict(
        env_file=".env",  # Load from .env if it exists locally
        env_file_encoding='utf-8',
        extra="ignore",
        case_sensitive=False,  # Environment variables are case-insensitive
    )

settings = Settings()
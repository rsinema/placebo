from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_bot_token: str
    moonshot_api_key: str
    database_url: str
    checkin_hour: int = 14
    checkin_minute: int = 0
    checkin_timezone: str = "UTC"
    langsmith_api_key: str = ""
    langsmith_project: str = "placebo"


settings = Settings()

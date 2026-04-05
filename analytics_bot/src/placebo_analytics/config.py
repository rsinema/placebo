from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    placebo_env: str = "dev"  # 'dev' or 'prod'

    # Bot tokens — selected based on PLACEBO_ENV
    analytics_bot_token: str = ""
    test_analytics_bot_token: str = ""
    # Computed at init
    bot_token: str = ""

    moonshot_api_key: str
    database_url: str
    digest_day: int = 0  # 0=Monday, 6=Sunday
    digest_hour: int = 9
    digest_minute: int = 0
    langsmith_api_key: str = ""
    langsmith_project: str = "placebo-analytics"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Resolve bot_token based on environment
        if self.placebo_env == "prod":
            self.bot_token = self.analytics_bot_token
        else:
            self.bot_token = self.test_analytics_bot_token


settings = Settings()

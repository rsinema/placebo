from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    placebo_env: str = "prod"
    gym_telegram_bot_token: str = ""
    test_gym_bot_token: str = ""
    moonshot_api_key: str
    database_url: str
    langsmith_api_key: str = ""
    langsmith_project: str = "placebo-gym"

    @model_validator(mode="after")
    def use_test_token_in_dev(self):
        if self.placebo_env == "dev" and self.test_gym_bot_token:
            self.gym_telegram_bot_token = self.test_gym_bot_token
        return self


settings = Settings()

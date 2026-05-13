from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # Postgres (shared with bot/api)
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "db"
    postgres_port: int = 5432

    # S3
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str
    backup_s3_bucket: str
    backup_s3_prefix: str = "placebo"
    # Optional S3-compatible endpoint (R2, B2, MinIO). Leave blank for AWS S3.
    backup_s3_endpoint_url: str | None = None

    # Schedule and retention
    backup_retention_days: int = 30
    backup_hour_utc: int = 10  # 10:00 UTC ≈ 3am Pacific

    # When True, pre-restore safety snapshots are taken before any restore
    backup_pre_restore_snapshot: bool = True


settings = Settings()

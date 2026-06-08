from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # API authentication
    kyc_api_key: str = "dev-secret"
    admin_secret: str = "admin-secret-change-me"

    # Database
    database_url: str = "postgresql+asyncpg://verify:verify@localhost:5432/webank_verify"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Webhook (BFF endpoint)
    webhook_url: str = "http://localhost:8080/bff/v1/kyc/webhook"
    webhook_secret: str = "webhook-hmac-secret-change-me"

    # GeoIP
    geoip_db_path: str = "./data/GeoLite2-Country.mmdb"

    # S3-compatible storage
    s3_endpoint_url: str = "http://localhost:4566"
    s3_access_key: str = "test"
    s3_secret_key: str = "test"
    s3_bucket: str = "webank-verify"

    # Service
    port: int = 8070
    log_level: str = "INFO"
    environment: str = "development"

    @property
    def is_dev(self) -> bool:
        return self.environment == "development"


settings = Settings()

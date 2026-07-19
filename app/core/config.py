from pydantic_settings import BaseSettings, SettingsConfigDict

# Secrets that ship with insecure placeholder values — refuse to run with
# these in any non-development environment.
_INSECURE_DEFAULTS = {
    "kyc_api_key": "dev-secret",
    "admin_secret": "admin-secret-change-me",
    "webhook_secret": "webhook-hmac-secret-change-me",
}


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
    # s3_endpoint_url is used for uploads (server-side, Docker-internal hostname).
    # s3_public_url is used for presigned URLs returned to the browser; in dev it
    # must point to a host the browser can reach (e.g. localhost:4566 instead of
    # the Docker service name localstack:4566). Defaults to s3_endpoint_url.
    s3_endpoint_url: str = "http://localhost:4566"
    s3_public_url: str = ""
    s3_access_key: str = "test"
    s3_secret_key: str = "test"
    s3_bucket: str = "webank-verify"

    # Service
    port: int = 8070
    log_level: str = "INFO"
    environment: str = "development"
    # Keep ML execution deliberately narrow: each worker loads torch/TensorFlow
    # once and runs one CPU-heavy verification at a time off the event loop.
    inference_workers: int = 1

    @property
    def is_dev(self) -> bool:
        return self.environment == "development"

    def validate_secrets(self) -> None:
        if self.is_dev:
            return
        offenders = [
            name
            for name, default in _INSECURE_DEFAULTS.items()
            if getattr(self, name) == default
        ]
        if offenders:
            raise RuntimeError(
                "Refusing to start in environment="
                f"{self.environment!r} with default secrets: {', '.join(offenders)}. "
                "Set them via environment variables."
            )


settings = Settings()

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SITEPROOF_", env_ignore_empty=True)
    database_url: str = "postgresql://siteproof:siteproof@postgres:5432/siteproof"
    redis_url: str = "redis://redis:6379/0"
    tenant_keys_json: str = ""
    test_fixture_http: bool = False
    browser_key: str = "local-browser-key"
    tenant_key: str = "local-development-key"
    artifact_secret: str = "change-this-local-artifact-secret"
    mode: str = "fixture"
    model_url: str = "https://api.openai.com/v1"
    model_key: str = ""
    model_id: str = "gpt-4.1-mini"
    embedding_version: str = "v1"
    embedding_model: str = "text-embedding-3-small"
    browser_url: str = "http://browser:8081"
    s3_endpoint: str = "http://minio:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "siteproof"

    web_url: str = "http://web:3000"
    render_key: str = "local-render-key"

    input_cost_per_million: float | None = Field(default=None, ge=0)
    output_cost_per_million: float | None = Field(default=None, ge=0)

    embedding_cost_per_million: float | None = Field(default=None, ge=0)
    model_output_limit: int = Field(default=3000, ge=256, le=8000)
    vision_token_allowance: int = Field(default=2048, ge=256, le=16384)
    rerank_url: str = ""
    rerank_model: str = ""
    rerank_key: str = ""

    def tenant_keys(self) -> dict[str, str]:
        import json

        keys = json.loads(self.tenant_keys_json) if self.tenant_keys_json else {"local": self.tenant_key}
        if (
            not isinstance(keys, dict)
            or not keys
            or any(not isinstance(k, str) or not isinstance(v, str) or not v for k, v in keys.items())
        ):
            raise ValueError("SITEPROOF_TENANT_KEYS_JSON must map tenant IDs to nonempty credential strings")
        import re

        if len(set(keys.values())) != len(keys) or any(not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", key) for key in keys):
            raise ValueError("Tenant IDs must be safe identifiers and credentials must be unique")
        return keys


settings = Settings()

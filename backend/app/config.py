import os
from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "EchoTrace"
    app_version: str = "1.0.0"
    debug: bool = os.getenv("ECHOTRACE_DEBUG", "false").lower() == "true"
    host: str = os.getenv("ECHOTRACE_HOST", "127.0.0.1")
    port: int = int(os.getenv("ECHOTRACE_PORT", "8000"))

    # HydraDB connection configuration
    hydradb_bolt_uri: str = os.getenv("HYDRADB_BOLT_URI", "bolt://127.0.0.1:7687")
    hydradb_auth_token: str = os.getenv("HYDRADB_AUTH_TOKEN", "local-development-token-32-bytes")
    hydradb_allow_plaintext: bool = os.getenv("HYDRADB_ALLOW_PLAINTEXT", "true").lower() == "true"
    use_in_memory_fallback: bool = os.getenv("USE_IN_MEMORY_FALLBACK", "false").lower() == "true"

    # Agent executor configuration
    executor_timeout_seconds: float = float(os.getenv("EXECUTOR_TIMEOUT_SECONDS", "30"))
    executor_bearer_token: str = os.getenv("EXECUTOR_BEARER_TOKEN", "")
    executor_allowed_hosts: str = os.getenv("EXECUTOR_ALLOWED_HOSTS", "")


settings = Settings()

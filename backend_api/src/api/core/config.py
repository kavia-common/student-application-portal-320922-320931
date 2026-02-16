import os
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""

    # Security
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60 * 24  # 24 hours

    # CORS
    cors_allow_origins: str = "*"

    # Postgres connection (provided by database container env vars)
    postgres_url: str | None = None
    postgres_user: str | None = None
    postgres_password: str | None = None
    postgres_db: str | None = None
    postgres_port: str | None = None
    postgres_host: str | None = None

    def _normalize_postgres_url(self, raw_url: str) -> str:
        """
        Normalize POSTGRES_URL to ensure it contains credentials if required.

        Why:
            In some preview environments the injected POSTGRES_URL might be a bare
            URL like: postgresql://localhost:5000/mydb
            In that case psycopg2 will try to connect with the OS user, which may not
            exist as a DB role (e.g., role "kavia" does not exist).

        Behavior:
            - If POSTGRES_URL already contains username/password, return as-is.
            - If it's missing credentials but POSTGRES_USER/POSTGRES_PASSWORD are set,
              inject them.
            - Preserve host/port/path/query/fragment.
        """
        parsed = urlparse(raw_url)
        if parsed.scheme not in {"postgresql", "postgres"}:
            return raw_url

        if parsed.username:
            return raw_url

        if self.postgres_user and self.postgres_password:
            # Rebuild netloc as: user:pass@host:port (host/port from parsed)
            host = parsed.hostname or ""
            port = f":{parsed.port}" if parsed.port else ""
            netloc = f"{self.postgres_user}:{self.postgres_password}@{host}{port}"
            rebuilt = parsed._replace(netloc=netloc)
            return urlunparse(rebuilt)

        return raw_url

    def sqlalchemy_database_uri(self) -> str:
        """
        Build the SQLAlchemy database URL.

        Prefers POSTGRES_URL if provided, otherwise constructs from component env vars.
        """
        if self.postgres_url:
            return self._normalize_postgres_url(self.postgres_url)

        # Fall back to component vars; require all to be present.
        missing = [
            name
            for name, val in [
                ("POSTGRES_HOST", self.postgres_host),
                ("POSTGRES_PORT", self.postgres_port),
                ("POSTGRES_USER", self.postgres_user),
                ("POSTGRES_PASSWORD", self.postgres_password),
                ("POSTGRES_DB", self.postgres_db),
            ]
            if not val
        ]
        if missing:
            raise RuntimeError(
                "Database configuration missing. Provide POSTGRES_URL or: "
                + ", ".join(missing)
            )

        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


# PUBLIC_INTERFACE
def get_settings() -> Settings:
    """Load settings from environment variables.

    Notes:
        This service is commonly run in preview/dev environments where not all env vars
        are injected. We therefore provide safe defaults for startup so the FastAPI app
        can bind to its port and serve basic endpoints.

        Security: In production you MUST set JWT_SECRET to a strong, random value.
    """
    jwt_secret = os.getenv("JWT_SECRET")
    if not jwt_secret:
        # Allow preview/dev startup without explicit secret. This prevents import-time
        # crashes that keep the container from binding to port 3001.
        jwt_secret = "dev-insecure-jwt-secret-change-me"

    return Settings(
        jwt_secret=jwt_secret,
        jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
        access_token_ttl_minutes=int(os.getenv("ACCESS_TOKEN_TTL_MINUTES", str(60 * 24))),
        cors_allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*"),
        postgres_url=os.getenv("POSTGRES_URL"),
        postgres_user=os.getenv("POSTGRES_USER"),
        postgres_password=os.getenv("POSTGRES_PASSWORD"),
        postgres_db=os.getenv("POSTGRES_DB"),
        postgres_port=os.getenv("POSTGRES_PORT"),
        postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
    )

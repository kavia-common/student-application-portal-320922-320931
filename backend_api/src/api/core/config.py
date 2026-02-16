import os
from dataclasses import dataclass


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

    def sqlalchemy_database_uri(self) -> str:
        """
        Build the SQLAlchemy database URL.

        Prefers POSTGRES_URL if provided, otherwise constructs from component env vars.
        """
        if self.postgres_url:
            return self.postgres_url

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
    """Load settings from environment variables."""
    jwt_secret = os.getenv("JWT_SECRET")
    if not jwt_secret:
        raise RuntimeError(
            "JWT_SECRET env var is required. Ask orchestrator to set it in .env."
        )

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

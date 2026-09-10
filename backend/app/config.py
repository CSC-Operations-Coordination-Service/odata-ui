"""Application settings, loaded from the environment."""

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    SECRET_KEY must be a urlsafe base64 32-byte key (a Fernet key). Generate one with:
        python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    secret_key: str = ""

    # Path to a file holding the key, used instead of SECRET_KEY. This is how Docker
    # and swarm secrets deliver it (/run/secrets/<name>), and it keeps the key out of
    # the service spec, so `docker service inspect` cannot reveal it.
    secret_key_file: str = ""

    db_path: str = "./data/odata_ui.db"

    # Comma-separated list of allowed browser origins. Both spellings of the loopback
    # host are included by default: they are distinct origins to the browser, and which
    # one the user types in the address bar is not something we control.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Number of query_run rows to keep.
    history_limit: int = 500

    # How long a parsed $metadata document stays cached, in seconds.
    metadata_cache_ttl: int = 600

    # Hard cap on rows returned in a single query, whatever $top asks for.
    max_page_size: int = 5000

    @model_validator(mode="after")
    def _load_secret_key_file(self) -> "Settings":
        """Fold SECRET_KEY_FILE into secret_key, so nothing downstream has to care."""
        if self.secret_key_file and not self.secret_key:
            path = Path(self.secret_key_file)
            if not path.is_file():
                raise ValueError(
                    f"SECRET_KEY_FILE points at {path}, which does not exist."
                )
            self.secret_key = path.read_text().strip()
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

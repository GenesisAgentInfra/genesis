"""Client settings. Repository configuration cannot choose a credential recipient."""

from __future__ import annotations

import json
import os
import stat
import tempfile
import tomllib
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    exclude: list[str] = Field(default_factory=list)
    input_token_budget: int = Field(default=40000, ge=100, le=40000)
    max_excerpt_chars: int = Field(default=12000, ge=100, le=120000)
    max_excerpts: int = Field(default=80, ge=1, le=1000)


def load_settings(repo: Path) -> Settings:
    path = repo / ".genesis" / "config.toml"
    if not path.exists():
        return Settings()
    if path.is_symlink() or not path.resolve().is_relative_to(repo.resolve()):
        raise ValueError("Configuration must be a regular file inside the repository.")
    if path.stat().st_size > 65536:
        raise ValueError("Configuration exceeds 64 KiB.")
    return Settings.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))


def normalize_service_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Service URL must not contain credentials, a query, or a fragment.")
    if not parsed.hostname:
        raise ValueError("Service URL must include a hostname.")
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        raise ValueError("HTTPS is required, except for local development on loopback.")
    if parsed.path not in {"", "/"}:
        raise ValueError("Use the service origin without an API path.")
    # Accessing port also rejects malformed port strings before any network access.
    _ = parsed.port
    return urlunsplit((parsed.scheme, parsed.netloc.lower(), "", "", ""))


def credentials_path() -> Path:
    config_root = os.environ.get("XDG_CONFIG_HOME")
    root = Path(config_root).expanduser() if config_root else Path.home() / ".config"
    return root / "genesis" / "credentials.json"


def save_credentials(api_key: str, service_url: str) -> None:
    if not api_key.strip() or "\n" in api_key or "\r" in api_key:
        raise ValueError("API key must be a nonempty single line.")
    destination = credentials_path()
    if destination.is_symlink() or destination.parent.is_symlink():
        raise ValueError("Credential storage must not be a symbolic link.")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination.parent.chmod(0o700)
    descriptor, temporary = tempfile.mkstemp(prefix="credentials-", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                {"api_key": api_key, "service_url": normalize_service_url(service_url)}, handle
            )
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_credentials() -> dict[str, str]:
    path = credentials_path()
    if not path.exists():
        return {}
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("Credential storage must not be a symbolic link.")
    if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("Credential permissions must be owner-only; run genesis auth again.")
    if path.stat().st_size > 16384:
        raise ValueError("Credential file is too large.")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(v, str) for v in value.values()):
        raise ValueError("Invalid credential file; run genesis auth again.")
    return value


def resolve_connection(explicit_url: str | None) -> tuple[str | None, str | None]:
    selected_url = explicit_url or os.environ.get("GENESIS_SERVICE_URL")
    env_key = os.environ.get("GENESIS_API_KEY")
    if selected_url and env_key:
        return normalize_service_url(selected_url), env_key
    stored = read_credentials()
    selected_url = selected_url or stored.get("service_url")
    url = normalize_service_url(selected_url) if selected_url else None
    if env_key:
        return url, env_key
    # A saved key is never forwarded to a different origin.
    stored_url = stored.get("service_url")
    if url and stored_url and url == normalize_service_url(stored_url):
        return url, stored.get("api_key")
    return url, None

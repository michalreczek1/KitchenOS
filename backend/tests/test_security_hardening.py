import asyncio
import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

os.environ["JWT_SECRET_KEY"] = "test-jwt-secret"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.pop("ENVIRONMENT", None)
os.environ.pop("APP_ENV", None)
os.environ.pop("ALLOWED_ORIGINS", None)
os.environ["GROQ_API_KEY"] = ""

import main  # noqa: E402


def test_parse_allowed_origins_production_requires_explicit_origins():
    with pytest.raises(ValueError, match="ALLOWED_ORIGINS"):
        main.parse_allowed_origins({"ENVIRONMENT": "production"})


def test_parse_allowed_origins_production_rejects_wildcard():
    with pytest.raises(ValueError, match=r"\*"):
        main.parse_allowed_origins(
            {
                "ENVIRONMENT": "production",
                "ALLOWED_ORIGINS": "https://kitchenos.pl,*",
            }
        )


def test_parse_allowed_origins_production_accepts_explicit_origin():
    assert main.parse_allowed_origins(
        {
            "ENVIRONMENT": "production",
            "ALLOWED_ORIGINS": "https://kitchenos.pl",
        }
    ) == ["https://kitchenos.pl"]


def test_parse_allowed_origins_dev_uses_localhost_fallback():
    assert main.parse_allowed_origins({"ENVIRONMENT": "development"}) == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_parse_allowed_origins_dev_ignores_wildcard():
    assert main.parse_allowed_origins(
        {
            "ENVIRONMENT": "development",
            "ALLOWED_ORIGINS": "*",
        }
    ) == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def public_resolver(hostname: str, port: int | None = None) -> list[str]:
    return ["93.184.216.34"]


def test_recipe_url_validation_allows_public_https_domain_format():
    main.validate_recipe_source_url(
        "https://kwestiasmaku.com/przepis/test",
        resolver=public_resolver,
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000",
        "http://127.0.0.1",
        "http://192.168.1.1",
        "ftp://example.com",
        "https:///bez-hosta",
    ],
)
def test_recipe_url_validation_blocks_unsafe_urls(url: str):
    with pytest.raises(HTTPException):
        main.validate_recipe_source_url(url, resolver=public_resolver)


def test_recipe_url_validation_blocks_domain_resolving_to_private_ip():
    def private_resolver(hostname: str, port: int | None = None) -> list[str]:
        return ["93.184.216.34", "10.0.0.5"]

    with pytest.raises(HTTPException):
        main.validate_recipe_source_url("https://example.com/przepis", resolver=private_resolver)


def run_bootstrap(monkeypatch: pytest.MonkeyPatch, enabled: str | None, token_env: str | None, token_request: str | None):
    if enabled is None:
        monkeypatch.delenv("BOOTSTRAP_ENABLED", raising=False)
    else:
        monkeypatch.setenv("BOOTSTRAP_ENABLED", enabled)

    if token_env is None:
        monkeypatch.delenv("ADMIN_BOOTSTRAP_TOKEN", raising=False)
    else:
        monkeypatch.setenv("ADMIN_BOOTSTRAP_TOKEN", token_env)

    request = main.BootstrapRequest(
        email="admin@example.com",
        password="Password123!",
        token=token_request,
    )
    return asyncio.run(main.bootstrap_admin(request, db=None))


def test_bootstrap_disabled_returns_403(monkeypatch):
    with pytest.raises(HTTPException) as exc_info:
        run_bootstrap(monkeypatch, enabled="false", token_env="secret", token_request="secret")

    assert exc_info.value.status_code == 403
    assert "wyłączony" in exc_info.value.detail


def test_bootstrap_enabled_without_token_is_configuration_error(monkeypatch):
    with pytest.raises(HTTPException) as exc_info:
        run_bootstrap(monkeypatch, enabled="true", token_env=None, token_request="secret")

    assert exc_info.value.status_code == 503
    assert "konfiguracji" in exc_info.value.detail


def test_bootstrap_wrong_token_returns_403(monkeypatch):
    with pytest.raises(HTTPException) as exc_info:
        run_bootstrap(monkeypatch, enabled="true", token_env="secret", token_request="wrong")

    assert exc_info.value.status_code == 403
    assert "Nieprawidłowy token" in exc_info.value.detail

"""Serverless cold-start checks without local secrets or external service calls."""
import importlib.util
import json
import os
import socket
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def settings(tmp_path_factory):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    account = {
        "type": "service_account",
        "project_id": "deployment-test",
        "private_key_id": "test-key",
        "private_key": key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
        "client_email": "test@deployment-test.iam.gserviceaccount.com",
        "client_id": "123456789",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    values = {
        "APP_ENV": "production", "APP_VERSION": "test",
        "SUPABASE_URL": "https://example.supabase.co", "SUPABASE_KEY": "test-key",
        "HUGGINGFACE_API_KEY": "", "OPENROUTER_API_KEY": "",
        "OPEN_EXCHANGE_RATES_APP_ID": "test-key", "CRON_SECRET": "test-cron-secret",
        "FIREBASE_SERVICE_ACCOUNT_JSON": json.dumps(account),
        "AZURE_FOUNDRY_API_KEY": "test-key",
        "AZURE_FOUNDRY_PROJECT_URL": "https://example.openai.azure.com",
        "AZURE_FOUNDRY_PROJECT_MODEL_NAME": "test-model",
        "AZURE_FOUNDRY_PROJECT_API_VERSION": "2024-02-15-preview",
        "SMTP_HOST": "smtp.example.com", "SMTP_PORT": "465",
        "SMTP_USERNAME": "test", "SMTP_PASSWORD": "test",
        "FROM_EMAIL": "test@example.com", "FROM_NAME": "Mali",
        "ALLOWED_ORIGINS": "https://frontend.example.com",
        "API_BASE_URL": "https://backend.example.com", "VERCEL": "1",
    }
    with pytest.MonkeyPatch.context() as patch:
        # Do not load the developer's .env or contact real projects during tests.
        patch.chdir(tmp_path_factory.mktemp("vercel-cold-start"))
        patch.syspath_prepend(str(ROOT))
        patch.setattr(socket.socket, "connect", Mock(side_effect=AssertionError("Unexpected network access")))
        patch.setattr(socket.socket, "connect_ex", Mock(side_effect=AssertionError("Unexpected network access")))
        for name in list(os.environ):
            if name.upper() in values:
                patch.delenv(name)
        for name, value in values.items():
            patch.setenv(name, value)
        from core.config import settings as configured
        yield configured


def load_firebase():
    spec = importlib.util.spec_from_file_location(
        "firebase_config_under_test", ROOT / "firebase/config.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("app_env", ["production", "prod", "development"])
def test_firebase_uses_environment_json_on_vercel(settings, monkeypatch, app_env):
    import firebase_admin
    from firebase_admin import credentials

    monkeypatch.setattr(settings, "app_env", app_env)
    monkeypatch.setattr(firebase_admin, "_apps", {})
    certificate = Mock()
    initialize = Mock()
    monkeypatch.setattr(credentials, "Certificate", certificate)
    monkeypatch.setattr(firebase_admin, "initialize_app", initialize)
    load_firebase()
    certificate.assert_called_once_with(json.loads(settings.firebase_service_account_json))
    initialize.assert_called_once_with(certificate.return_value)


@pytest.mark.parametrize("app_env,vercel", [("development", "1"), ("prod", "0"), ("production", "0")])
def test_firebase_never_uses_local_file_in_production(settings, monkeypatch, app_env, vercel):
    import firebase_admin

    monkeypatch.setattr(firebase_admin, "_apps", {})
    monkeypatch.setattr(settings, "app_env", app_env)
    monkeypatch.setattr(settings, "firebase_service_account_json", "")
    monkeypatch.setenv("VERCEL", vercel)
    with pytest.raises(RuntimeError, match="FIREBASE_SERVICE_ACCOUNT_JSON"):
        load_firebase()


def test_firebase_local_file_fallback(settings, monkeypatch):
    import firebase_admin
    from firebase_admin import credentials

    monkeypatch.setattr(firebase_admin, "_apps", {})
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "firebase_service_account_json", None)
    monkeypatch.delenv("VERCEL")
    monkeypatch.setattr(Path, "exists", lambda self: True)
    certificate = Mock()
    monkeypatch.setattr(credentials, "Certificate", certificate)
    monkeypatch.setattr(firebase_admin, "initialize_app", Mock())
    load_firebase()
    certificate.assert_called_once_with(str(ROOT / "firebase/firebase-service-account.json"))


def test_firebase_invalid_json_does_not_echo_credentials(settings, monkeypatch):
    import firebase_admin

    monkeypatch.setattr(firebase_admin, "_apps", {})
    monkeypatch.setattr(settings, "firebase_service_account_json", "private-test-value")
    with pytest.raises(RuntimeError, match="FIREBASE_SERVICE_ACCOUNT_JSON") as error:
        load_firebase()
    assert "private-test-value" not in str(error.value)


@pytest.fixture
def app(settings):
    import main
    return main


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient
    with TestClient(app.app) as test_client:
        yield test_client


def test_cold_start_health_docs_and_schema(app, client):
    assert app.app is app.fast_api_app
    assert client.get("/health").json() == {"status": "healthy"}
    assert client.get("/").json()["version"] == "test"
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    assert "/mali/chat" in schema.json()["paths"]


def test_cors(client):
    response = client.options("/mali/chat", headers={
        "Origin": "https://frontend.example.com",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,authorization",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://frontend.example.com"


@pytest.mark.asyncio
@pytest.mark.parametrize("vercel,expected_calls", [("1", 0), ("0", 1)])
async def test_scheduler_only_runs_on_persistent_hosts(app, monkeypatch, vercel, expected_calls):
    start, stop = Mock(), Mock()
    monkeypatch.setenv("VERCEL", vercel)
    monkeypatch.setattr(app, "start_scheduler", start)
    monkeypatch.setattr(app, "stop_scheduler", stop)
    await app.startup_event()
    await app.shutdown_event()
    assert start.call_count == expected_calls
    assert stop.call_count == expected_calls


CRONS = json.loads((ROOT / "vercel.json").read_text())["crons"]


@pytest.mark.parametrize("job", CRONS, ids=lambda job: job["path"])
def test_crons_reject_unauthenticated_requests(client, job):
    assert client.get(job["path"]).status_code == 401
    assert client.get(job["path"], headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_empty_cron_secret_fails_closed(client, settings, monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "")
    assert client.get("/fetch/forex").status_code == 503


@pytest.mark.parametrize("kind", ["forex", "fuel", "food", "feed"])
@pytest.mark.parametrize("method,headers", [
    ("get", {"Authorization": "Bearer test-cron-secret"}),
    ("post", {"x-cron-secret": "test-cron-secret"}),
])
def test_fetcher_get_and_legacy_post(client, monkeypatch, kind, method, headers):
    from api.routes import fetchers

    fetch = AsyncMock(return_value=[] if kind == "food" else {"status": "ok"})
    insight = AsyncMock(return_value={"summary": "test insight"})
    monkeypatch.setattr(fetchers, f"run_{kind}_fetcher", fetch)
    monkeypatch.setattr(fetchers, "run_insight_pipeline", insight)
    response = getattr(client, method)(f"/fetch/{kind}", headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    fetch.assert_awaited_once()
    assert insight.await_count == (0 if kind == "feed" else 1)


@pytest.mark.parametrize("day,failed,status,calls", [(2, 0, 200, 0), (1, 0, 200, 1), (1, 1, 500, 1)])
def test_monthly_cron_date_guard_and_failure(client, monkeypatch, day, failed, status, calls):
    from api.routes import cron

    class FixedDateTime:
        @staticmethod
        def now(tz):
            return datetime(2026, 10, day, tzinfo=tz)

    archive = Mock(return_value={"archived": 0, "skipped": 0, "failed": failed})
    monkeypatch.setattr(cron, "datetime", FixedDateTime)
    monkeypatch.setattr(cron, "archive_previous_month_spending", archive)
    response = client.get("/cron/monthly-spending", headers={"Authorization": "Bearer test-cron-secret"})
    assert response.status_code == status
    assert archive.call_count == calls


def test_email_templates_are_available_outside_project_directory(app):
    from api.services.email_service import EmailService

    assert "123456" in EmailService._build_verification_email_html("Test", "123456", 15)
    assert "123456" in EmailService._build_forgot_password_email_html("Test", "123456", 15)
    assert "Test" in EmailService._build_password_reset_success_email_html("Test")

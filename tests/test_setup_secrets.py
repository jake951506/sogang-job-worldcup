from __future__ import annotations

import tomllib

from setup_local_secrets import build_toml


def test_generated_secrets_toml_round_trips_private_key_newlines() -> None:
    credentials = {
        "type": "service_account",
        "project_id": "project-test",
        "private_key_id": "key-id",
        "private_key": "-----BEGIN PRIVATE KEY-----\nABC\n-----END PRIVATE KEY-----\n",
        "client_email": "bot@example.iam.gserviceaccount.com",
        "client_id": "123",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://example.invalid/cert",
        "universe_domain": "googleapis.com",
    }

    rendered = build_toml(credentials, "sheet-id", "접속코드")
    parsed = tomllib.loads(rendered)

    assert parsed["google_sheets"]["spreadsheet_id"] == "sheet-id"
    assert parsed["app"]["require_google_storage"] is True
    assert parsed["app"]["access_code"] == "접속코드"
    assert parsed["gcp_service_account"]["private_key"] == credentials["private_key"]

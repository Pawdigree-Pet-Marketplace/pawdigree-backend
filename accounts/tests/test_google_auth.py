import pytest
from google.auth.exceptions import GoogleAuthError

from accounts.google_auth import GoogleTokenError, verify_google_token

TARGET = "accounts.google_auth.id_token.verify_oauth2_token"


def test_unconfigured_client_id_is_rejected(settings):
    settings.GOOGLE_CLIENT_ID = ""

    with pytest.raises(GoogleTokenError):
        verify_google_token("any-token")


def test_unverified_google_email_is_rejected(settings, monkeypatch):
    settings.GOOGLE_CLIENT_ID = "client-id"
    monkeypatch.setattr(
        TARGET,
        lambda token, request, audience: {
            "email": "a@example.com",
            "email_verified": False,
        },
    )

    with pytest.raises(GoogleTokenError):
        verify_google_token("token")


def test_verified_email_is_accepted_and_checked_against_our_client_id(
    settings, monkeypatch
):
    settings.GOOGLE_CLIENT_ID = "client-id"
    seen = {}

    def fake_verify(token, request, audience):
        seen["audience"] = audience
        return {"email": "a@example.com", "email_verified": True}

    monkeypatch.setattr(TARGET, fake_verify)

    info = verify_google_token("token")

    assert info["email"] == "a@example.com"
    assert seen["audience"] == "client-id"


@pytest.mark.parametrize("error", [ValueError("bad"), GoogleAuthError("bad")])
def test_invalid_tokens_are_rejected(settings, monkeypatch, error):
    settings.GOOGLE_CLIENT_ID = "client-id"

    def fake_verify(token, request, audience):
        raise error

    monkeypatch.setattr(TARGET, fake_verify)

    with pytest.raises(GoogleTokenError):
        verify_google_token("token")

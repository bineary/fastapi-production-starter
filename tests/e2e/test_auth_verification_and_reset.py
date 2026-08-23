import pytest
from httpx import AsyncClient

from tests.e2e.conftest import CapturingEmailSender

pytestmark = pytest.mark.e2e


async def test_register_sends_a_verification_email(
    api_client: AsyncClient, email_sender: CapturingEmailSender
) -> None:
    response = await api_client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Verify Co",
            "email": "verify-me@example.com",
            "password": "a-strong-password-123",
            "full_name": "Verify Me",
        },
    )
    assert response.status_code == 201
    assert email_sender.sent[-1]["to"] == "verify-me@example.com"
    assert response.json()["is_email_verified"] is False


async def test_confirm_email_verification(
    api_client: AsyncClient, email_sender: CapturingEmailSender
) -> None:
    await api_client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Verify Co",
            "email": "confirm-verify@example.com",
            "password": "a-strong-password-123",
            "full_name": "Verify Me",
        },
    )
    token = email_sender.last_token()

    confirm = await api_client.post(
        "/api/v1/auth/email-verification/confirm", json={"token": token}
    )
    assert confirm.status_code == 204

    login = await api_client.post(
        "/api/v1/auth/login",
        data={"username": "confirm-verify@example.com", "password": "a-strong-password-123"},
    )
    me = await api_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert me.json()["is_email_verified"] is True


async def test_confirm_email_verification_with_garbage_token_is_unauthorized(
    api_client: AsyncClient,
) -> None:
    response = await api_client.post(
        "/api/v1/auth/email-verification/confirm", json={"token": "not-a-real-token"}
    )
    assert response.status_code == 401


async def test_password_reset_flow(
    api_client: AsyncClient, email_sender: CapturingEmailSender
) -> None:
    await api_client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Reset Co",
            "email": "reset-me@example.com",
            "password": "original-password-123",
            "full_name": "Reset Me",
        },
    )

    reset_request = await api_client.post(
        "/api/v1/auth/password-reset/request", json={"email": "reset-me@example.com"}
    )
    assert reset_request.status_code == 202
    token = email_sender.last_token()

    reset_confirm = await api_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "a-brand-new-password-456"},
    )
    assert reset_confirm.status_code == 204

    old_password_login = await api_client.post(
        "/api/v1/auth/login",
        data={"username": "reset-me@example.com", "password": "original-password-123"},
    )
    assert old_password_login.status_code == 401

    new_password_login = await api_client.post(
        "/api/v1/auth/login",
        data={"username": "reset-me@example.com", "password": "a-brand-new-password-456"},
    )
    assert new_password_login.status_code == 200


async def test_password_reset_request_for_unknown_email_does_not_leak_existence(
    api_client: AsyncClient, email_sender: CapturingEmailSender
) -> None:
    response = await api_client.post(
        "/api/v1/auth/password-reset/request", json={"email": "nobody-here@example.com"}
    )
    assert response.status_code == 202
    assert email_sender.sent == []


async def test_password_reset_confirm_with_garbage_token_is_unauthorized(
    api_client: AsyncClient,
) -> None:
    response = await api_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": "not-a-real-token", "new_password": "whatever-1234"},
    )
    assert response.status_code == 401


async def test_email_verification_token_cannot_be_used_for_password_reset(
    api_client: AsyncClient, email_sender: CapturingEmailSender
) -> None:
    """Purpose-scoped tokens must not be interchangeable — a verification
    token leaking somewhere shouldn't let an attacker reset the password."""
    await api_client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Purpose Co",
            "email": "purpose-check@example.com",
            "password": "a-strong-password-123",
            "full_name": "Purpose Check",
        },
    )
    verification_token = email_sender.last_token()

    response = await api_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": verification_token, "new_password": "whatever-1234"},
    )
    assert response.status_code == 401

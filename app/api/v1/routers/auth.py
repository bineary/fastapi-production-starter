from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.v1.responses import CONFLICT, RATE_LIMITED, UNAUTHORIZED, VALIDATION
from app.core.dependencies import (
    CurrentUser,
    DbSession,
    EmailSenderDep,
    SettingsDep,
    enforce_auth_rate_limit,
)
from app.schemas.auth import (
    ChangePasswordRequest,
    EmailVerificationConfirmRequest,
    LogoutRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.user import UserRead
from app.services.auth_service import AuthService

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    dependencies=[Depends(enforce_auth_rate_limit)],
    responses={**RATE_LIMITED, **VALIDATION},
)


def _service(db: DbSession, settings: SettingsDep, email_sender: EmailSenderDep) -> AuthService:
    return AuthService(db, settings, email_sender)


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new organization and its first (owner) user",
    description=(
        "Creates a brand-new organization and its first user, who is granted the `owner` role. "
        "Also fires a (console-logged) verification email — see the EmailSender design note "
        "in the README."
    ),
    responses={**CONFLICT},
)
async def register(
    body: RegisterRequest, db: DbSession, settings: SettingsDep, email_sender: EmailSenderDep
) -> UserRead:
    service = _service(db, settings, email_sender)
    user = await service.register(
        organization_name=body.organization_name,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
    )
    return UserRead.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Exchange credentials for a token pair",
    responses={**UNAUTHORIZED},
)
async def login(
    db: DbSession,
    settings: SettingsDep,
    email_sender: EmailSenderDep,
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> TokenResponse:
    service = _service(db, settings, email_sender)
    user = await service.authenticate(email=form_data.username, password=form_data.password)
    tokens = await service.issue_token_pair(user)
    return TokenResponse(access_token=tokens.access_token, refresh_token=tokens.refresh_token)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate a refresh token for a new access/refresh pair",
    description=(
        "Presenting a refresh token that was already rotated out (or explicitly revoked) is "
        "treated as token theft: the entire rotation family is revoked, ending every session "
        "descended from it."
    ),
    responses={**UNAUTHORIZED},
)
async def refresh(
    body: RefreshRequest, db: DbSession, settings: SettingsDep, email_sender: EmailSenderDep
) -> TokenResponse:
    service = _service(db, settings, email_sender)
    tokens = await service.refresh(body.refresh_token)
    return TokenResponse(access_token=tokens.access_token, refresh_token=tokens.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke a refresh token")
async def logout(
    body: LogoutRequest, db: DbSession, settings: SettingsDep, email_sender: EmailSenderDep
) -> None:
    service = _service(db, settings, email_sender)
    await service.logout(body.refresh_token)


@router.get(
    "/me",
    response_model=UserRead,
    summary="Get the current authenticated user",
    responses={**UNAUTHORIZED},
)
async def get_me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change the current user's password",
    description="Revokes every existing refresh token — other devices/sessions are logged out.",
    responses={**UNAUTHORIZED},
)
async def change_password(
    body: ChangePasswordRequest,
    current_user: CurrentUser,
    db: DbSession,
    settings: SettingsDep,
    email_sender: EmailSenderDep,
) -> None:
    service = _service(db, settings, email_sender)
    await service.change_password(
        current_user, current_password=body.current_password, new_password=body.new_password
    )


@router.post(
    "/password-reset/request",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a password reset email (stubbed via console EmailSender)",
    description=(
        "Always returns 202, whether or not the email is registered, to avoid leaking "
        "account existence."
    ),
)
async def request_password_reset(
    body: PasswordResetRequest, db: DbSession, settings: SettingsDep, email_sender: EmailSenderDep
) -> None:
    service = _service(db, settings, email_sender)
    await service.request_password_reset(body.email)


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Complete a password reset with the emailed token",
    responses={**UNAUTHORIZED},
)
async def confirm_password_reset(
    body: PasswordResetConfirmRequest,
    db: DbSession,
    settings: SettingsDep,
    email_sender: EmailSenderDep,
) -> None:
    service = _service(db, settings, email_sender)
    await service.confirm_password_reset(token=body.token, new_password=body.new_password)


@router.post(
    "/email-verification/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Confirm an email address with the emailed token",
    responses={**UNAUTHORIZED},
)
async def confirm_email_verification(
    body: EmailVerificationConfirmRequest,
    db: DbSession,
    settings: SettingsDep,
    email_sender: EmailSenderDep,
) -> None:
    service = _service(db, settings, email_sender)
    await service.verify_email(body.token)

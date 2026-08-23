from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    organization_name: str = Field(min_length=1, max_length=200, examples=["Acme Inc."])
    email: EmailStr = Field(examples=["owner@acme.test"])
    password: str = Field(min_length=8, max_length=128, examples=["a-strong-password-123"])
    full_name: str = Field(min_length=1, max_length=200, examples=["Ada Lovelace"])


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class EmailVerificationConfirmRequest(BaseModel):
    token: str

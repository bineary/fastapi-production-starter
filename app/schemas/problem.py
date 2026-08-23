from pydantic import BaseModel, Field


class ProblemDetail(BaseModel):
    """RFC 9457 `application/problem+json` error shape — returned by every
    error response in this API instead of ad-hoc `{"detail": ...}` bodies."""

    type: str = Field(examples=["/problems/not-found"])
    title: str = Field(examples=["Not Found"])
    status: int = Field(examples=[404])
    detail: str = Field(examples=["Project not found"])
    instance: str = Field(examples=["/api/v1/projects/3fa85f64-5717-4562-b3fc-2c963f66afa6"])
    trace_id: str = Field(examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"])


class ValidationProblemDetail(ProblemDetail):
    errors: list[dict[str, str]] = Field(
        examples=[
            [
                {
                    "field": "email",
                    "message": "value is not a valid email address",
                    "type": "value_error",
                }
            ]
        ]
    )

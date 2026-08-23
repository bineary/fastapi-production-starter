import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200, examples=["Website Relaunch"])
    description: str | None = Field(default=None, max_length=10_000)


class ProjectUpdate(BaseModel):
    """All fields optional — a PATCH only changes what's provided."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    created_by_id: uuid.UUID | None
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

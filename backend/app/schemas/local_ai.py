from typing import Optional

from sqlmodel import SQLModel


class LocalAIStatusRead(SQLModel):
    enabled: bool
    provider: str
    base_url: str
    model_name: Optional[str] = None
    is_localhost: bool
    reachable: bool
    vision_capable: str
    message: str


class LocalAIConfigRead(SQLModel):
    enabled: bool
    provider: str
    base_url: str
    model_name: Optional[str] = None
    timeout_seconds: int
    is_localhost: bool


class LocalAITestConnectionRead(SQLModel):
    ok: bool
    reachable: bool
    models: list[str]
    message: str

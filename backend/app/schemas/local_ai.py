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
    max_images: int
    max_tokens: int
    disable_thinking: bool
    is_localhost: bool


class LocalAITestConnectionRead(SQLModel):
    ok: bool
    reachable: bool
    models: list[str]
    selected_model: Optional[str] = None
    selected_model_found: bool
    message: str

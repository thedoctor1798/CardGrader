from typing import Optional

from sqlmodel import SQLModel


class LocalAIStatusRead(SQLModel):
    mode: str = "disabled"
    enabled: bool
    provider: str
    base_url: str
    worker_base_url: Optional[str] = None
    model_name: Optional[str] = None
    is_localhost: bool
    reachable: bool
    worker_reachable: bool = False
    vision_capable: str
    server_role: str = "local_app"
    client_role: str = "same_machine"
    message: str


class LocalAIConfigRead(SQLModel):
    mode: str = "disabled"
    enabled: bool
    provider: str
    base_url: str
    worker_base_url: Optional[str] = None
    model_name: Optional[str] = None
    timeout_seconds: int
    max_images: int
    max_tokens: int
    disable_thinking: bool
    is_localhost: bool
    server_role: str = "local_app"
    client_role: str = "same_machine"


class LocalAITestConnectionRead(SQLModel):
    ok: bool
    reachable: bool
    mode: str = "disabled"
    worker_reachable: bool = False
    models: list[str]
    selected_model: Optional[str] = None
    selected_model_found: bool
    message: str

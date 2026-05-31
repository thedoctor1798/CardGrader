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
    ai_model: str = "auto"
    context_tokens: int = 15000
    phase_a_tokens: int = 1500
    phase_b_tokens: int = 2500
    temperature: float = 0.1
    send_diagnostic_images: bool = True


class LocalAITestConnectionRead(SQLModel):
    ok: bool
    reachable: bool
    mode: str = "disabled"
    worker_reachable: bool = False
    models: list[str]
    selected_model: Optional[str] = None
    selected_model_found: bool
    message: str


class LocalAISettingsRead(SQLModel):
    ai_model: str = "auto"
    context_tokens: int = 15000
    phase_a_tokens: int = 1500
    phase_b_tokens: int = 2500
    temperature: float = 0.1
    send_diagnostic_images: bool = True
    disable_thinking: bool = True


class LocalAISettingsUpdate(SQLModel):
    ai_model: Optional[str] = None
    context_tokens: Optional[int] = None
    phase_a_tokens: Optional[int] = None
    phase_b_tokens: Optional[int] = None
    temperature: Optional[float] = None
    send_diagnostic_images: Optional[bool] = None
    disable_thinking: Optional[bool] = None

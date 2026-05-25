import time
from dataclasses import dataclass


@dataclass
class ProviderRateState:
    last_request_at: float = 0.0
    blocked_until: float = 0.0


_states: dict[str, ProviderRateState] = {}


def rate_state(provider: str) -> ProviderRateState:
    return _states.setdefault(provider, ProviderRateState())


def provider_blocked_seconds(provider: str) -> float:
    state = rate_state(provider)
    remaining = state.blocked_until - time.monotonic()
    return max(0.0, remaining)


def wait_for_provider_slot(provider: str, interval_seconds: float) -> None:
    if interval_seconds <= 0:
        rate_state(provider).last_request_at = time.monotonic()
        return
    state = rate_state(provider)
    blocked = provider_blocked_seconds(provider)
    if blocked > 0:
        time.sleep(blocked)
    now = time.monotonic()
    elapsed = now - state.last_request_at
    if elapsed < interval_seconds:
        time.sleep(interval_seconds - elapsed)
    state.last_request_at = time.monotonic()


def block_provider(provider: str, retry_after_seconds: int | float | None = None) -> None:
    if retry_after_seconds is None or retry_after_seconds <= 0:
        return
    state = rate_state(provider)
    state.blocked_until = max(state.blocked_until, time.monotonic() + float(retry_after_seconds))

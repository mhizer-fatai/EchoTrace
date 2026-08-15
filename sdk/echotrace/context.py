import contextvars
from typing import Optional

_current_agent_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_agent_id", default=None
)
_current_session_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_session_id", default="default"
)


def get_current_agent_id() -> Optional[str]:
    return _current_agent_id.get()


def set_current_agent_id(agent_id: Optional[str]) -> contextvars.Token:
    return _current_agent_id.set(agent_id)


def reset_current_agent_id(token: contextvars.Token):
    _current_agent_id.reset(token)


def get_current_session_id() -> str:
    return _current_session_id.get()


def set_current_session_id(session_id: str) -> contextvars.Token:
    return _current_session_id.set(session_id)


def reset_current_session_id(token: contextvars.Token):
    _current_session_id.reset(token)

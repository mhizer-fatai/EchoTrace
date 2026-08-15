from functools import wraps
import inspect
import logging
from typing import Any, Callable, Dict, List, Optional
import requests

from sdk.echotrace.context import (
    get_current_agent_id,
    get_current_session_id,
    set_current_agent_id,
    set_current_session_id,
    reset_current_agent_id,
    reset_current_session_id,
)

logger = logging.getLogger("echotrace.sdk")


class EchoTrace:
    """
    Main developer SDK client for instrumenting multi-agent systems with EchoTrace.
    """

    def __init__(self, endpoint: str = "http://127.0.0.1:8000", session_id: str = "default"):
        self.endpoint = endpoint.rstrip("/")
        self.default_session_id = session_id

    def agent(self, name: str, role: Optional[str] = None):
        """
        Decorator to register and trace an agent execution context.
        """
        def decorator(func: Callable):
            agent_id = f"agent_{name.lower().replace(' ', '_')}"
            agent_role = role or name

            @wraps(func)
            def wrapper(*args, **kwargs):
                token_agent = set_current_agent_id(agent_id)
                token_session = set_current_session_id(self.default_session_id)
                try:
                    return func(*args, **kwargs)
                finally:
                    reset_current_agent_id(token_agent)
                    reset_current_session_id(token_session)

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                token_agent = set_current_agent_id(agent_id)
                token_session = set_current_session_id(self.default_session_id)
                try:
                    return await func(*args, **kwargs)
                finally:
                    reset_current_agent_id(token_agent)
                    reset_current_session_id(token_session)

            if inspect.iscoroutinefunction(func):
                return async_wrapper
            return wrapper

        return decorator

    def log_fact(
        self,
        entity: str,
        property_name: str,
        property_value: str,
        confidence: float = 1.0,
        evidence_source: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """
        Logs a factual belief discovered by the active agent into HydraDB.
        """
        sess = session_id or get_current_session_id() or self.default_session_id
        agent_id = get_current_agent_id()

        payload = {
            "session_id": sess,
            "entity": entity,
            "property_name": property_name,
            "property_value": str(property_value),
            "agent_id": agent_id,
            "confidence": confidence,
            "evidence_source": evidence_source,
        }

        try:
            resp = requests.post(f"{self.endpoint}/api/ingest/fact", json=payload, timeout=5)
            if resp.status_code == 200:
                return resp.json().get("fact_id", "")
        except Exception as exc:
            logger.debug(f"EchoTrace SDK ingestion warning (fact): {exc}")
        return ""

    def log_decision(
        self,
        action_type: str,
        rationale: str,
        depends_on: Optional[List[str]] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """
        Logs an architecture, planning, or code decision with explicit fact dependencies.
        """
        sess = session_id or get_current_session_id() or self.default_session_id
        agent_id = get_current_agent_id() or "agent_unknown"

        payload = {
            "session_id": sess,
            "agent_id": agent_id,
            "action_type": action_type,
            "rationale": rationale,
            "depends_on_fact_ids": depends_on or [],
        }

        try:
            resp = requests.post(f"{self.endpoint}/api/ingest/decision", json=payload, timeout=5)
            if resp.status_code == 200:
                return resp.json().get("decision_id", "")
        except Exception as exc:
            logger.debug(f"EchoTrace SDK ingestion warning (decision): {exc}")
        return ""

    def log_artifact(
        self,
        artifact_name: str,
        content: str,
        decision_id: str,
        artifact_type: str = "code",
        session_id: Optional[str] = None,
    ) -> str:
        """
        Logs an output artifact (e.g. source file, test, plan) linked to the triggering decision.
        """
        sess = session_id or get_current_session_id() or self.default_session_id

        payload = {
            "session_id": sess,
            "artifact_name": artifact_name,
            "content": content,
            "artifact_type": artifact_type,
            "decision_id": decision_id,
        }

        try:
            resp = requests.post(f"{self.endpoint}/api/ingest/artifact", json=payload, timeout=5)
            if resp.status_code == 200:
                return resp.json().get("artifact_id", "")
        except Exception as exc:
            logger.debug(f"EchoTrace SDK ingestion warning (artifact): {exc}")
        return ""

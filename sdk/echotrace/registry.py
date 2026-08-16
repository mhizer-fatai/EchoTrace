import inspect
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("echotrace.sdk.registry")


class AgentHandler:
    def __init__(self, name: str, role: str, func: Callable, description: Optional[str] = None):
        self.name = name
        self.role = role
        self.func = func
        self.description = description or func.__doc__ or f"Agent responsible for {role}"
        self.signature = inspect.signature(func)

    def execute(self, *args, **kwargs) -> Any:
        return self.func(*args, **kwargs)

    async def execute_async(self, *args, **kwargs) -> Any:
        if inspect.iscoroutinefunction(self.func):
            return await self.func(*args, **kwargs)
        return self.func(*args, **kwargs)


class AgentRegistry:
    """
    Global registry for executable agent handlers in EchoTrace.
    Enables true autonomous re-execution and healing of stale decisions.
    """

    def __init__(self):
        self._handlers: Dict[str, AgentHandler] = {}

    def register(self, name: str, role: str, func: Callable, description: Optional[str] = None) -> AgentHandler:
        handler_key = name.lower().replace(" ", "_")
        handler = AgentHandler(name=name, role=role, func=func, description=description)
        self._handlers[handler_key] = handler
        logger.info(f"Registered executable agent handler: {handler_key} ({role})")
        return handler

    def get_handler(self, name: str) -> Optional[AgentHandler]:
        handler_key = name.lower().replace(" ", "_")
        return self._handlers.get(handler_key)

    def list_handlers(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": h.name,
                "role": h.role,
                "description": h.description,
                "parameters": list(h.signature.parameters.keys()),
            }
            for h in self._handlers.values()
        ]


# Global singleton agent registry
agent_registry = AgentRegistry()

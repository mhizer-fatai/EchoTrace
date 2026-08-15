import pytest
from sdk.echotrace.tracer import EchoTrace
from sdk.echotrace.context import get_current_agent_id


def test_sdk_agent_decorator():
    tracer = EchoTrace(session_id="test_sdk_session")

    @tracer.agent(name="DataAnalyst", role="Analyst")
    def analyze_dataset():
        agent_id = get_current_agent_id()
        return agent_id

    result_agent_id = analyze_dataset()
    assert result_agent_id == "agent_dataanalyst"
    # Ensure context resets after function completes
    assert get_current_agent_id() is None

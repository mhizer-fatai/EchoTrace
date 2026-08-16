import pytest
from unittest.mock import Mock, patch
from sdk.echotrace.tracer import EchoTrace
from sdk.echotrace.context import get_current_agent_id


def test_sdk_agent_decorator():
    tracer = EchoTrace(session_id="test_sdk_session")

    @tracer.agent(name="DataAnalyst", role="Analyst")
    def analyze_dataset():
        agent_id = get_current_agent_id()
        return agent_id

    response = Mock()
    response.raise_for_status.return_value = None
    with patch("sdk.echotrace.tracer.requests.post", return_value=response) as post:
        result_agent_id = analyze_dataset()
    assert result_agent_id == "agent_dataanalyst"
    assert post.call_args.args[0].endswith("/api/ingest/agent")
    # Ensure context resets after function completes
    assert get_current_agent_id() is None

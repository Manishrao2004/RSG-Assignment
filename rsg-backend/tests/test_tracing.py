from contextlib import contextmanager

from app.main_agent.tracing import AgentTracing


def test_tracing_disabled_without_key(settings, monkeypatch):
    observed = {}

    @contextmanager
    def capture(**kwargs):
        observed.update(kwargs)
        yield

    monkeypatch.setattr("app.main_agent.tracing.tracing_context", capture)
    tracer = AgentTracing(settings)
    with tracer.turn("conversation-1"):
        pass
    assert observed["enabled"] is False
    assert observed["metadata"]["thread_id"] == "conversation-1"


def test_tracing_client_project_and_shutdown(settings, monkeypatch):
    observed = {}

    class FakeClient:
        def __init__(self, **kwargs):
            observed["client_args"] = kwargs

        def flush(self):
            observed["flushed"] = True

        def close(self):
            observed["closed"] = True

    @contextmanager
    def capture(**kwargs):
        observed.update(kwargs)
        yield

    monkeypatch.setattr("app.main_agent.tracing.Client", FakeClient)
    monkeypatch.setattr("app.main_agent.tracing.tracing_context", capture)
    tracer = AgentTracing(
        settings.model_copy(
            update={
                "langsmith_tracing": True,
                "langsmith_api_key": "test-key",
                "langsmith_project": "test-project",
            }
        )
    )
    with tracer.turn("conversation-2"):
        pass
    tracer.close()
    assert observed["enabled"] is True
    assert observed["project_name"] == "test-project"
    assert observed["metadata"]["thread_id"] == "conversation-2"
    assert "test-key" not in str(observed["metadata"])
    assert observed["flushed"] and observed["closed"]

"""Explicit per-request LangSmith context; no global environment mutation."""

from contextlib import contextmanager

from langsmith import Client, tracing_context


class AgentTracing:
    def __init__(self, settings):
        self.settings = settings
        self.client = None
        if settings.langsmith_tracing and settings.langsmith_api_key:
            self.client = Client(api_key=settings.langsmith_api_key, api_url=settings.langsmith_endpoint)

    @contextmanager
    def turn(self, thread_id: str):
        with tracing_context(
            enabled=self.client is not None,
            client=self.client,
            project_name=self.settings.langsmith_project,
            tags=["rsg", "sales-main-agent"],
            metadata={"thread_id": thread_id, "model": self.settings.groq_model},
        ):
            yield

    def close(self):
        if self.client:
            self.client.flush()
            self.client.close()

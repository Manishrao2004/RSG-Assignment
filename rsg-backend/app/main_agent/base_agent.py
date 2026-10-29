"""Adapted from the existing agent model: model, tools and system prompt."""

from langchain_groq import ChatGroq

from app.config import Settings
from app.main_agent.prompts import SYSTEM_PROMPT
from app.main_agent.tools import make_query_tools


class BaseAgent:
    def __init__(self, settings: Settings, model=None):
        self.settings = settings
        self.tools = make_query_tools(settings.db_path)
        self.tool_map = {tool.name: tool for tool in self.tools}
        self.model = model

    def get_model(self, final_only: bool = False):
        if self.model is None:
            self.model = ChatGroq(
                api_key=self.settings.groq_api_key,
                model=self.settings.groq_model,
                temperature=0,
                max_tokens=1200,
                timeout=25,
                max_retries=1,
                **({"reasoning_effort": "low"} if "gpt-oss" in self.settings.groq_model else {}),
            )
        tools = [tool for tool in self.tools if tool.name != "final_answer"]
        return self.model.bind_tools(
            tools,
            tool_choice="none" if final_only else "auto",
            parallel_tool_calls=False,
        )

    def system_prompt(self, final_only: bool = False) -> str:
        return SYSTEM_PROMPT + (
            "\nTool budget exhausted. Finish now; do not request further queries." if final_only else ""
        )

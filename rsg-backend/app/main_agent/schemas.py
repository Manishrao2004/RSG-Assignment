from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=2000)
    thread_id: UUID | None = None

    @field_validator("question")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if len(value.strip()) < 3:
            raise ValueError("Enter at least three characters.")
        return value.strip()


class MainAgentAnswer(BaseModel):
    """Like the reference agent: answer, clarification, or an explicit inability."""

    model_config = ConfigDict(extra="forbid")
    type: Literal["answer", "clarification", "cant_answer", "off_scope"]
    message: str = Field(min_length=1, max_length=12000)
    supporting_query_ids: list[str] = Field(default_factory=list, max_length=8)

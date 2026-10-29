"""Request-scoped read tools, adapted from the reference's make_query_tools."""

import sqlite3
from pathlib import Path
from uuid import uuid4

from langchain_core.tools import tool

from app.database import quality
from app.main_agent.query import QueryRejected, execute_query
from app.main_agent.schemas import MainAgentAnswer


def make_query_tools(db_path: Path):
    @tool
    def sql_query(sql: str, parameters: dict[str, str | int | float | None] | None = None) -> dict:
        """Run one SQLite SELECT on sales. Write SQL using the schema in your prompt.

        Use named parameters for user-provided filter values. The server validates
        SQL and scopes every sales reference to Completed transactions. You may use
        aggregates, joins, CTEs and window functions. Errors are NOT empty results:
        read the error, correct your query and retry. At most 100 rows are returned.
        """
        try:
            return execute_query(db_path, sql, parameters)
        except (QueryRejected, sqlite3.Error, ValueError, OverflowError) as exc:
            return {
                "error": str(exc),
                "instruction": "This query did not succeed. Correct it; do not invent results.",
            }

    @tool
    def data_quality() -> dict:
        """Get actual import counts and reasons for quarantined or excluded records."""
        report = quality(db_path)
        return {
            "query_id": uuid4().hex,
            "tool": "data_quality",
            "columns": [
                "source_rows",
                "accepted_rows",
                "eligible_rows",
                "quarantined_rows",
                "excluded_status_rows",
            ],
            "rows": [
                {
                    key: report[key]
                    for key in (
                        "source_rows",
                        "accepted_rows",
                        "eligible_rows",
                        "quarantined_rows",
                        "excluded_status_rows",
                    )
                }
            ],
            "report": report,
            "truncated": False,
        }

    @tool(args_schema=MainAgentAnswer)
    def final_answer(type: str, message: str, supporting_query_ids: list[str] | None = None) -> dict:
        """Finish this turn with an answer grounded in successful query IDs.

        For ambiguous questions use clarification and ask one concise question.
        For unavailable information use cant_answer; unrelated topics use off_scope.
        An answer requires at least one real query ID from a successful tool result.
        """
        return {"type": type, "message": message, "supporting_query_ids": supporting_query_ids or []}

    return [sql_query, data_quality, final_answer]

"""Adapted from the existing agent's SQL guard: AST validation plus scoped sources."""

import sqlite3
import time
from pathlib import Path
from uuid import uuid4

import sqlglot
from sqlglot import exp

from app.database import readonly

MAX_ROWS = 100
FUNCTIONS = {
    "sum",
    "count",
    "min",
    "max",
    "avg",
    "round",
    "substr",
    "substring",
    "strftime",
    "coalesce",
    "nullif",
    "abs",
    "lower",
    "upper",
    "length",
    "date",
    "like",
    "total",
    "ifnull",
    "cast",
    "printf",
    "row_number",
    "rank",
    "dense_rank",
    "lag",
    "lead",
}
FORBIDDEN = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.Command,
    exp.Into,
    exp.Transaction,
)


class QueryRejected(ValueError):
    pass


def guard_sql(sql: str) -> str:
    """Allow one SELECT and replace every sales reference with completed sales.

    This is the same source-substitution approach as the reference's scope guard.
    It works inside joins, subqueries, CTEs, and UNIONs, rather than appending a
    WHERE clause that a generated OR predicate could bypass.
    """
    if len(sql) > 12000:
        raise QueryRejected("SQL is too long.")
    try:
        statements = sqlglot.parse(sql, read="sqlite")
    except sqlglot.errors.ParseError as exc:
        raise QueryRejected(f"Invalid SQLite SQL: {exc}") from exc
    if len(statements) != 1 or not isinstance(
        statements[0], (exp.Select, exp.Union, exp.Intersect, exp.Except)
    ):
        raise QueryRejected("Only one read-only SELECT statement is allowed.")
    tree = statements[0]
    if any(isinstance(node, FORBIDDEN) for node in tree.walk()):
        raise QueryRejected("Data-changing SQL is forbidden, including inside CTEs.")
    ctes = {cte.alias.lower() for cte in tree.find_all(exp.CTE)}
    if "sales" in ctes:
        raise QueryRejected("A CTE may not shadow the sales table.")
    sales_seen = False
    for table in list(tree.find_all(exp.Table)):
        name = table.name.lower()
        if table.db or table.catalog:
            raise QueryRejected("Cross-database references are forbidden.")
        if name in ctes:
            continue
        if name != "sales":
            raise QueryRejected(f"Unknown or forbidden table: {table.name}. Only sales is queryable.")
        sales_seen = True
        scoped = sqlglot.parse_one("SELECT * FROM sales WHERE status = 'Completed'", read="sqlite")
        table.replace(scoped.subquery(alias=table.alias_or_name))
    if not sales_seen:
        raise QueryRejected("Query the actual sales table; constant-only answers are not evidence.")
    return tree.sql(dialect="sqlite")


def execute_query(db_path: Path, sql: str, parameters: dict | None = None) -> dict:
    validated = guard_sql(sql)
    started = time.monotonic()
    with readonly(db_path) as conn:

        def authorize(action, arg1, arg2, database, source):
            if action == sqlite3.SQLITE_READ:
                return sqlite3.SQLITE_OK if arg1 == "sales" else sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_FUNCTION:
                return sqlite3.SQLITE_OK if (arg2 or "").lower() in FUNCTIONS else sqlite3.SQLITE_DENY
            return (
                sqlite3.SQLITE_OK
                if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE)
                else sqlite3.SQLITE_DENY
            )

        conn.set_authorizer(authorize)
        steps = 0

        def interrupt():
            nonlocal steps
            steps += 1
            return int(steps > 500 or time.monotonic() - started > 2)

        conn.set_progress_handler(interrupt, 1000)
        cursor = conn.execute(validated, parameters or {})
        columns = [column[0] for column in cursor.description]
        if len(set(columns)) != len(columns):
            raise QueryRejected("Give result columns distinct aliases.")
        rows = [dict(row) for row in cursor.fetchmany(MAX_ROWS + 1)]
    return {
        "query_id": uuid4().hex,
        "sql": sql,
        "executed_sql": validated,
        "parameters": parameters or {},
        "columns": columns,
        "rows": rows[:MAX_ROWS],
        "row_count": min(len(rows), MAX_ROWS),
        "truncated": len(rows) > MAX_ROWS,
    }

import csv
import sqlite3
from decimal import Decimal

import pytest

from app.database import initialize, quality
from app.main_agent.query import QueryRejected, execute_query, guard_sql


@pytest.fixture
def database(settings):
    initialize(settings.db_path, settings.csv_path)
    return settings.db_path


def test_total_against_independent_csv(database, settings):
    with settings.csv_path.open(newline="", encoding="utf-8-sig") as source:
        expected = sum(
            Decimal(row["Quantity"]) * Decimal(row["Unit_price"]) - Decimal(row["Discount_amount"])
            for row in csv.DictReader(source)
            if row["Status"] == "Completed" and row["Unit_price"] and int(row["Quantity"]) > 0
        )
    result = execute_query(database, "SELECT SUM(revenue_cents)/100.0 AS revenue FROM sales")
    assert Decimal(str(result["rows"][0]["revenue"])) == expected == Decimal("1439200")


@pytest.mark.parametrize(
    "sql,label,value",
    [
        (
            "SELECT product, SUM(revenue_cents)/100.0 AS revenue FROM sales GROUP BY product ORDER BY revenue DESC LIMIT 1",
            "Monitor",
            473000,
        ),
        (
            "SELECT product, SUM(revenue_cents)/100.0 AS revenue FROM sales GROUP BY product ORDER BY revenue ASC LIMIT 1",
            "Laptop Stand",
            96000,
        ),
        (
            "SELECT region, SUM(revenue_cents)/100.0 AS revenue FROM sales GROUP BY region ORDER BY revenue DESC LIMIT 1",
            "South",
            411200,
        ),
        (
            "SELECT region, SUM(revenue_cents)/100.0 AS revenue FROM sales GROUP BY region ORDER BY revenue ASC LIMIT 1",
            "West",
            296850,
        ),
    ],
)
def test_highest_and_lowest(database, sql, label, value):
    row = execute_query(database, sql)["rows"][0]
    assert list(row.values()) == [label, value]


def test_monthly_and_comparison(database):
    rows = execute_query(
        database,
        "SELECT substr(order_date,1,7) AS month, SUM(revenue_cents)/100.0 AS revenue FROM sales GROUP BY month ORDER BY month",
    )["rows"]
    assert [row["revenue"] for row in rows] == [210250, 234600, 223900, 240700, 318500, 211250]
    sql = """WITH months AS (SELECT substr(order_date,1,7) AS month, SUM(revenue_cents)/100.0 AS revenue FROM sales GROUP BY month), values_to_compare AS (SELECT (SELECT revenue FROM months WHERE month=:baseline) AS baseline, (SELECT revenue FROM months WHERE month=:target) AS target) SELECT baseline,target,target-baseline AS change,ROUND((target-baseline)*100.0/NULLIF(baseline,0),2) AS percentage_change FROM values_to_compare"""
    row = execute_query(database, sql, {"baseline": "2026-01", "target": "2026-02"})["rows"][0]
    assert row == {"baseline": 210250, "target": 234600, "change": 24350, "percentage_change": 11.58}
    assert (
        execute_query(database, sql, {"baseline": "2026-12", "target": "2026-02"})["rows"][0]["change"]
        is None
    )


def test_scoped_nested_cte_and_union(database):
    result = execute_query(
        database,
        "WITH x AS (SELECT COUNT(*) AS n FROM sales WHERE status='Returned' OR 1=1) SELECT n FROM x UNION ALL SELECT COUNT(*) AS n FROM sales WHERE status='Returned'",
    )
    assert result["rows"] == [{"n": 48}, {"n": 0}]


def test_parameters_do_not_execute_injected_value(database):
    result = execute_query(
        database,
        "SELECT COUNT(*) AS n FROM sales WHERE region=:region",
        {"region": "North'; DROP TABLE sales;--"},
    )
    assert result["rows"] == [{"n": 0}]
    assert quality(database)["eligible_rows"] == 48


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE sales",
        "DELETE FROM sales",
        "UPDATE sales SET quantity=1",
        "SELECT * FROM sales; DELETE FROM sales",
        "PRAGMA query_only=OFF",
        "ATTACH DATABASE ':memory:' AS evil",
        "SELECT * FROM sqlite_master",
        "SELECT * FROM metadata",
        "SELECT * FROM main.sales",
        "WITH sales AS (SELECT 99) SELECT * FROM sales",
        "SELECT 99999 AS revenue",
        "SELECT * FROM pragma_table_info('sales')",
    ],
)
def test_reject_unsafe_sql(sql):
    with pytest.raises(QueryRejected):
        guard_sql(sql)


def test_forbidden_functions_and_expensive_query(database):
    with pytest.raises(sqlite3.DatabaseError):
        execute_query(database, "SELECT load_extension('evil') FROM sales")
    with pytest.raises(sqlite3.DatabaseError):
        execute_query(
            database,
            "SELECT COUNT(*) FROM sales a CROSS JOIN sales b CROSS JOIN sales c CROSS JOIN sales d CROSS JOIN sales e",
        )


def test_limit_and_duplicate_columns(database):
    result = execute_query(database, "SELECT a.product FROM sales a CROSS JOIN sales b")
    assert result["truncated"] and len(result["rows"]) == 100
    with pytest.raises(QueryRejected):
        execute_query(database, "SELECT product,product FROM sales")


def test_import_quality_and_idempotency(database, settings):
    initialize(database, settings.csv_path)
    report = quality(database)
    assert (report["source_rows"], report["accepted_rows"], report["eligible_rows"]) == (51, 49, 48)
    assert {row["transaction_id"] for row in report["issues"]} == {"TXN0034", "TXN0051"}

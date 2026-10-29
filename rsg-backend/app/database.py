"""Validated, idempotent CSV ingestion and restricted read access."""

import csv
import hashlib
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.schemas import CATEGORIES, CHANNELS, PRODUCTS, REGIONS

REQUIRED = {
    "Transaction_Id",
    "Order_date",
    "Product",
    "Category",
    "Region",
    "Sales_channel",
    "Quantity",
    "Unit_price",
    "Discount_amount",
    "Status",
}


def money(value: str) -> int:
    amount = Decimal(value.strip())
    if not amount.is_finite() or amount < 0 or amount != amount.quantize(Decimal("0.01")):
        raise ValueError("Money must be nonnegative with at most two decimal places.")
    return int(amount * 100)


def initialize(db_path: Path, csv_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sales (
                transaction_id TEXT PRIMARY KEY, order_date TEXT NOT NULL,
                product TEXT NOT NULL, category TEXT NOT NULL, region TEXT NOT NULL,
                channel TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity > 0),
                unit_price_cents INTEGER NOT NULL CHECK(unit_price_cents >= 0),
                discount_cents INTEGER NOT NULL CHECK(discount_cents >= 0),
                status TEXT NOT NULL CHECK(status IN ('Completed','Returned','Cancelled')),
                revenue_cents INTEGER NOT NULL CHECK(revenue_cents >= 0)
            );
            CREATE TABLE IF NOT EXISTS import_issues (
                row_number INTEGER, transaction_id TEXT, reason TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_sales_status_date ON sales(status, order_date);
        """)
        previous = conn.execute("SELECT value FROM metadata WHERE key='source_sha256'").fetchone()
        if previous and previous[0] == digest:
            return
        with csv_path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            if not REQUIRED.issubset(reader.fieldnames or []):
                raise ValueError("CSV is missing required columns.")
            conn.execute("DELETE FROM sales")
            conn.execute("DELETE FROM import_issues")
            seen = set()
            total = 0
            for row_number, raw in enumerate(reader, start=2):
                total += 1
                row = {k: (v or "").strip() for k, v in raw.items() if k}
                try:
                    transaction_id = row["Transaction_Id"]
                    if not transaction_id or transaction_id in seen:
                        raise ValueError("Missing or duplicate transaction ID.")
                    date = datetime.strptime(row["Order_date"], "%d-%m-%Y").date().isoformat()
                    quantity = int(row["Quantity"])
                    if quantity <= 0:
                        raise ValueError("Quantity must be a positive integer.")
                    if not row["Unit_price"]:
                        raise ValueError("Unit price is missing; revenue cannot be calculated.")
                    price = money(row["Unit_price"])
                    discount = money(row["Discount_amount"])
                    if discount > quantity * price:
                        raise ValueError("Discount exceeds gross line value.")
                    for key, allowed in [
                        ("Product", PRODUCTS),
                        ("Category", CATEGORIES),
                        ("Region", REGIONS),
                        ("Sales_channel", CHANNELS),
                        ("Status", ["Completed", "Returned", "Cancelled"]),
                    ]:
                        if row[key] not in allowed:
                            raise ValueError(f"Invalid {key}.")
                    conn.execute(
                        "INSERT INTO sales VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            transaction_id,
                            date,
                            row["Product"],
                            row["Category"],
                            row["Region"],
                            row["Sales_channel"],
                            quantity,
                            price,
                            discount,
                            row["Status"],
                            quantity * price - discount,
                        ),
                    )
                    seen.add(transaction_id)
                except (ValueError, InvalidOperation, sqlite3.IntegrityError, OverflowError) as exc:
                    conn.execute(
                        "INSERT INTO import_issues VALUES (?,?,?)",
                        (row_number, row.get("Transaction_Id", ""), str(exc)),
                    )
        conn.executemany(
            "INSERT OR REPLACE INTO metadata VALUES (?,?)",
            [("source_sha256", digest), ("source_rows", str(total)), ("source_file", csv_path.name)],
        )


@contextmanager
def readonly(db_path: Path):
    conn = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")

    def authorize(action, arg1, arg2, database, source):
        return (
            sqlite3.SQLITE_OK
            if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION)
            else sqlite3.SQLITE_DENY
        )

    conn.set_authorizer(authorize)
    try:
        yield conn
    finally:
        conn.close()


def quality(db_path: Path) -> dict:
    with readonly(db_path) as conn:
        meta = dict(conn.execute("SELECT key, value FROM metadata").fetchall())
        accepted = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
        eligible = conn.execute("SELECT COUNT(*) FROM sales WHERE status='Completed'").fetchone()[0]
        issues = [dict(row) for row in conn.execute("SELECT * FROM import_issues ORDER BY row_number")]
        span = conn.execute(
            "SELECT MIN(order_date), MAX(order_date) FROM sales WHERE status='Completed'"
        ).fetchone()
    return {
        "source_rows": int(meta["source_rows"]),
        "accepted_rows": accepted,
        "eligible_rows": eligible,
        "excluded_status_rows": accepted - eligible,
        "quarantined_rows": len(issues),
        "issues": issues,
        "source_file": meta["source_file"],
        "source_sha256": meta["source_sha256"],
        "date_start": span[0],
        "date_end": span[1],
    }

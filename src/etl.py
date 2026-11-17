"""
ETL: load data/claims_raw.csv into SQLite claims.db.

- Creates tables/views from sql/schema.sql + sql/views.sql if missing.
- Cleans / validates each row; invalid rows go to the dq_log
  (data-quality log) table with a reason and are NOT loaded.
- Idempotent: claim_id is the primary key, loads use INSERT OR IGNORE,
  so a re-run inserts 0 new rows and never creates duplicates.

Validation rules:
  * claim_id present, payer in the known payer list
  * status in {Paid, Denied, Pending}
  * billed_amount > 0, paid_amount >= 0, paid_amount <= billed_amount
  * Denied claims must have a denial_reason other than "None";
    Paid/Pending claims must have denial_reason "None"
  * service_date is a valid YYYY-MM-DD date in 2025-2026
  * days_in_ar >= 0

Run:  python3 src/etl.py [--csv data/claims_raw.csv] [--db claims.db]
"""
import argparse
import csv
import sqlite3
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
VALID_PAYERS = {"Medicare", "Medicaid", "Aetna", "Cigna", "UnitedHealthcare", "BCBS"}
VALID_STATUS = {"Paid", "Denied", "Pending"}


def validate(row: dict) -> str | None:
    """Return a rejection reason, or None if the row is valid."""
    if not row.get("claim_id"):
        return "missing claim_id"
    if row.get("payer") not in VALID_PAYERS:
        return f"unknown payer: {row.get('payer')}"
    if row.get("status") not in VALID_STATUS:
        return f"unknown status: {row.get('status')}"
    try:
        billed = float(row["billed_amount"])
        paid = float(row["paid_amount"])
    except (TypeError, ValueError):
        return "non-numeric amount"
    if billed <= 0:
        return "billed_amount <= 0"
    if paid < 0:
        return "paid_amount < 0"
    if paid > billed:
        return "paid_amount > billed_amount"
    try:
        d = datetime.strptime(row["service_date"], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return "invalid service_date"
    if not (2025 <= d.year <= 2026):
        return "service_date outside 2025-2026"
    try:
        days = int(row["days_in_ar"])
    except (TypeError, ValueError):
        return "non-integer days_in_ar"
    if days < 0:
        return "days_in_ar < 0"
    reason = (row.get("denial_reason") or "").strip()
    if row["status"] == "Denied" and reason in ("", "None"):
        return "Denied claim with no denial_reason"
    if row["status"] != "Denied" and reason != "None":
        return "non-Denied claim with a denial_reason"
    return None


def run_sql_file(conn: sqlite3.Connection, path: Path) -> None:
    conn.executescript(path.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser(description="Load synthetic claims CSV into SQLite.")
    ap.add_argument("--csv", default=str(BASE / "data" / "claims_raw.csv"))
    ap.add_argument("--db", default=str(BASE / "claims.db"))
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    try:
        run_sql_file(conn, BASE / "sql" / "schema.sql")
        run_sql_file(conn, BASE / "sql" / "views.sql")

        with open(args.csv, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        inserted = skipped_dup = rejected = 0
        for row in rows:
            reason = validate(row)
            if reason:
                conn.execute(
                    "INSERT INTO dq_log (claim_id, reason, raw_row) VALUES (?, ?, ?)",
                    (row.get("claim_id"), reason, str(row)),
                )
                rejected += 1
                continue
            cur = conn.execute(
                """INSERT OR IGNORE INTO claims
                   (claim_id, patient_id, payer, cpt_code, icd10_code, service_date,
                    billed_amount, paid_amount, status, denial_reason, days_in_ar)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (row["claim_id"], row["patient_id"], row["payer"], row["cpt_code"],
                 row["icd10_code"], row["service_date"], float(row["billed_amount"]),
                 float(row["paid_amount"]), row["status"], row["denial_reason"],
                 int(row["days_in_ar"])),
            )
            if cur.rowcount == 1:
                inserted += 1
            else:
                skipped_dup += 1
        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
        dq_total = conn.execute("SELECT COUNT(*) FROM dq_log").fetchone()[0]
        print(f"CSV rows read : {len(rows)}")
        print(f"Inserted      : {inserted}")
        print(f"Duplicates    : {skipped_dup} (already in DB, ignored)")
        print(f"Rejected (DQ): {rejected}")
        print(f"Total in DB   : {total}")
        print(f"Total in dq_log: {dq_total}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

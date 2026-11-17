-- RCM Reporting Dashboard — SQLite schema
-- SYNTHETIC DATA ONLY. No real patients or claims.
-- Run via src/etl.py (which applies this file), or:
--   sqlite3 claims.db < sql/schema.sql

CREATE TABLE IF NOT EXISTS claims (
    claim_id      TEXT PRIMARY KEY,
    patient_id    TEXT NOT NULL,          -- fake ID only, e.g. P0001; no names / PHI
    payer         TEXT NOT NULL,          -- Medicare, Medicaid, Aetna, Cigna, UnitedHealthcare, BCBS
    cpt_code      TEXT NOT NULL,          -- e.g. 99213
    icd10_code    TEXT NOT NULL,          -- e.g. J18.9
    service_date  TEXT NOT NULL,          -- YYYY-MM-DD, 2025-2026
    billed_amount REAL NOT NULL CHECK (billed_amount > 0),
    paid_amount   REAL NOT NULL CHECK (paid_amount >= 0),
    status        TEXT NOT NULL CHECK (status IN ('Paid', 'Denied', 'Pending')),
    denial_reason TEXT NOT NULL,          -- 'None' unless status = 'Denied'
    days_in_ar    INTEGER NOT NULL CHECK (days_in_ar >= 0),
    loaded_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_claims_payer        ON claims (payer);
CREATE INDEX IF NOT EXISTS idx_claims_status       ON claims (status);
CREATE INDEX IF NOT EXISTS idx_claims_service_date ON claims (service_date);

-- Data-quality log: every row rejected by the ETL, with the reason.
CREATE TABLE IF NOT EXISTS dq_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id   TEXT,
    reason     TEXT NOT NULL,
    raw_row    TEXT,
    logged_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- RCM Reporting Dashboard — PostgreSQL DDL
-- SAME tables/views as sql/schema.sql + sql/views.sql, ported to PostgreSQL.
--
-- *** NOT TESTED against a live PostgreSQL server in this project ***
-- No PostgreSQL server / psql was available in the build environment
-- (checked: `which psql postgres` returned nothing), so this file is
-- provided as a portability DDL only. Do not claim it was run/tested
-- until it has been applied to a real PostgreSQL instance.
-- To test it:  psql -d <db> -f sql/schema_postgres.sql

CREATE TABLE IF NOT EXISTS claims (
    claim_id      TEXT PRIMARY KEY,
    patient_id    TEXT NOT NULL,
    payer         TEXT NOT NULL,
    cpt_code      TEXT NOT NULL,
    icd10_code    TEXT NOT NULL,
    service_date  DATE NOT NULL,
    billed_amount NUMERIC(12, 2) NOT NULL CHECK (billed_amount > 0),
    paid_amount   NUMERIC(12, 2) NOT NULL CHECK (paid_amount >= 0),
    status        TEXT NOT NULL CHECK (status IN ('Paid', 'Denied', 'Pending')),
    denial_reason TEXT NOT NULL,
    days_in_ar    INTEGER NOT NULL CHECK (days_in_ar >= 0),
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_claims_payer        ON claims (payer);
CREATE INDEX IF NOT EXISTS idx_claims_status       ON claims (status);
CREATE INDEX IF NOT EXISTS idx_claims_service_date ON claims (service_date);

CREATE TABLE IF NOT EXISTS dq_log (
    id         SERIAL PRIMARY KEY,
    claim_id   TEXT,
    reason     TEXT NOT NULL,
    raw_row    TEXT,
    logged_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Views (same logic as sql/views.sql; PostgreSQL syntax)
CREATE OR REPLACE VIEW vw_ar_aging AS
SELECT
    CASE
        WHEN days_in_ar BETWEEN 0 AND 30 THEN '0-30'
        WHEN days_in_ar BETWEEN 31 AND 60 THEN '31-60'
        WHEN days_in_ar BETWEEN 61 AND 90 THEN '61-90'
        ELSE '90+'
    END AS ar_bucket,
    COUNT(*) AS claim_count,
    ROUND(SUM(billed_amount - paid_amount)::numeric, 2) AS ar_balance
FROM claims
WHERE status IN ('Denied', 'Pending')
GROUP BY ar_bucket;

CREATE OR REPLACE VIEW vw_denial_rate AS
SELECT
    payer,
    COUNT(*) AS total_claims,
    SUM(CASE WHEN status = 'Denied' THEN 1 ELSE 0 END) AS denied_claims,
    ROUND(100.0 * SUM(CASE WHEN status = 'Denied' THEN 1 ELSE 0 END)
          / NULLIF(COUNT(*), 0), 2) AS denial_rate_pct
FROM claims
GROUP BY payer;

CREATE OR REPLACE VIEW vw_denial_by_reason AS
SELECT
    denial_reason,
    COUNT(*) AS denied_claims,
    ROUND(100.0 * COUNT(*) / NULLIF(
        (SELECT COUNT(*) FROM claims WHERE status = 'Denied'), 0), 2) AS pct_of_denials
FROM claims
WHERE status = 'Denied'
GROUP BY denial_reason;

CREATE OR REPLACE VIEW vw_payment_summary AS
SELECT
    COUNT(*) AS total_claims,
    ROUND(SUM(billed_amount)::numeric, 2) AS total_billed,
    ROUND(SUM(paid_amount)::numeric, 2) AS total_paid,
    ROUND(SUM(CASE WHEN status IN ('Denied', 'Pending')
              THEN billed_amount - paid_amount ELSE 0 END)::numeric, 2) AS total_outstanding,
    ROUND(100.0 * SUM(paid_amount) / NULLIF(SUM(billed_amount), 0), 2) AS collection_rate_pct,
    ROUND(100.0 * SUM(CASE WHEN status = 'Denied' THEN 1 ELSE 0 END)
          / NULLIF(COUNT(*), 0), 2) AS denial_rate_pct
FROM claims;

CREATE OR REPLACE VIEW vw_revenue_by_month AS
SELECT
    to_char(service_date, 'YYYY-MM') AS service_month,
    COUNT(*) AS claim_count,
    ROUND(SUM(billed_amount)::numeric, 2) AS total_billed,
    ROUND(SUM(paid_amount)::numeric, 2) AS total_paid,
    ROUND(100.0 * SUM(paid_amount) / NULLIF(SUM(billed_amount), 0), 2) AS collection_rate_pct
FROM claims
GROUP BY service_month
ORDER BY service_month;

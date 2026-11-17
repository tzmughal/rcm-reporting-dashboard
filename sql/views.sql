-- RCM Reporting Dashboard — SQLite views
-- Applied by src/etl.py after sql/schema.sql, or:
--   sqlite3 claims.db < sql/views.sql
--
-- Definition used throughout: AR (accounts receivable) = billed - paid
-- for claims that are NOT yet paid, i.e. status IN ('Denied', 'Pending').
-- Paid claims have $0 outstanding, so they are excluded from AR views;
-- that is what makes the AR bucket totals sum exactly to total AR.

-- AR aging: outstanding balance by days-in-AR bucket
DROP VIEW IF EXISTS vw_ar_aging;
CREATE VIEW vw_ar_aging AS
SELECT
    CASE
        WHEN days_in_ar BETWEEN 0 AND 30 THEN '0-30'
        WHEN days_in_ar BETWEEN 31 AND 60 THEN '31-60'
        WHEN days_in_ar BETWEEN 61 AND 90 THEN '61-90'
        ELSE '90+'
    END AS ar_bucket,
    COUNT(*) AS claim_count,
    ROUND(SUM(billed_amount - paid_amount), 2) AS ar_balance
FROM claims
WHERE status IN ('Denied', 'Pending')
GROUP BY ar_bucket;

-- Denial rate by payer
DROP VIEW IF EXISTS vw_denial_rate;
CREATE VIEW vw_denial_rate AS
SELECT
    payer,
    COUNT(*) AS total_claims,
    SUM(CASE WHEN status = 'Denied' THEN 1 ELSE 0 END) AS denied_claims,
    ROUND(100.0 * SUM(CASE WHEN status = 'Denied' THEN 1 ELSE 0 END)
          / COUNT(*), 2) AS denial_rate_pct
FROM claims
GROUP BY payer;

-- Denials broken down by reason (denied claims only)
DROP VIEW IF EXISTS vw_denial_by_reason;
CREATE VIEW vw_denial_by_reason AS
SELECT
    denial_reason,
    COUNT(*) AS denied_claims,
    ROUND(100.0 * COUNT(*)
          / (SELECT COUNT(*) FROM claims WHERE status = 'Denied'), 2) AS pct_of_denials
FROM claims
WHERE status = 'Denied'
GROUP BY denial_reason;

-- Overall billed vs paid / collection & denial rates
-- NOTE: total_outstanding counts ONLY Denied + Pending claims (the AR),
-- so it equals the sum of vw_ar_aging and the AR Balance measure.
-- The uncollected slice of Paid claims (billed minus paid on paid claims)
-- is NOT in AR; it is the payer write-off / contractual gap, not money owed.
DROP VIEW IF EXISTS vw_payment_summary;
CREATE VIEW vw_payment_summary AS
SELECT
    COUNT(*) AS total_claims,
    ROUND(SUM(billed_amount), 2) AS total_billed,
    ROUND(SUM(paid_amount), 2) AS total_paid,
    ROUND(SUM(CASE WHEN status IN ('Denied', 'Pending')
              THEN billed_amount - paid_amount ELSE 0 END), 2) AS total_outstanding,
    ROUND(100.0 * SUM(paid_amount) / SUM(billed_amount), 2) AS collection_rate_pct,
    ROUND(100.0 * SUM(CASE WHEN status = 'Denied' THEN 1 ELSE 0 END)
          / COUNT(*), 2) AS denial_rate_pct
FROM claims;

-- Monthly billed vs paid trend
DROP VIEW IF EXISTS vw_revenue_by_month;
CREATE VIEW vw_revenue_by_month AS
SELECT
    substr(service_date, 1, 7) AS service_month,
    COUNT(*) AS claim_count,
    ROUND(SUM(billed_amount), 2) AS total_billed,
    ROUND(SUM(paid_amount), 2) AS total_paid,
    ROUND(100.0 * SUM(paid_amount) / SUM(billed_amount), 2) AS collection_rate_pct
FROM claims
GROUP BY service_month
ORDER BY service_month;

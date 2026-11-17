# Power BI Dashboard Spec — RCM Reporting Dashboard

> All data is **synthetic** (800 invented claims, seed 42). No real patients,
> claims, or payer data. A "Synthetic data — portfolio project" note appears
> on every page.

Source: `claims` table (`claims.db`, or `data/claims_raw.csv` imported
directly). Measures: see `dax_measures.md`.

## Global

- **Filters (all pages):** Slicer — Payer (multi-select); Slicer — Service
  Date (date range, Jan 2025 – Oct 2026); Slicer — Status.
- **Theme:** light background, dark-blue headers, one accent colour per
  status (Paid = green, Denied = red, Pending = amber).
- **KPI cards** use the DAX measures in `dax_measures.md`, formatted as
  in that file.

## Page 1 — Overview

Purpose: one-glance answer to "how much did we bill, collect, and lose?"

| Visual | Content |
|---|---|
| KPI cards (row of 6) | Total Claims, Total Billed, Total Paid, Collection Rate, Denial Rate, AR Balance |
| Line chart | Monthly revenue — Total Billed vs Total Paid by service_month (`vw_revenue_by_month`) |
| Donut chart | Claims by status (Paid / Denied / Pending) — count and % |
| Table | Top payers by Total Billed, Total Paid, Collection Rate |

## Page 2 — AR Aging

Purpose: where the unpaid money sits, and how old it is.

| Visual | Content |
|---|---|
| KPI cards | AR Balance, AR 90+, AR 90+ % of AR, Avg Days in AR |
| Clustered bar chart | AR Balance by AR Bucket (0-30, 31-60, 61-90, 90+) — from `vw_ar_aging` |
| Stacked bar chart | Claim count by AR Bucket, stacked by Status (Denied / Pending) |
| Table | AR by payer: AR Balance, claim count, AR 90+ — sorted by AR Balance desc |

Key check: the four bucket balances must sum exactly to AR Balance
(they do by construction — see `sql/views.sql`).

## Page 3 — Denials

Purpose: why claims are denied, and which payers deny most.

| Visual | Content |
|---|---|
| KPI cards | Denial Rate, Denied Claims, top denial reason (count) |
| Bar chart | Denial Rate by payer (`vw_denial_rate`), sorted desc |
| Bar chart | Denied claims by denial reason (`vw_denial_by_reason`) |
| Table | Denied claims detail: claim_id, payer, CPT, ICD-10, service_date, billed_amount, denial_reason, days_in_ar |

## Page 4 — Payer Performance (optional / stretch)

| Visual | Content |
|---|---|
| Matrix | Payer × Status: claim count, Total Billed, Total Paid |
| Bar chart | Collection Rate by payer |
| Table | All payers ranked by Denial Rate |

## Refresh

Re-run `python3 src/generate_claims.py` then `python3 src/etl.py` to
regenerate the data, then **Refresh** in Power BI. The ETL is idempotent,
so re-running it against the same CSV adds no duplicates.

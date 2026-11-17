# Power BI — DAX Measures (RCM Reporting Dashboard)

Data model: one fact table `claims` (from `claims.db` / `data/claims_raw.csv`),
loaded into Power BI via the SQLite ODBC driver or by importing the CSV.
No calculated columns are needed for the measures below; the AR bucket is
a calculated column (see bottom).

> All data is **synthetic** — no real patients, claims, or payer data.

## Core measures

```dax
Total Billed =
SUM ( claims[billed_amount] )

Total Paid =
SUM ( claims[paid_amount] )

-- Total Outstanding is the AR: only Denied + Pending claims.
-- (Billed − Paid over ALL claims would also include the uncollected
-- slice of Paid claims, which is not money owed, so it is NOT used here.)
Total Outstanding =
CALCULATE (
    SUMX ( claims, claims[billed_amount] - claims[paid_amount] ),
    claims[status] IN { "Denied", "Pending" }
)

Collection Rate =
DIVIDE ( [Total Paid], [Total Billed] )

Denial Rate =
DIVIDE (
    CALCULATE ( COUNTROWS ( claims ), claims[status] = "Denied" ),
    COUNTROWS ( claims )
)

Denied Claims =
CALCULATE ( COUNTROWS ( claims ), claims[status] = "Denied" )

Total Claims =
COUNTROWS ( claims )
```

## AR measures

AR = billed − paid on claims not yet paid (status `Denied` or `Pending`).
Paid claims have $0 outstanding and are excluded, so the AR buckets sum
exactly to AR Balance.

```dax
AR Balance =
CALCULATE (
    SUMX ( claims, claims[billed_amount] - claims[paid_amount] ),
    claims[status] IN { "Denied", "Pending" }
)

AR 90+ =
CALCULATE (
    [AR Balance],
    claims[days_in_ar] > 90
)

AR 90+ % of AR =
DIVIDE ( [AR 90+], [AR Balance] )

Avg Days in AR =
AVERAGE ( claims[days_in_ar] )
```

## Calculated column — AR bucket

```dax
AR Bucket =
SWITCH (
    TRUE (),
    claims[days_in_ar] <= 30, "0-30",
    claims[days_in_ar] <= 60, "31-60",
    claims[days_in_ar] <= 90, "61-90",
    "90+"
)
```

## Useful supporting measures

```dax
Avg Billed per Claim =
DIVIDE ( [Total Billed], [Total Claims] )

Paid Claims =
CALCULATE ( COUNTROWS ( claims ), claims[status] = "Paid" )

Pending Claims =
CALCULATE ( COUNTROWS ( claims ), claims[status] = "Pending" )

Denial Rate — Missing Documentation =
DIVIDE (
    CALCULATE (
        COUNTROWS ( claims ),
        claims[status] = "Denied",
        claims[denial_reason] = "Missing documentation"
    ),
    [Denied Claims]
)
```

## Formatting

| Measure | Format |
|---|---|
| Total Billed / Total Paid / AR Balance / AR 90+ | Currency, $#,##0 |
| Collection Rate / Denial Rate / AR 90+ % of AR | Percentage, 1 decimal |
| Total / Denied / Paid / Pending Claims | Whole number |
| Avg Days in AR | Decimal, 1 place |

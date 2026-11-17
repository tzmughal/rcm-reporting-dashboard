"""
Build excel/RCM_Reporting_Dashboard.xlsx from the SQLite DB.

Sheets:
  * Claims (Pivot-ready) — one row per claim, flat table with headers,
    formatted as an Excel Table so Insert > PivotTable works directly.
    Two helper columns are added (values, computed here from the claim):
    ar_bucket ("0-30"/"31-60"/"61-90"/"90+") and outstanding_amount
    (billed - paid for Denied/Pending claims, else 0). These are what the
    AR pivot is built on.
  * Summary — KPI tables from the SQL views (values snapshot) PLUS a
    "live formulas" block: COUNTA / SUM / SUMIF / COUNTIF / COUNTIFS /
    SUMIFS formulas that recalculate from the Claims sheet.
  * Pivot — Denial by Payer — a REAL native PivotTable (pivotTableDefinition
    + pivotCacheDefinition + pivotCacheRecords, built by src/pivot_utils.py)
    with rows = payer and Count of claim_id / Sum of billed / Sum of paid.
  * Pivot — AR Aging — a REAL native PivotTable sourced from the hidden
    helper sheet AR_Claims_src (outstanding claims only), rows = ar_bucket
    and Count of claim_id / Sum of outstanding_amount.
  * Lookup — claim lookup by ID using VLOOKUP and XLOOKUP formulas.
  * AR_Claims_src (hidden) — outstanding (Denied + Pending) claims only;
    the source range for the AR Aging pivot. Static extract: re-run this
    script to regenerate it after rebuilding the data.
  * README — synthetic-data notice + how to use the pivots and lookups.

Pivot note (honest): the native PivotTable definitions + caches are embedded
in the file and refreshOnLoad is set, so Excel renders the live pivot on
open. The pivot output cells are ALSO pre-filled with the true values
computed from the same source data (cross-checked against the SQL views),
because LibreOffice 24.2 in this sandbox does not render the pivot
definition on import — the pre-filled values make the sheets display
correctly in any viewer. See README.md for the full verification note.

Run:  python3 src/build_excel.py [--db claims.db] [--out excel/RCM_Reporting_Dashboard.xlsx]
"""
import argparse
import sqlite3
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.worksheet.table import Table, TableStyleInfo

from pivot_utils import build_pivot

BASE = Path(__file__).resolve().parent.parent
HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(color="FFFFFF", bold=True)
TITLE_FONT = Font(size=14, bold=True)
MONEY_FMT = '#,##0.00'
CLAIMS = "'Claims (Pivot-ready)'"


def ar_bucket(days: int) -> str:
    if days <= 30:
        return "0-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    return "90+"


def _write_df(ws, df, title, start_row=1):
    ws.cell(row=start_row, column=1, value=title).font = TITLE_FONT
    for r in dataframe_to_rows(df, index=False, header=True):
        ws.append(r)
    header_row = start_row + 2
    for cell in ws[header_row]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
    return header_row + len(df) + 2  # next free row


def _fit_to_page(ws):
    ws.page_setup.orientation = "landscape"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1


def _prefill_pivot(ws, table, first_header_row, money_cols):
    """Write the computed pivot result into the pivot output cells."""
    r = first_header_row
    for c, h in enumerate(table["headers"], start=1):
        cell = ws.cell(row=r, column=c, value=h)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
    for row in table["rows"]:
        r += 1
        for c, v in enumerate(row, start=1):
            cell = ws.cell(row=r, column=c, value=v)
            if c in money_cols:
                cell.number_format = MONEY_FMT
    r += 1
    for c, v in enumerate(table["grand"], start=1):
        cell = ws.cell(row=r, column=c, value=v)
        cell.font = Font(bold=True)
        if c in money_cols:
            cell.number_format = MONEY_FMT
    return r + 2  # next free row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(BASE / "claims.db"))
    ap.add_argument("--out", default=str(BASE / "excel" / "RCM_Reporting_Dashboard.xlsx"))
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    claims = pd.read_sql_query(
        "SELECT claim_id, patient_id, payer, cpt_code, icd10_code, service_date,"
        " billed_amount, paid_amount, status, denial_reason, days_in_ar"
        " FROM claims ORDER BY claim_id", conn)
    summary = pd.read_sql_query("SELECT * FROM vw_payment_summary", conn)
    ar = pd.read_sql_query(
        "SELECT * FROM vw_ar_aging ORDER BY "
        "CASE ar_bucket WHEN '0-30' THEN 1 WHEN '31-60' THEN 2 "
        "WHEN '61-90' THEN 3 ELSE 4 END", conn)
    denial_payer = pd.read_sql_query(
        "SELECT * FROM vw_denial_rate ORDER BY denial_rate_pct DESC", conn)
    denial_reason = pd.read_sql_query(
        "SELECT * FROM vw_denial_by_reason ORDER BY denied_claims DESC", conn)
    monthly = pd.read_sql_query("SELECT * FROM vw_revenue_by_month", conn)
    conn.close()

    # helper columns (values, computed from the claim row)
    claims["ar_bucket"] = claims["days_in_ar"].map(ar_bucket)
    claims["outstanding_amount"] = claims.apply(
        lambda r: round(r["billed_amount"] - r["paid_amount"], 2)
        if r["status"] in ("Denied", "Pending") else 0.0, axis=1)
    n = len(claims)
    ar_claims = claims[claims["status"].isin(["Denied", "Pending"])].copy()
    n_ar = len(ar_claims)

    wb = Workbook()

    # --- Claims (Pivot-ready) ---
    ws = wb.active
    ws.title = "Claims (Pivot-ready)"
    for r in dataframe_to_rows(claims, index=False, header=True):
        ws.append(r)
    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
    tab = Table(displayName="Claims", ref=f"A1:M{n + 1}")
    tab.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9", showFirstColumn=False, showRowStripes=True)
    ws.add_table(tab)
    ws.freeze_panes = "A2"
    for col, width in zip("ABCDEFGHIJKLM",
                          [12, 12, 18, 10, 10, 13, 14, 13, 10, 22, 11, 11, 18]):
        ws.column_dimensions[col].width = width

    # --- AR_Claims_src (hidden helper sheet: outstanding claims only) ---
    ws_src = wb.create_sheet("AR_Claims_src")
    for r in dataframe_to_rows(ar_claims, index=False, header=True):
        ws_src.append(r)
    for cell in ws_src[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
    ws_src.sheet_state = "hidden"

    # --- Summary ---
    ws = wb.create_sheet("Summary")
    ws["A1"] = "RCM Reporting Dashboard — Summary (SYNTHETIC DATA)"
    ws["A1"].font = TITLE_FONT
    row = 3
    row = _write_df(ws, summary.T.reset_index().rename(
        columns={"index": "metric", 0: "value"}), "Key KPIs (values from SQL views)", row)
    row = _write_df(ws, ar, "AR Aging (outstanding = Denied + Pending)", row)
    row = _write_df(ws, denial_payer, "Denial Rate by Payer", row)
    row = _write_df(ws, denial_reason, "Denials by Reason", row)
    row = _write_df(ws, monthly, "Monthly Revenue — Billed vs Paid", row)

    # live-formula KPI block (recalculates from the Claims sheet)
    ws.cell(row=row, column=1,
           value="Key KPIs — LIVE FORMULAS (recalculate from 'Claims (Pivot-ready)')").font = TITLE_FONT
    row += 2
    ws.cell(row=row, column=1, value="metric").fill = HEADER_FILL
    ws.cell(row=row, column=1).font = HEADER_FONT
    ws.cell(row=row, column=2, value="value (formula)").fill = HEADER_FILL
    ws.cell(row=row, column=2).font = HEADER_FONT
    formulas = [
        ("Total claims", f"=COUNTA({CLAIMS}!A2:A{n + 1})", "0"),
        ("Total billed", f"=SUM({CLAIMS}!G2:G{n + 1})", MONEY_FMT),
        ("Total paid", f"=SUM({CLAIMS}!H2:H{n + 1})", MONEY_FMT),
        ("AR balance", f"=SUM({CLAIMS}!M2:M{n + 1})", MONEY_FMT),
        ("Denied claims", f'=COUNTIF({CLAIMS}!I2:I{n + 1},"Denied")', "0"),
        ("Pending claims (COUNTIFS example)",
         f'=COUNTIFS({CLAIMS}!I2:I{n + 1},"Pending")', "0"),
        ("Total billed — Medicare (SUMIF example)",
         f'=SUMIF({CLAIMS}!C2:C{n + 1},"Medicare",{CLAIMS}!G2:G{n + 1})', MONEY_FMT),
        ("AR 90+ (SUMIFS example)",
         f'=SUMIFS({CLAIMS}!M2:M{n + 1},{CLAIMS}!L2:L{n + 1},"90+")', MONEY_FMT),
    ]
    first_formula_row = row + 1
    for i, (label, formula, fmt) in enumerate(formulas):
        r = first_formula_row + i
        ws.cell(row=r, column=1, value=label)
        c = ws.cell(row=r, column=2, value=formula)
        c.number_format = fmt
    r = first_formula_row + len(formulas)
    ws.cell(row=r, column=1, value="Collection rate")
    c = ws.cell(row=r, column=2,
               value=f"=B{first_formula_row + 2}/B{first_formula_row + 1}")
    c.number_format = "0.0%"
    r += 1
    ws.cell(row=r, column=1, value="Denial rate")
    c = ws.cell(row=r, column=2,
               value=f"=B{first_formula_row + 4}/B{first_formula_row}")
    c.number_format = "0.0%"
    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 20
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 18
    ws.column_dimensions["E"].width = 18
    _fit_to_page(ws)

    # --- Pivot — Denial by Payer (native PivotTable) ---
    ws = wb.create_sheet("Pivot — Denial by Payer")
    ws["A1"] = "PivotTable — Denial by Payer (SYNTHETIC DATA)"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = ("Native Excel PivotTable: rows = payer; values = Count of claim_id, "
                "Sum of billed_amount, Sum of paid_amount. Source: 'Claims (Pivot-ready)' "
                f"!$A$1:$M${n + 1}. Refresh: right-click the pivot > Refresh (or Data > "
                "Refresh All). Values below are pre-filled from the same source data.")
    _, table1 = build_pivot(
        wb["Claims (Pivot-ready)"], f"$A$1:$M${n + 1}", ws,
        name="PivotDenialByPayer", cache_id=1, row_field="payer",
        data_fields=[("claim_id", "count"), ("billed_amount", "sum"),
                     ("paid_amount", "sum")],
        location_ref="A3:D10", first_header_row=3)
    note_row = _prefill_pivot(ws, table1, 3, money_cols={3, 4})
    ws.cell(row=note_row, column=1, value="Note: this is a real PivotTable (pivotTableDefinition + "
           "pivotCacheDefinition + pivotCacheRecords are embedded in this file). "
           "The values shown are pre-filled from the source data so the sheet "
           "displays correctly in any viewer; Excel renders the live pivot on open.")
    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 20
    ws.column_dimensions["D"].width = 18
    _fit_to_page(ws)

    # --- Pivot — AR Aging (native PivotTable, outstanding claims only) ---
    ws = wb.create_sheet("Pivot — AR Aging")
    ws["A1"] = "PivotTable — AR Aging (SYNTHETIC DATA)"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = ("Native Excel PivotTable: rows = ar_bucket; values = Count of claim_id, "
                "Sum of outstanding_amount. Source: hidden sheet 'AR_Claims_src' "
                f"(outstanding Denied + Pending claims only), $A$1:$M${n_ar + 1}.")
    _, table2 = build_pivot(
        ws_src, f"$A$1:$M${n_ar + 1}", ws,
        name="PivotARAging", cache_id=2, row_field="ar_bucket",
        data_fields=[("claim_id", "count"), ("outstanding_amount", "sum")],
        location_ref="A3:C8", first_header_row=3)
    note_row = _prefill_pivot(ws, table2, 3, money_cols={3})
    ws.cell(row=note_row, column=1, value="Note: counts and AR balances here match the "
           "vw_ar_aging SQL view exactly (0-30 / 31-60 / 61-90 / 90+). See the "
           "Summary sheet and README.md for the verification numbers.")
    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 27
    _fit_to_page(ws)

    # --- Lookup (VLOOKUP + XLOOKUP) ---
    ws = wb.create_sheet("Lookup")
    ws["A1"] = "Claim Lookup — VLOOKUP and XLOOKUP (SYNTHETIC DATA)"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = "Claim ID:"
    ws["A2"].font = Font(bold=True)
    ws["B2"] = "CLM-0001"
    ws["B2"].font = Font(bold=True)
    ws["A3"] = ("VLOOKUP block — works in Excel and LibreOffice. "
                "Looks the claim up in 'Claims (Pivot-ready)'.")
    ws["A4"] = ("XLOOKUP block — needs Excel 2021 / Microsoft 365. LibreOffice 24.2 "
                "shows #NAME? for XLOOKUP (support added in LibreOffice 25.2); "
                "the formulas are still valid in Excel.")
    lookups = [
        ("Payer", 3, "C"), ("CPT code", 4, "D"), ("ICD-10", 5, "E"),
        ("Service date", 6, "F"), ("Billed amount", 7, "G"),
        ("Paid amount", 8, "H"), ("Status", 9, "I"),
        ("Denial reason", 10, "J"), ("Days in AR", 11, "K"),
        ("AR bucket", 12, "L"), ("Outstanding amount", 13, "M"),
    ]
    r0 = 6
    ws.cell(row=r0, column=1, value="Field").fill = HEADER_FILL
    ws.cell(row=r0, column=1).font = HEADER_FONT
    ws.cell(row=r0, column=2, value="VLOOKUP").fill = HEADER_FILL
    ws.cell(row=r0, column=2).font = HEADER_FONT
    ws.cell(row=r0, column=3, value="XLOOKUP").fill = HEADER_FILL
    ws.cell(row=r0, column=3).font = HEADER_FONT
    for i, (label, col_idx, col_letter) in enumerate(lookups):
        r = r0 + 1 + i
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value=(
            f"=VLOOKUP($B$2,{CLAIMS}!$A$2:$M${n + 1},{col_idx},FALSE)"))
        ws.cell(row=r, column=3, value=(
            f"=XLOOKUP($B$2,{CLAIMS}!$A$2:$A${n + 1},"
            f"{CLAIMS}!${col_letter}$2:${col_letter}${n + 1},\"Not found\")"))
        if label in ("Billed amount", "Paid amount", "Outstanding amount"):
            ws.cell(row=r, column=2).number_format = MONEY_FMT
            ws.cell(row=r, column=3).number_format = MONEY_FMT
    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 22
    _fit_to_page(ws)

    # --- README ---
    ws = wb.create_sheet("README")
    ws["A1"] = "SYNTHETIC DATA — all 800 claims are invented for a portfolio project."
    ws["A1"].font = Font(bold=True)
    notes = [
        "No real patients, claims, or payer data. Patient IDs are fake (P0001...).",
        "",
        "Sheets:",
        "- Claims (Pivot-ready): 800 claims as an Excel Table + helper columns",
        "  ar_bucket and outstanding_amount (values computed from each claim).",
        "- Summary: KPI tables from the SQL views + live formulas (SUM, SUMIF,",
        "  COUNTIF, COUNTIFS, SUMIFS) that recalculate from the Claims sheet.",
        "- Pivot — Denial by Payer / Pivot — AR Aging: real native PivotTables",
        "  (pivotTableDefinition + pivotCacheDefinition + pivotCacheRecords).",
        "  Refresh in Excel: right-click the pivot > Refresh. Values are also",
        "  pre-filled from the source data so the sheets display in any viewer.",
        "- Lookup: claim lookup by ID with VLOOKUP and XLOOKUP formulas.",
        "- AR_Claims_src (hidden): outstanding claims only, source for the AR pivot.",
        "",
        "How to build your own PivotTable from the data:",
        "1. Go to 'Claims (Pivot-ready)', click any cell inside the table.",
        "2. Insert > PivotTable, drag payer to Rows and billed_amount to Values.",
        "",
        "Source: claims.db (SQLite), built by src/etl.py from data/claims_raw.csv.",
    ]
    for i, line in enumerate(notes, start=2):
        ws.cell(row=i, column=1, value=line)
    ws.column_dimensions["A"].width = 95

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    wb.save(args.out)
    print(f"Wrote {args.out} ({n} claims, {len(wb.sheetnames)} sheets: "
          f"{', '.join(wb.sheetnames)})")


if __name__ == "__main__":
    main()

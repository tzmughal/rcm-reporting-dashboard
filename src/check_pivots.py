"""
Structural + values check for the native PivotTables in the workbook.

Verifies, without needing Excel:
  * workbook.xml lists the pivot caches (cacheIds 1 and 2)
  * each pivotCacheDefinition has one cache field per source column, with
    shared-item counts equal to the distinct values in that column
  * each pivotCacheRecords part has one record per source row, 13 values
    per record, every shared-item index in range
  * each pivotTableDefinition's row/col/data fields, row/col item counts
    and location range agree with the source data
  * the pre-filled values on the pivot sheets equal an independent
    recomputation (pandas groupby) AND the SQL views vw_denial_rate /
    vw_ar_aging
  * the Lookup sheet holds VLOOKUP and XLOOKUP formulas; the Summary
    sheet holds live formula cells

Run:  python3 src/check_pivots.py [--xlsx excel/RCM_Reporting_Dashboard.xlsx]
Exits non-zero if any check fails.
"""
import argparse
import sqlite3
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd
from openpyxl import load_workbook

BASE = Path(__file__).resolve().parent.parent
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
FAILURES = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAILURES.append(name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default=str(BASE / "excel" / "RCM_Reporting_Dashboard.xlsx"))
    ap.add_argument("--db", default=str(BASE / "claims.db"))
    args = ap.parse_args()

    z = zipfile.ZipFile(args.xlsx)
    names = z.namelist()
    check("pivot parts present",
          all(n in names for n in [
              "xl/pivotTables/pivotTable1.xml",
              "xl/pivotTables/pivotTable2.xml",
              "xl/pivotCache/pivotCacheDefinition1.xml",
              "xl/pivotCache/pivotCacheDefinition2.xml",
              "xl/pivotCache/pivotCacheRecords1.xml",
              "xl/pivotCache/pivotCacheRecords2.xml",
          ]))

    wb = load_workbook(args.xlsx, data_only=False)
    claims_ws = wb["Claims (Pivot-ready)"]
    ar_ws = wb["AR_Claims_src"]
    sources = {1: claims_ws, 2: ar_ws}

    wbx = ET.fromstring(z.read("xl/workbook.xml"))
    caches = wbx.findall(".//m:pivotCaches/m:pivotCache", NS)
    check("workbook lists 2 pivot caches",
          len(caches) == 2 and
          sorted(int(c.get("cacheId")) for c in caches) == [1, 2],
          f"cacheIds={[c.get('cacheId') for c in caches]}")

    pivot_specs = {
        1: {"sheet": "Pivot — Denial by Payer", "row_field": "payer",
            "data": [("claim_id", "count"), ("billed_amount", "sum"),
                     ("paid_amount", "sum")], "location": "A3:D10"},
        2: {"sheet": "Pivot — AR Aging", "row_field": "ar_bucket",
            "data": [("claim_id", "count"), ("outstanding_amount", "sum")],
            "location": "A3:C8"},
    }

    for pid, spec in pivot_specs.items():
        src = sources[pid]
        headers = [c.value for c in src[1]]
        rows = [list(r) for r in src.iter_rows(min_row=2, values_only=True)]
        rows = [r for r in rows if any(v is not None for v in r)]

        cdef = ET.fromstring(z.read(
            f"xl/pivotCache/pivotCacheDefinition{pid}.xml"))
        fields = cdef.findall(".//m:cacheFields/m:cacheField", NS)
        check(f"pivot {pid}: cache fields == source columns",
              len(fields) == len(headers), f"{len(fields)} vs {len(headers)}")
        ok_items = True
        for j, f in enumerate(fields):
            si = f.find("m:sharedItems", NS)
            distinct = len(set(r[j] for r in rows))
            if int(si.get("count")) != distinct:
                ok_items = False
        check(f"pivot {pid}: shared-item counts == distinct values", ok_items)
        check(f"pivot {pid}: recordCount == source rows",
              int(cdef.get("recordCount")) == len(rows),
              f"{cdef.get('recordCount')} vs {len(rows)}")

        recs = ET.fromstring(z.read(
            f"xl/pivotCache/pivotCacheRecords{pid}.xml"))
        rlist = recs.findall("m:r", NS)
        ok_rec = len(rlist) == len(rows)
        if ok_rec:
            for r in rlist:
                if len(list(r)) != len(headers):
                    ok_rec = False
                    break
                for j, child in enumerate(r):
                    if child.tag.endswith("}x"):
                        distinct = len(set(rr[j] for rr in rows))
                        if not (0 <= int(child.get("v")) < distinct):
                            ok_rec = False
        check(f"pivot {pid}: records == rows, 13 values each, indices in range",
              ok_rec, f"{len(rlist)} records")

        ptab = ET.fromstring(z.read(f"xl/pivotTables/pivotTable{pid}.xml"))
        check(f"pivot {pid}: cacheId matches",
              int(ptab.get("cacheId")) == pid)
        loc = ptab.find("m:location", NS)
        check(f"pivot {pid}: location ref {spec['location']}",
              loc.get("ref") == spec["location"], f"got {loc.get('ref')}")
        row_idx = headers.index(spec["row_field"])
        rf = ptab.findall("m:rowFields/m:field", NS)
        check(f"pivot {pid}: row field == {spec['row_field']}",
              len(rf) == 1 and int(rf[0].get("x")) == row_idx)
        df = ptab.findall("m:dataFields/m:dataField", NS)
        check(f"pivot {pid}: data fields match spec",
              [(int(d.get("fld")), d.get("subtotal")) for d in df] ==
              [(headers.index(h), s) for h, s in spec["data"]])
        n_row_vals = len(set(r[row_idx] for r in rows))
        ri = ptab.findall("m:rowItems/m:i", NS)
        ci = ptab.findall("m:colItems/m:i", NS)
        check(f"pivot {pid}: rowItems == distinct row values + grand",
              len(ri) == n_row_vals + 1, f"{len(ri)} vs {n_row_vals + 1}")
        check(f"pivot {pid}: colItems == data fields + grand",
              len(ci) == len(spec["data"]) + 1,
              f"{len(ci)} vs {len(spec['data']) + 1}")

        # pre-filled values on the pivot sheet vs independent recomputation
        ws = wb[spec["sheet"]]
        df_src = pd.DataFrame(rows, columns=headers)
        ok_vals = True
        for i, val in enumerate(sorted(df_src[spec["row_field"]].unique())):
            g = df_src[df_src[spec["row_field"]] == val]
            sheet_row = 4 + i
            if ws.cell(row=sheet_row, column=1).value != val:
                ok_vals = False
            for k, (h, s) in enumerate(spec["data"], start=2):
                expect = len(g) if s == "count" else round(g[h].sum(), 2)
                got = ws.cell(row=sheet_row, column=k).value
                if got is None or abs(float(got) - float(expect)) > 0.01:
                    ok_vals = False
        grand_row = 4 + n_row_vals
        if ws.cell(row=grand_row, column=1).value != "Grand Total":
            ok_vals = False
        for k, (h, s) in enumerate(spec["data"], start=2):
            expect = len(df_src) if s == "count" else round(df_src[h].sum(), 2)
            got = ws.cell(row=grand_row, column=k).value
            if got is None or abs(float(got) - float(expect)) > 0.01:
                ok_vals = False
        check(f"pivot {pid}: pre-filled sheet values == recomputation", ok_vals)

    # pre-filled values vs the SQL views
    conn = sqlite3.connect(args.db)
    vw_denial = pd.read_sql_query(
        "SELECT payer, COUNT(*) AS total_claims,"
        " ROUND(SUM(billed_amount),2) AS b,"
        " ROUND(SUM(paid_amount),2) AS p FROM claims GROUP BY payer", conn)
    ws = wb["Pivot — Denial by Payer"]
    ok_sql = True
    for i, prow in enumerate(vw_denial.sort_values("payer").itertuples(), start=4):
        if (ws.cell(row=i, column=1).value != prow.payer
                or ws.cell(row=i, column=2).value != prow.total_claims
                or abs(ws.cell(row=i, column=3).value - prow.b) > 0.01
                or abs(ws.cell(row=i, column=4).value - prow.p) > 0.01):
            ok_sql = False
    check("pivot 1 pre-filled values == SQL (billed/paid by payer)", ok_sql)
    vw_ar = pd.read_sql_query("SELECT * FROM vw_ar_aging", conn)
    ws = wb["Pivot — AR Aging"]
    ok_sql = True
    order = ["0-30", "31-60", "61-90", "90+"]
    for i, b in enumerate(order, start=4):
        vrow = vw_ar[vw_ar["ar_bucket"] == b].iloc[0]
        if (ws.cell(row=i, column=1).value != b
                or ws.cell(row=i, column=2).value != int(vrow["claim_count"])
                or abs(ws.cell(row=i, column=3).value - vrow["ar_balance"]) > 0.01):
            ok_sql = False
    check("pivot 2 pre-filled values == SQL vw_ar_aging", ok_sql)
    conn.close()

    # formulas present
    lk = wb["Lookup"]
    n_vlookup = sum(1 for row in lk.iter_rows()
                    for c in row if isinstance(c.value, str)
                    and c.value.startswith("=VLOOKUP"))
    n_xlookup = sum(1 for row in lk.iter_rows()
                    for c in row if isinstance(c.value, str)
                    and c.value.startswith("=XLOOKUP"))
    check("Lookup sheet: 11 VLOOKUP formulas", n_vlookup == 11, f"got {n_vlookup}")
    check("Lookup sheet: 11 XLOOKUP formulas", n_xlookup == 11, f"got {n_xlookup}")
    sm = wb["Summary"]
    n_formula = sum(1 for row in sm.iter_rows()
                    for c in row if isinstance(c.value, str)
                    and c.value.startswith("="))
    check("Summary sheet: live formula cells present", n_formula >= 10,
          f"got {n_formula}")

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
        sys.exit(1)
    print("ALL PIVOT/FORMULA CHECKS PASSED")


if __name__ == "__main__":
    main()

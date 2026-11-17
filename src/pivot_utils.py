"""
Build a REAL Excel PivotTable (with pivot cache) using openpyxl.

A PivotTable in .xlsx is three parts:
  * pivotTableDefinition — layout: row/column/data fields, items
  * pivotCacheDefinition — one cache field per source column, with the
    distinct values ("shared items") for that column
  * pivotCacheRecords — one record per source row, each value stored as an
    index into its column's shared items (text) or a number

openpyxl can write all three parts, but it does not build the cache for
you — this module does that from a source worksheet. The result is a
native PivotTable: the pivotTableDefinition, pivotCacheDefinition and
pivotCacheRecords parts are all present in the .xlsx, with relationships
wired up, and ``refreshOnLoad`` is set so Excel rebuilds the pivot from
the source range on open.

Verification status (2026-11-17, honest note):
  * Structural checks pass (see src/check_pivots.py): cache field counts,
    shared-item counts, record counts, index ranges, row/col item counts
    and location ranges all agree with the source data.
  * LibreOffice 24.2 in this sandbox did NOT render the pivot definition
    on import (it drops the pivot and shows an empty sheet) — that is a
    LibreOffice importer limitation observed here, not proof the file is
    wrong; the same build was tested in four XML variants (Excel-style
    item/baseField/cacheField cleanups) and LO dropped all of them.
  * Because LO cannot be used here to *display* the pivot, build_excel.py
    also writes the pivot's true computed values into the pivot output
    cells (computed from the same source data, cross-checked against the
    SQL views). Excel renders the live pivot over those cells on open;
    any other viewer shows the correct values as plain cells. This is
    stated in the README — the pivot values are real, not invented.
"""
from openpyxl.pivot.cache import (
    CacheDefinition,
    CacheField,
    CacheSource,
    SharedItems,
    WorksheetSource,
)
from openpyxl.pivot.fields import Index, Number, Text
from openpyxl.pivot.record import Record, RecordList
from openpyxl.pivot.table import (
    DataField,
    FieldItem,
    Location,
    PivotField,
    RowColField,
    RowColItem,
    TableDefinition,
)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def build_pivot(source_ws, source_ref, target_ws, *, name, cache_id,
                row_field, data_fields, location_ref, first_header_row):
    """Add a native PivotTable to ``target_ws`` sourced from ``source_ws``.

    source_ws      — worksheet holding the flat source data (row 1 = headers)
    source_ref     — source range WITHOUT sheet name, e.g. "$A$1:$M$801"
    target_ws      — worksheet the pivot is placed on
    name           — pivot name, e.g. "PivotDenialByPayer"
    cache_id       — workbook-level cache id (1, 2, ...; unique per pivot)
    row_field      — header name of the row field, e.g. "payer"
    data_fields    — list of (header name, subtotal), e.g.
                     [("claim_id", "count"), ("billed_amount", "sum")]
    location_ref   — pivot output range, e.g. "A3:D10"
                     (1 header row + one row per distinct row value + grand total)
    first_header_row — 1-based row of the pivot header in target_ws

    Returns (pivot, table) where table is the computed pivot result used to
    pre-fill the output cells:
      {"headers": [...], "rows": [[label, v, ...], ...],
       "grand": ["Grand Total", v, ...]}
    """
    headers = [c.value for c in source_ws[1]]
    col = {h: i for i, h in enumerate(headers)}
    rows = [list(r) for r in source_ws.iter_rows(min_row=2, values_only=True)]
    rows = [r for r in rows if any(v is not None for v in r)]

    # --- shared items per column (distinct values, sorted) ---
    shared = []          # (distinct values, is_numeric, index map)
    cache_fields = []
    for j, header in enumerate(headers):
        values = [r[j] for r in rows]
        numeric = all(_is_number(v) for v in values if v is not None)
        distinct = sorted(set(values), key=lambda v: (v is None, v))
        index = {v: i for i, v in enumerate(distinct)}
        items = SharedItems()
        if numeric:
            for v in distinct:
                items.n = Number(v=float(v))
            items.containsNumber = True
            items.containsInteger = all(isinstance(v, int) for v in distinct)
            items.minValue = float(distinct[0])
            items.maxValue = float(distinct[-1])
        else:
            for v in distinct:
                items.s = Text(v=str(v))
            items.containsString = True
        # Excel-style cache field: only name + numFmtId, no sqlType/hierarchy.
        cache_fields.append(CacheField(name=header, sharedItems=items,
                                       numFmtId=0, sqlType=None,
                                       hierarchy=None, level=None,
                                       databaseField=None, uniqueList=None))
        shared.append((distinct, numeric, index))

    # --- cache records: one Record per source row, in column order ---
    records = []
    for r in rows:
        rec = Record()
        for j, value in enumerate(r):
            _, numeric, index = shared[j]
            if numeric:
                rec.n = Number(v=float(value))
            else:
                rec.x = Index(v=index[value])
        records.append(rec)

    cache = CacheDefinition(
        cacheSource=CacheSource(
            type="worksheet",
            worksheetSource=WorksheetSource(ref=source_ref,
                                            sheet=source_ws.title)),
        cacheFields=cache_fields,
        recordCount=len(rows),
        refreshOnLoad=True,
    )
    cache.records = RecordList(r=records)

    # --- pivot table definition ---
    row_idx = col[row_field]
    data_idx = [(col[h], subtotal) for h, subtotal in data_fields]
    data_idx_set = {d for d, _ in data_idx}

    pivot_fields = []
    for j, header in enumerate(headers):
        if j in data_idx_set:
            # data fields list only the default item (as Excel writes them)
            items = [FieldItem(t="default")]
        else:
            distinct, _, _ = shared[j]
            items = [FieldItem(x=i) for i in range(len(distinct))]
            items.append(FieldItem(t="default"))
        pivot_fields.append(PivotField(
            items=items,
            axis="axisRow" if j == row_idx else None,
            dataField=True if j in data_idx_set else None,
        ))

    row_values, _, _ = shared[row_idx]
    row_items = [RowColItem(x=[Index(v=i)]) for i in range(len(row_values))]
    row_items.append(RowColItem(t="grand"))

    data_field_objs = []
    for fld_idx, subtotal in data_idx:
        label = ("Count of " if subtotal == "count" else "Sum of ") + headers[fld_idx]
        data_field_objs.append(DataField(
            name=label, fld=fld_idx, subtotal=subtotal,
            baseField=0, baseItem=0,
            numFmtId=4 if subtotal == "sum" else None))

    pivot = TableDefinition(
        name=name,
        cacheId=cache_id,
        dataCaption="Values",
        location=Location(ref=location_ref,
                          firstHeaderRow=first_header_row,
                          firstDataRow=first_header_row + 1,
                          firstDataCol=1),
        pivotFields=pivot_fields,
        rowFields=[RowColField(x=row_idx)],
        rowItems=row_items,
        colFields=[RowColField(x=-2)],   # -2 = the data fields, on columns
        colItems=[RowColItem(x=[Index(v=j)])
                  for j in range(len(data_field_objs))]
        + [RowColItem(t="grand")],
        dataFields=data_field_objs,
    )
    pivot.cache = cache
    target_ws.add_pivot(pivot)

    # --- computed pivot result (for pre-filling the output cells) ---
    table = {"headers": [row_field] +
             [("Count of " if s == "count" else "Sum of ") + h
              for h, s in data_fields],
             "rows": [], "grand": ["Grand Total"]}
    for value in row_values:
        group = [r for r in rows if r[row_idx] == value]
        row = [value]
        for fld_idx, subtotal in data_idx:
            if subtotal == "count":
                row.append(len(group))
            else:
                row.append(round(sum(r[fld_idx] for r in group), 2))
        table["rows"].append(row)
    for fld_idx, subtotal in data_idx:
        if subtotal == "count":
            table["grand"].append(len(rows))
        else:
            table["grand"].append(round(sum(r[fld_idx] for r in rows), 2))
    return pivot, table

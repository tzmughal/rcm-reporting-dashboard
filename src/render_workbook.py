"""
Render the actual Excel workbook's Summary and Pivot sheets as images.

Method (honest): LibreOffice 24.2 headless converts the real .xlsx to PDF,
then pdftotext identifies which PDF page holds each sheet and pdftoppm
renders those pages to PNG. What you see is the workbook as LibreOffice
renders it — including the pre-filled pivot values and the live-formula
cells as LibreOffice calculates them (XLOOKUP cells are NOT in these
screenshots; LibreOffice 24.2 shows #NAME? for XLOOKUP).

Outputs (screenshots/):
  excel_summary.png, excel_pivot_denial_by_payer.png, excel_pivot_ar_aging.png

Run:  python3 src/render_workbook.py [--xlsx excel/RCM_Reporting_Dashboard.xlsx]
Requires: soffice, pdftotext, pdftoppm, pdfinfo.
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

TARGETS = {
    "excel_summary.png": "RCM Reporting Dashboard — Summary",
    "excel_pivot_denial_by_payer.png": "PivotTable — Denial by Payer",
    "excel_pivot_ar_aging.png": "PivotTable — AR Aging",
}


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout, r.stderr, file=sys.stderr)
        raise SystemExit(f"command failed ({r.returncode}): {' '.join(cmd)}")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default=str(BASE / "excel" / "RCM_Reporting_Dashboard.xlsx"))
    ap.add_argument("--out", default=str(BASE / "screenshots"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    for tool in ("soffice", "pdftotext", "pdftoppm", "pdfinfo"):
        if not shutil.which(tool):
            raise SystemExit(f"missing required tool: {tool}")

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        run(["soffice", "--headless", "--calc", "--convert-to", "pdf",
             "--outdir", str(td), args.xlsx])
        pdf = next(td.glob("*.pdf"))
        n_pages = int(run(["pdfinfo", pdf]).stdout.split(
            "Pages:")[1].splitlines()[0].strip())
        print(f"workbook PDF: {n_pages} pages")
        page_of = {}
        for p in range(1, n_pages + 1):
            text = run(["pdftotext", "-f", str(p), "-l", str(p), "-layout",
                        str(pdf), "-"]).stdout
            for fname, marker in TARGETS.items():
                if marker in text and fname not in page_of:
                    page_of[fname] = p
        missing = [f for f in TARGETS if f not in page_of]
        if missing:
            raise SystemExit(f"could not find pages for: {missing} "
                             f"(found: {page_of})")
        for fname, p in page_of.items():
            prefix = td / Path(fname).stem
            run(["pdftoppm", "-png", "-r", "150", "-f", str(p), "-l", str(p),
                 str(pdf), str(prefix)])
            png = next(td.glob(f"{prefix.stem}-*.png"))
            shutil.copy(png, out / fname)
            print(f"page {p} -> screenshots/{fname}")


if __name__ == "__main__":
    main()

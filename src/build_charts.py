"""
Build matplotlib charts (PNG) in charts/ from the SQLite views.

  * ar_aging.png            — AR balance by bucket (0-30 / 31-60 / 61-90 / 90+)
  * denial_rate_by_payer.png — denial rate % by payer
  * denial_reason.png        — denied claims by reason
  * monthly_revenue.png      — monthly billed vs paid

Run:  python3 src/build_charts.py [--db claims.db] [--out charts]
"""
import argparse
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
plt.rcParams.update({"figure.dpi": 150, "axes.titlesize": 12})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(BASE / "claims.db"))
    ap.add_argument("--out", default=str(BASE / "charts"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(args.db)
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

    # 1. AR aging
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(ar["ar_bucket"], ar["ar_balance"], color="#1F4E79")
    ax.set_title("AR Balance by Aging Bucket (synthetic data)")
    ax.set_xlabel("Days in AR")
    ax.set_ylabel("AR balance ($)")
    for i, v in enumerate(ar["ar_balance"]):
        ax.text(i, v, f"${v:,.0f}", ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(out / "ar_aging.png")
    plt.close(fig)

    # 2. Denial rate by payer
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh(denial_payer["payer"], denial_payer["denial_rate_pct"], color="#C0392B")
    ax.set_title("Denial Rate by Payer (synthetic data)")
    ax.set_xlabel("Denial rate (%)")
    for i, v in enumerate(denial_payer["denial_rate_pct"]):
        ax.text(v, i, f" {v:.1f}%", va="center", fontsize=9)
    fig.tight_layout()
    fig.savefig(out / "denial_rate_by_payer.png")
    plt.close(fig)

    # 3. Denial reason
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh(denial_reason["denial_reason"], denial_reason["denied_claims"],
            color="#E67E22")
    ax.set_title("Denied Claims by Reason (synthetic data)")
    ax.set_xlabel("Denied claims")
    for i, v in enumerate(denial_reason["denied_claims"]):
        ax.text(v, i, f" {v}", va="center", fontsize=9)
    fig.tight_layout()
    fig.savefig(out / "denial_reason.png")
    plt.close(fig)

    # 4. Monthly revenue
    fig, ax = plt.subplots(figsize=(10, 4.5))
    x = range(len(monthly))
    ax.plot(x, monthly["total_billed"], marker="o", label="Billed")
    ax.plot(x, monthly["total_paid"], marker="o", label="Paid")
    ax.set_title("Monthly Revenue — Billed vs Paid (synthetic data)")
    ax.set_xlabel("Service month")
    ax.set_ylabel("$")
    ax.set_xticks(list(x))
    ax.set_xticklabels(monthly["service_month"], rotation=45, ha="right", fontsize=8)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "monthly_revenue.png")
    plt.close(fig)

    print(f"Wrote 4 charts to {out}/")


if __name__ == "__main__":
    main()

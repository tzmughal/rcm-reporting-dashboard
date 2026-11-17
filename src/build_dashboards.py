"""
Render Power BI-STYLE dashboard pages as images from the real synthetic data.

These are matplotlib renders laid out like the Power BI dashboard described
in powerbi/dashboard_spec.md — they are NOT screenshots of Power BI Desktop
and NO .pbix file was created (see README.md). They exist so the dashboard
design can be reviewed as images, and so the DAX measures + spec have a
visual companion built from the same numbers.

Pages:
  screenshots/powerbi_overview.png   — Page 1 (Overview): KPI cards, monthly
                                       billed vs paid, claims by status,
                                       denial rate by payer.
  screenshots/powerbi_ar_denials.png — Page 2 (AR Aging & Denials): AR KPI
                                       cards, AR aging, denials by reason,
                                       denial rate by payer.

All data is SYNTHETIC. Run:  python3 src/build_dashboards.py
"""
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyBboxPatch

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

NAVY = "#1F4E79"
BLUE = "#2E75B6"
LIGHT_BLUE = "#D9E2F3"
GREEN = "#107C10"
RED = "#D13438"
AMBER = "#FF8C00"
GREY = "#605E5C"
CARD_BG = "#F3F2F1"
MONEY = lambda v: f"${v:,.0f}"


def load():
    conn = sqlite3.connect(BASE / "claims.db")
    s = pd.read_sql_query("SELECT * FROM vw_payment_summary", conn).iloc[0]
    ar = pd.read_sql_query(
        "SELECT * FROM vw_ar_aging ORDER BY "
        "CASE ar_bucket WHEN '0-30' THEN 1 WHEN '31-60' THEN 2 "
        "WHEN '61-90' THEN 3 ELSE 4 END", conn)
    denial_payer = pd.read_sql_query(
        "SELECT * FROM vw_denial_rate ORDER BY denial_rate_pct DESC", conn)
    denial_reason = pd.read_sql_query(
        "SELECT * FROM vw_denial_by_reason ORDER BY denied_claims DESC", conn)
    monthly = pd.read_sql_query("SELECT * FROM vw_revenue_by_month", conn)
    status = pd.read_sql_query(
        "SELECT status, COUNT(*) AS n FROM claims GROUP BY status", conn)
    ar90 = pd.read_sql_query(
        "SELECT ROUND(SUM(billed_amount - paid_amount), 2) AS v, COUNT(*) AS n"
        " FROM claims WHERE status IN ('Denied','Pending') AND days_in_ar > 90",
        conn).iloc[0]
    avg_days = conn.execute(
        "SELECT ROUND(AVG(days_in_ar), 1) FROM claims"
        " WHERE status IN ('Denied','Pending')").fetchone()[0]
    conn.close()
    return s, ar, denial_payer, denial_reason, monthly, status, ar90, avg_days


def _page(title, subtitle):
    fig = plt.figure(figsize=(16, 9))
    fig.patch.set_facecolor("white")
    # title bar
    ax = fig.add_axes([0, 0.92, 1, 0.08])
    ax.axis("off")
    ax.add_patch(FancyBboxPatch((0.005, 0.1), 0.99, 0.85,
                                boxstyle="round,pad=0.02,rounding_size=0.02",
                                facecolor=NAVY, edgecolor="none",
                                transform=ax.transAxes))
    ax.text(0.02, 0.52, title, color="white", fontsize=20,
            fontweight="bold", va="center", transform=ax.transAxes)
    ax.text(0.98, 0.52, "SYNTHETIC DATA", color="#F2C811", fontsize=11,
            fontweight="bold", va="center", ha="right", transform=ax.transAxes)
    fig.text(0.02, 0.905, subtitle, fontsize=10, color=GREY)
    fig.text(0.98, 0.015,
             "Synthetic data only — portfolio project  •  "
             "Power BI-style render (matplotlib), not a Power BI screenshot — no .pbix",
             fontsize=8, color=GREY, ha="right")
    return fig


def _kpi_cards(fig, cards, y=0.80, height=0.10):
    n = len(cards)
    w = (0.96 - 0.01 * (n - 1)) / n
    for i, card in enumerate(cards):
        label, value, color = card[0], card[1], card[2]
        vsize = card[3] if len(card) > 3 else 17
        x = 0.02 + i * (w + 0.01)
        ax = fig.add_axes([x, y, w, height])
        ax.axis("off")
        ax.add_patch(FancyBboxPatch((0, 0), 1, 1,
                                    boxstyle="round,pad=0.01,rounding_size=0.02",
                                    facecolor=CARD_BG, edgecolor="#E1DFDD",
                                    transform=ax.transAxes))
        ax.plot([0.06, 0.06], [0.12, 0.88], color=color, lw=4,
                transform=ax.transAxes, solid_capstyle="round")
        ax.text(0.12, 0.68, label, fontsize=10, color=GREY,
                transform=ax.transAxes, va="center")
        ax.text(0.12, 0.32, value, fontsize=vsize, color="#323130",
                fontweight="bold", transform=ax.transAxes, va="center")


def _panel(fig, rect, title):
    ax = fig.add_axes(rect)
    ax.set_title(title, fontsize=12, fontweight="bold", color="#323130",
                 loc="left", pad=10)
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color("#E1DFDD")
    ax.spines["bottom"].set_color("#E1DFDD")
    ax.tick_params(colors=GREY, labelsize=9)
    return ax


def overview(s, ar, denial_payer, denial_reason, monthly, status, ar90, avg_days):
    fig = _page("RCM Reporting Dashboard — Overview",
                "Page 1 of 2  •  800 synthetic claims, Jan 2025 – Oct 2026  •  Measures: powerbi/dax_measures.md")
    _kpi_cards(fig, [
        ("Total Claims", f"{int(s['total_claims']):,}", NAVY),
        ("Total Billed", MONEY(s["total_billed"]), BLUE),
        ("Total Paid", MONEY(s["total_paid"]), GREEN),
        ("Collection Rate", f"{s['collection_rate_pct']:.1f}%", GREEN),
        ("Denial Rate", f"{s['denial_rate_pct']:.1f}%", RED),
        ("AR Balance", MONEY(s["total_outstanding"]), AMBER),
    ])
    ax = _panel(fig, [0.05, 0.42, 0.56, 0.32],
                "Monthly revenue — Billed vs Paid")
    ax.plot(monthly["service_month"], monthly["total_billed"],
            marker="o", ms=3, label="Billed", color=BLUE)
    ax.plot(monthly["service_month"], monthly["total_paid"],
            marker="o", ms=3, label="Paid", color=GREEN)
    ax.set_ylabel("$", fontsize=9)
    ax.tick_params(axis="x", labelrotation=45, labelsize=8)
    ax.legend(fontsize=9, frameon=False)

    ax = _panel(fig, [0.66, 0.42, 0.29, 0.32], "Claims by status")
    colors = {"Paid": GREEN, "Denied": RED, "Pending": AMBER}
    vals = [int(status.loc[status["status"] == st, "n"].iloc[0])
            for st in ["Paid", "Denied", "Pending"]]
    ax.pie(vals, colors=[colors[st] for st in ["Paid", "Denied", "Pending"]],
           autopct="%1.1f%%", pctdistance=0.8, textprops={"fontsize": 9},
           wedgeprops={"width": 0.45, "edgecolor": "white"})
    ax.legend(["Paid", "Denied", "Pending"], fontsize=9, frameon=False,
              loc="center left", bbox_to_anchor=(0.95, 0.5))

    ax = _panel(fig, [0.10, 0.06, 0.85, 0.28], "Denial rate by payer (%)")
    ax.barh(denial_payer["payer"][::-1], denial_payer["denial_rate_pct"][::-1],
            color=RED, height=0.6)
    for i, v in enumerate(denial_payer["denial_rate_pct"][::-1]):
        ax.text(v + 0.4, i, f"{v:.1f}%", va="center", fontsize=9)
    ax.set_xlim(0, max(denial_payer["denial_rate_pct"]) * 1.25)
    fig.savefig(OUT / "powerbi_overview.png", dpi=150)
    plt.close(fig)
    print("wrote screenshots/powerbi_overview.png")


def ar_denials(s, ar, denial_payer, denial_reason, monthly, status, ar90, avg_days):
    fig = _page("RCM Reporting Dashboard — AR Aging & Denials",
                "Page 2 of 2  •  AR = billed − paid on Denied + Pending claims only  •  "
                "Avg Days in AR is over outstanding claims only")
    ar90_pct = 100 * ar90["v"] / s["total_outstanding"]
    top_reason = denial_reason.iloc[0]
    _kpi_cards(fig, [
        ("AR Balance", MONEY(s["total_outstanding"]), AMBER),
        ("AR 90+", MONEY(ar90["v"]), RED),
        ("AR 90+ % of AR", f"{ar90_pct:.1f}%", RED),
        ("Avg Days in AR*", f"{avg_days:.1f}", NAVY),
        ("Top Denial Reason", "Missing\ndocumentation", NAVY, 13),
        ("Denials — Top Reason", f"{int(top_reason['denied_claims'])} claims", RED),
    ], y=0.80)

    ax = _panel(fig, [0.05, 0.42, 0.43, 0.32], "AR balance by aging bucket ($)")
    ax.bar(ar["ar_bucket"], ar["ar_balance"], color=NAVY, width=0.6)
    for i, v in enumerate(ar["ar_balance"]):
        ax.text(i, v, MONEY(v), ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("$", fontsize=9)

    ax = _panel(fig, [0.56, 0.42, 0.39, 0.32], "Denied claims by reason")
    ax.barh(denial_reason["denial_reason"][::-1],
            denial_reason["denied_claims"][::-1], color="#E67E22", height=0.6)
    for i, v in enumerate(denial_reason["denied_claims"][::-1]):
        ax.text(v + 0.7, i, f"{int(v)}", va="center", fontsize=9)
    ax.set_xlim(0, max(denial_reason["denied_claims"]) * 1.2)

    ax = _panel(fig, [0.05, 0.06, 0.90, 0.28], "Denial rate by payer (%)")
    ax.bar(denial_payer["payer"], denial_payer["denial_rate_pct"],
           color=RED, width=0.6)
    for i, v in enumerate(denial_payer["denial_rate_pct"]):
        ax.text(i, v + 0.5, f"{v:.1f}%", ha="center", fontsize=9)
    ax.set_ylim(0, max(denial_payer["denial_rate_pct"]) * 1.25)
    ax.set_ylabel("%", fontsize=9)
    fig.savefig(OUT / "powerbi_ar_denials.png", dpi=150)
    plt.close(fig)
    print("wrote screenshots/powerbi_ar_denials.png")


if __name__ == "__main__":
    data = load()
    overview(*data)
    ar_denials(*data)

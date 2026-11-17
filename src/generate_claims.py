"""
Generate 800 synthetic US medical billing claims.

SYNTHETIC DATA ONLY — no real patients, no real claims, no real payer data.
All values are invented for a portfolio / learning project. Patient IDs are
fake (P0001, P0002, ...); no names, dates of birth, or any PHI are included.

Seeded (RANDOM_SEED = 42) so every run produces the same file.
Run:  python3 src/generate_claims.py [--rows 800] [--out data/claims_raw.csv]
"""
import argparse
import csv
import random
from datetime import date, timedelta

RANDOM_SEED = 42

PAYERS = ["Medicare", "Medicaid", "Aetna", "Cigna", "UnitedHealthcare", "BCBS"]
PAYER_WEIGHTS = [0.22, 0.18, 0.15, 0.15, 0.16, 0.14]

CPT_CODES = ["99213", "99214", "99215", "93000", "71046", "80053", "85025", "90471"]
ICD10_CODES = ["J18.9", "I10", "E11.9", "M54.5", "J06.9", "R05", "K21.9", "N39.0"]

# status, then (denial reasons, weights) — denial_reason is "None" unless Denied
DENIAL_REASONS = [
    "Missing documentation",
    "Coding error",
    "Prior authorization",
    "Duplicate claim",
    "Eligibility",
]
DENIAL_WEIGHTS = [0.30, 0.25, 0.20, 0.10, 0.15]

FIELDNAMES = [
    "claim_id", "patient_id", "payer", "cpt_code", "icd10_code",
    "service_date", "billed_amount", "paid_amount", "status",
    "denial_reason", "days_in_ar",
]


def generate_claims(n: int = 800, seed: int = RANDOM_SEED):
    rng = random.Random(seed)
    start = date(2025, 1, 1)
    end = date(2026, 10, 31)
    span = (end - start).days
    rows = []
    for i in range(1, n + 1):
        payer = rng.choices(PAYERS, weights=PAYER_WEIGHTS, k=1)[0]
        status = rng.choices(
            ["Paid", "Denied", "Pending"], weights=[0.65, 0.18, 0.17], k=1
        )[0]
        billed = round(rng.uniform(150.0, 2500.0), 2)
        if status == "Paid":
            paid = round(billed * rng.uniform(0.70, 0.98), 2)
            days_in_ar = rng.randint(15, 45)
            denial_reason = "None"
        elif status == "Denied":
            paid = 0.0
            days_in_ar = rng.randint(60, 120)
            denial_reason = rng.choices(
                DENIAL_REASONS, weights=DENIAL_WEIGHTS, k=1
            )[0]
        else:  # Pending
            paid = 0.0
            days_in_ar = rng.randint(10, 90)
            denial_reason = "None"
        rows.append({
            "claim_id": f"CLM-{i:04d}",
            "patient_id": f"P{rng.randint(1, 500):04d}",
            "payer": payer,
            "cpt_code": rng.choice(CPT_CODES),
            "icd10_code": rng.choice(ICD10_CODES),
            "service_date": (start + timedelta(days=rng.randint(0, span))).isoformat(),
            "billed_amount": billed,
            "paid_amount": paid,
            "status": status,
            "denial_reason": denial_reason,
            "days_in_ar": days_in_ar,
        })
    return rows


def main():
    ap = argparse.ArgumentParser(description="Generate synthetic RCM claims (seeded).")
    ap.add_argument("--rows", type=int, default=800)
    ap.add_argument("--out", default="data/claims_raw.csv")
    ap.add_argument("--seed", type=int, default=RANDOM_SEED)
    args = ap.parse_args()

    rows = generate_claims(args.rows, args.seed)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} synthetic claims to {args.out} (seed={args.seed})")


if __name__ == "__main__":
    main()

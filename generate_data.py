"""
Component 1 — Synthetic risk dataset generator.

Produces a single, unified table of risk exposures across the three domains a
Divisional Data Office governs — Credit, Market, Liquidity — using realistic
**Critical Data Elements (CDEs)**: the fields that are material to risk decisions
and therefore the first targets of data-quality controls.

It then *deliberately injects* data-quality defects, each tagged to the BCBS 239
principle it violates, and records them in a ground-truth `issue_log.csv`. That log
lets us later measure how much of the injected population the rules engine actually
catches — i.e. our **DQ control coverage** (a real governance metric).

ALL DATA IS SYNTHETIC. No real firm data, no PII.

Run:  python generate_data.py
Out:  data/risk_exposures.csv   (the dataset)
      data/issue_log.csv        (ground-truth of injected defects)
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

import pandas as pd

import config

# Deterministic output — same dataset every run (239 = a nod to the standard).
SEED = 239
random.seed(SEED)

N_ROWS = 600                      # total exposures across all domains
INJECT_RATE = 0.18               # ~18% of rows get a defect (realistic-ish)

REPORTING_DATE = datetime.strptime(config.REPORTING_DATE, "%Y-%m-%d")

# Domain-specific reference data --------------------------------------------------
PRODUCTS = {
    "Credit":    ["Term Loan", "Revolving Credit", "Letter of Credit",
                  "Corporate Bond", "Counterparty Derivative"],
    "Market":    ["Equity Position", "FX Forward", "Interest Rate Swap",
                  "Commodity Future", "Government Bond"],
    "Liquidity": ["HQLA Level 1", "HQLA Level 2A", "Term Deposit",
                  "Repo", "Committed Facility"],
}
LEGAL_ENTITIES = ["NA Broker-Dealer", "EMEA Bank plc", "APAC Securities",
                  "India GCC Entity"]
SOURCE_BY_DOMAIN = {
    "Credit": "CreditMart",
    "Market": "MarketRiskHub",
    "Liquidity": "LiquidityEngine",
}


def _clean_row(i: int) -> dict:
    """Build one well-formed exposure record (a 'good' row before injection)."""
    domain = random.choice(config.RISK_DOMAINS)
    notional = round(random.uniform(1_000_000, 250_000_000), 2)
    # last_updated within the timeliness SLA (i.e. timely by default)
    fresh_days = random.randint(0, config.TIMELINESS_SLA_DAYS)
    last_updated = REPORTING_DATE - timedelta(days=fresh_days,
                                              hours=random.randint(0, 23))
    maturity = REPORTING_DATE + timedelta(days=random.randint(30, 3650))

    row = {
        "exposure_id": f"EXP-{i:05d}",
        "as_of_date": REPORTING_DATE.strftime("%Y-%m-%d"),
        "risk_domain": domain,
        "legal_entity": random.choice(LEGAL_ENTITIES),
        "counterparty_id": f"CP-{random.randint(1, 180):04d}",
        "counterparty_name": f"Counterparty {random.randint(1, 180):04d}",
        "product_type": random.choice(PRODUCTS[domain]),
        "currency": random.choice(config.VALID_CURRENCIES),
        "notional_amount": notional,
        "exposure_amount": round(notional * random.uniform(0.3, 1.0), 2),
        # Domain-specific CDEs (blank where not applicable to the domain)
        "probability_of_default": round(random.uniform(0.001, 0.25), 4)
                                  if domain == "Credit" else "",
        "loss_given_default": round(random.uniform(0.2, 0.9), 2)
                              if domain == "Credit" else "",
        "internal_rating": random.choice(config.VALID_RATINGS)
                           if domain == "Credit" else "",
        "market_value": round(notional * random.uniform(0.8, 1.2), 2)
                        if domain == "Market" else "",
        "var_1d": round(notional * random.uniform(0.005, 0.05), 2)
                  if domain == "Market" else "",
        "lcr_hqla_amount": round(notional * random.uniform(0.5, 1.0), 2)
                           if domain == "Liquidity" else "",
        "maturity_date": maturity.strftime("%Y-%m-%d"),
        "source_system": SOURCE_BY_DOMAIN[domain],
        "last_updated_ts": last_updated.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return row


# Each injector mutates a row in place and returns (field, issue_type, principle).
# The 'principle' tag is the BCBS 239 principle the defect violates.
def _inject_completeness(row: dict):
    field = random.choice(["counterparty_name", "currency", "exposure_amount"])
    row[field] = ""
    return field, "missing_mandatory_cde", "P4 Completeness"


def _inject_accuracy(row: dict):
    # Universal defects apply to any domain; PD/rating defects only make sense on
    # Credit rows (those CDEs aren't material — or even populated — elsewhere).
    # Keeping injected defects on *material* CDEs is what keeps the ground truth
    # honest, and mirrors a real lesson: controls are scoped per domain.
    choices = ["neg_notional", "bad_ccy"]
    if row["risk_domain"] == "Credit":
        choices += ["bad_pd", "bad_rating"]
    choice = random.choice(choices)
    if choice == "bad_pd":
        # PD is a probability; must be in [0, 1]. Force an impossible value.
        row["probability_of_default"] = round(random.uniform(1.5, 9.9), 4)
        return "probability_of_default", "pd_out_of_range", "P3 Accuracy"
    if choice == "neg_notional":
        row["notional_amount"] = -abs(row["notional_amount"])
        return "notional_amount", "negative_amount", "P3 Accuracy"
    if choice == "bad_rating":
        row["internal_rating"] = random.choice(["ZZ", "X1", "NR?", "999"])
        return "internal_rating", "invalid_rating_code", "P3 Accuracy"
    row["currency"] = random.choice(["US$", "RUPEE", "XXX", "12"])
    return "currency", "invalid_currency_code", "P3 Accuracy"


def _inject_timeliness(row: dict):
    # Push last_updated well past the SLA — the record is stale for aggregation.
    stale = REPORTING_DATE - timedelta(days=random.randint(5, 45))
    row["last_updated_ts"] = stale.strftime("%Y-%m-%d %H:%M:%S")
    return "last_updated_ts", "stale_beyond_sla", "P5 Timeliness"


def _inject_consistency(row: dict):
    # Maturity before the reporting date is logically impossible for a live trade.
    bad = REPORTING_DATE - timedelta(days=random.randint(10, 400))
    row["maturity_date"] = bad.strftime("%Y-%m-%d")
    return "maturity_date", "maturity_before_asof", "P3 Accuracy"


INJECTORS = [_inject_completeness, _inject_accuracy, _inject_timeliness,
             _inject_consistency]


def generate() -> tuple[pd.DataFrame, pd.DataFrame]:
    config.ensure_dirs()

    rows = [_clean_row(i) for i in range(1, N_ROWS + 1)]
    issue_log: list[dict] = []

    # 1) Inject single-field defects into a random subset of rows.
    n_inject = int(N_ROWS * INJECT_RATE)
    for row in random.sample(rows, n_inject):
        injector = random.choice(INJECTORS)
        field, issue_type, principle = injector(row)
        issue_log.append({
            "exposure_id": row["exposure_id"],
            "field": field,
            "issue_type": issue_type,
            "principle": principle,
        })

    # 2) Inject a handful of duplicate exposure_ids (uniqueness / integrity).
    for _ in range(6):
        victim = random.choice(rows)
        dup = dict(victim)  # same exposure_id on a second physical record
        rows.append(dup)
        issue_log.append({
            "exposure_id": dup["exposure_id"],
            "field": "exposure_id",
            "issue_type": "duplicate_id",
            "principle": "P3 Integrity",
        })

    df = pd.DataFrame(rows)
    issues = pd.DataFrame(issue_log)

    df.to_csv(config.EXPOSURES_CSV, index=False)
    issues.to_csv(config.ISSUE_LOG_CSV, index=False)
    return df, issues


def _summary(df: pd.DataFrame, issues: pd.DataFrame) -> None:
    print(f"\n  Synthetic risk dataset written to {config.EXPOSURES_CSV}")
    print(f"  Reporting (as-of) date : {config.REPORTING_DATE}")
    print(f"  Total exposure records : {len(df)}")
    print("\n  Records by risk domain:")
    for domain, n in df["risk_domain"].value_counts().sort_index().items():
        print(f"     {domain:<10} {n}")
    print(f"\n  Injected DQ defects (ground truth) : {len(issues)}")
    print("  By BCBS 239 principle:")
    for principle, n in issues["principle"].value_counts().items():
        print(f"     {principle:<18} {n}")
    print("\n  Next: run  python dq_rules.py  to see how many the engine catches.\n")


if __name__ == "__main__":
    df, issues = generate()
    _summary(df, issues)

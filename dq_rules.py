"""
Component 2 — BCBS 239 data-quality rules engine.

This is the heart of the demo. Each block of rules implements one of the **Group II
risk-data-aggregation principles**:

    Principle 3 — Accuracy & Integrity   -> validity + uniqueness checks
    Principle 4 — Completeness           -> mandatory-CDE-present checks
    Principle 5 — Timeliness             -> freshness-vs-SLA check
    Principle 6 — Adaptability           -> ad-hoc re-aggregation on demand

The engine reads the synthetic dataset, runs every rule on every record, and emits a
long-format "findings" table (one row per failed check) plus a **DQ scorecard** —
pass rates by principle and by risk domain. That scorecard is the "evidence of
compliance" a Divisional Data Office takes to the DQGC and to supervisors.

Run:  python dq_rules.py
Out:  data/dq_results.csv   (one row per DQ finding)
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

import config

REPORTING_DATE = datetime.strptime(config.REPORTING_DATE, "%Y-%m-%d")

# Mandatory CDEs that every risk record must carry (Principle 4 — Completeness).
MANDATORY_CDES = [
    "exposure_id", "as_of_date", "risk_domain", "legal_entity",
    "counterparty_id", "counterparty_name", "product_type", "currency",
    "notional_amount", "exposure_amount", "source_system",
    "last_updated_ts", "maturity_date",
]
# Additional CDEs required only for specific domains.
DOMAIN_MANDATORY = {
    "Credit":    ["probability_of_default", "loss_given_default", "internal_rating"],
    "Market":    ["market_value", "var_1d"],
    "Liquidity": ["lcr_hqla_amount"],
}


def _is_blank(v) -> bool:
    return v is None or str(v).strip() == ""


def _num(v):
    """Parse a numeric CDE; return None if not a valid number."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _finding(row, principle, rule, field, detail) -> dict:
    return {
        "exposure_id": row["exposure_id"],
        "risk_domain": row["risk_domain"],
        "principle": principle,
        "rule": rule,
        "field": field,
        "observed": row.get(field, ""),
        "detail": detail,
    }


# ── Principle 4 — Completeness ───────────────────────────────────────────────
def check_completeness(row) -> list[dict]:
    findings = []
    required = MANDATORY_CDES + DOMAIN_MANDATORY.get(row["risk_domain"], [])
    for field in required:
        if _is_blank(row.get(field)):
            findings.append(_finding(
                row, "P4 Completeness", "mandatory_cde_present", field,
                f"Mandatory CDE '{field}' is missing for a {row['risk_domain']} exposure."))
    return findings


# ── Principle 3 — Accuracy & Integrity (validity) ────────────────────────────
def check_accuracy(row) -> list[dict]:
    findings = []

    # Currency must be a known ISO code (skip if blank — completeness owns that).
    if not _is_blank(row.get("currency")) and row["currency"] not in config.VALID_CURRENCIES:
        findings.append(_finding(
            row, "P3 Accuracy", "valid_currency_code", "currency",
            f"Currency '{row['currency']}' is not a recognised ISO code."))

    # Notional must be a positive number.
    notional = _num(row.get("notional_amount"))
    if notional is not None and notional <= 0:
        findings.append(_finding(
            row, "P3 Accuracy", "positive_notional", "notional_amount",
            f"Notional amount {notional:,.0f} is not positive."))

    # Exposure must be non-negative.
    exposure = _num(row.get("exposure_amount"))
    if exposure is not None and exposure < 0:
        findings.append(_finding(
            row, "P3 Accuracy", "non_negative_exposure", "exposure_amount",
            f"Exposure amount {exposure:,.0f} is negative."))

    # Maturity must not pre-date the reporting (as-of) date.
    if not _is_blank(row.get("maturity_date")):
        try:
            maturity = datetime.strptime(row["maturity_date"], "%Y-%m-%d")
            if maturity < REPORTING_DATE:
                findings.append(_finding(
                    row, "P3 Accuracy", "maturity_after_asof", "maturity_date",
                    f"Maturity {row['maturity_date']} pre-dates the as-of date "
                    f"{config.REPORTING_DATE}."))
        except ValueError:
            findings.append(_finding(
                row, "P3 Accuracy", "maturity_date_parseable", "maturity_date",
                f"Maturity date '{row['maturity_date']}' is not a valid date."))

    # Credit-only validity: PD and LGD are probabilities in [0, 1]; rating in scale.
    if row["risk_domain"] == "Credit":
        pd_val = _num(row.get("probability_of_default"))
        if pd_val is not None and not (0.0 <= pd_val <= 1.0):
            findings.append(_finding(
                row, "P3 Accuracy", "pd_in_unit_interval", "probability_of_default",
                f"PD {pd_val} is outside the valid [0,1] range."))
        lgd_val = _num(row.get("loss_given_default"))
        if lgd_val is not None and not (0.0 <= lgd_val <= 1.0):
            findings.append(_finding(
                row, "P3 Accuracy", "lgd_in_unit_interval", "loss_given_default",
                f"LGD {lgd_val} is outside the valid [0,1] range."))
        rating = row.get("internal_rating")
        if not _is_blank(rating) and rating not in config.VALID_RATINGS:
            findings.append(_finding(
                row, "P3 Accuracy", "valid_rating_code", "internal_rating",
                f"Internal rating '{rating}' is not on the approved rating scale."))

    return findings


# ── Principle 5 — Timeliness ─────────────────────────────────────────────────
def check_timeliness(row) -> list[dict]:
    if _is_blank(row.get("last_updated_ts")):
        return []  # completeness owns the missing case
    try:
        last = datetime.strptime(row["last_updated_ts"], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return [_finding(row, "P5 Timeliness", "last_updated_parseable",
                         "last_updated_ts", "Timestamp is not parseable.")]
    age_days = (REPORTING_DATE - last).days
    if age_days > config.TIMELINESS_SLA_DAYS:
        return [_finding(
            row, "P5 Timeliness", "within_freshness_sla", "last_updated_ts",
            f"Record last updated {age_days} days before as-of date — exceeds the "
            f"{config.TIMELINESS_SLA_DAYS}-day SLA.")]
    return []


# ── Principle 3 — Integrity (uniqueness, whole-dataset rule) ─────────────────
def check_integrity(df: pd.DataFrame) -> list[dict]:
    """Uniqueness is a population-level rule, not a per-row one."""
    findings = []
    dupes = df[df.duplicated(subset=["exposure_id"], keep=False)]
    for _, row in dupes.iterrows():
        findings.append(_finding(
            row, "P3 Integrity", "unique_exposure_id", "exposure_id",
            f"Duplicate exposure_id '{row['exposure_id']}' — breaks record integrity."))
    return findings


# ── Principle 6 — Adaptability (ad-hoc re-aggregation) ───────────────────────
def adaptability_demo(df: pd.DataFrame, dimensions: list[str]) -> pd.DataFrame:
    """Principle 6 is a *capability*, not a row check: can we re-slice risk data on
    demand for an ad-hoc request (a new stress scenario, a regulator's question)
    without re-engineering? We prove it by aggregating total exposure by an arbitrary
    set of dimensions passed at runtime."""
    work = df.copy()
    work["exposure_amount"] = pd.to_numeric(work["exposure_amount"], errors="coerce")
    return (work.groupby(dimensions)["exposure_amount"]
                .sum().reset_index()
                .rename(columns={"exposure_amount": "total_exposure"}))


# ── Engine ───────────────────────────────────────────────────────────────────
def run(df: pd.DataFrame) -> pd.DataFrame:
    findings: list[dict] = []
    for _, row in df.iterrows():
        findings += check_completeness(row)
        findings += check_accuracy(row)
        findings += check_timeliness(row)
    findings += check_integrity(df)
    return pd.DataFrame(findings)


def scorecard(df: pd.DataFrame, findings: pd.DataFrame) -> pd.DataFrame:
    """Pass rate by principle — the 'evidence of compliance' view (Principle 12)."""
    total = len(df)
    rows = []
    for principle in ["P3 Accuracy", "P3 Integrity", "P4 Completeness", "P5 Timeliness"]:
        flagged = findings[findings["principle"] == principle]["exposure_id"].nunique()
        pass_rate = (total - flagged) / total if total else 1.0
        band = ("Green" if pass_rate >= config.DQ_GREEN_THRESHOLD
                else "Amber" if pass_rate >= config.DQ_AMBER_THRESHOLD else "Red")
        rows.append({"principle": principle, "records_flagged": flagged,
                     "pass_rate": round(pass_rate, 4), "rag": band})
    return pd.DataFrame(rows)


def _summary(df, findings, scard) -> None:
    print(f"\n  DQ rules engine run against {len(df)} records "
          f"(as-of {config.REPORTING_DATE}).")
    print(f"  Total DQ findings: {len(findings)}\n")
    print("  Findings by principle:")
    for principle, n in findings["principle"].value_counts().items():
        print(f"     {principle:<18} {n}")

    print("\n  DQ scorecard (evidence of compliance):")
    print("     {:<18}{:>10}{:>12}{:>8}".format("Principle", "Flagged", "Pass-rate", "RAG"))
    for _, r in scard.iterrows():
        print("     {:<18}{:>10}{:>11.1%}{:>8}".format(
            r["principle"], r["records_flagged"], r["pass_rate"], r["rag"]))

    # Control coverage vs. ground truth (did we catch what we injected?)
    try:
        injected = pd.read_csv(config.ISSUE_LOG_CSV)
        inj_ids = set(injected["exposure_id"])
        caught_ids = set(findings["exposure_id"])
        coverage = len(inj_ids & caught_ids) / len(inj_ids) if inj_ids else 0
        print(f"\n  Control coverage: detected {len(inj_ids & caught_ids)} of "
              f"{len(inj_ids)} records carrying an injected defect "
              f"({coverage:.0%}).")
    except FileNotFoundError:
        pass

    # Principle 6 in action — two ad-hoc slices nobody pre-built.
    print("\n  Principle 6 (Adaptability) — ad-hoc re-aggregation on demand:")
    by_domain = adaptability_demo(df, ["risk_domain"])
    for _, r in by_domain.iterrows():
        print(f"     {r['risk_domain']:<10} total exposure ${r['total_exposure']:,.0f}")
    print("\n  Findings written to", config.DQ_RESULTS_CSV)
    print("  Next: python ai_triage.py  to draft DQGC remediation narratives.\n")


if __name__ == "__main__":
    df = pd.read_csv(config.EXPOSURES_CSV, keep_default_na=False)
    findings = run(df)
    findings.to_csv(config.DQ_RESULTS_CSV, index=False)
    scard = scorecard(df, findings)
    _summary(df, findings, scard)

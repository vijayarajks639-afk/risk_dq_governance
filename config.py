"""
Central configuration for the Risk DQ Governance Copilot.

Everything a reviewer might want to tune lives here: paths, the risk domains we
model, the Critical Data Elements (CDEs) per domain, and the thresholds that the
BCBS 239 DQ rules engine uses. Keeping these in one place is itself a governance
habit — controls and their parameters should be transparent and version-controlled,
not buried in code.
"""

from __future__ import annotations

from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

EXPOSURES_CSV = DATA_DIR / "risk_exposures.csv"   # the synthetic risk dataset
ISSUE_LOG_CSV = DATA_DIR / "issue_log.csv"        # ground-truth of injected issues
DQ_RESULTS_CSV = DATA_DIR / "dq_results.csv"      # output of the rules engine

# ── The "as-of" reporting date ───────────────────────────────────────────────
# In a real Divisional Data Office, risk data is aggregated and reported as of a
# specific business date (the "reporting date" / "as-of date"). Timeliness is
# measured against it (BCBS 239 Principle 5).
REPORTING_DATE = "2026-06-12"   # a recent business date for the demo

# ── Risk domains we model ────────────────────────────────────────────────────
RISK_DOMAINS = ["Credit", "Market", "Liquidity"]

# ── Reference data (used for validity checks) ────────────────────────────────
VALID_CURRENCIES = ["USD", "EUR", "GBP", "INR", "JPY", "AUD", "SGD"]
VALID_RATINGS = ["AAA", "AA", "A", "BBB", "BB", "B", "CCC", "CC", "C", "D"]
SOURCE_SYSTEMS = ["CreditMart", "MarketRiskHub", "LiquidityEngine", "GoldenSourceFDO"]

# ── DQ thresholds (BCBS 239 Principle 5 — Timeliness) ────────────────────────
# How fresh must a record be to be considered timely for risk aggregation?
# If last_updated is older than this many days before the reporting date, the
# record fails the timeliness check.
TIMELINESS_SLA_DAYS = 2

# ── DQ scorecard banding (used by the dashboard) ─────────────────────────────
# Pass-rate bands for the "evidence of compliance" scorecard.
DQ_GREEN_THRESHOLD = 0.98   # >= 98% pass = Green
DQ_AMBER_THRESHOLD = 0.90   # >= 90% pass = Amber, else Red

# ── AI triage (Component 3) ──────────────────────────────────────────────────
# The triage agent drafts DQGC remediation narratives. It runs at $0 by default
# using a templated fallback; if an Anthropic API key is available it uses Claude
# for richer, more specific narratives.
#
# Model: per Anthropic guidance we default to the most capable Opus model. The
# narratives are short, so cost per run is a few cents. Switch to
# "claude-haiku-4-5" here if you want the cheapest possible runs.
AI_MODEL = "claude-opus-4-8"
AI_MAX_ISSUES = 8          # cap issues sent to the model per run (bounds cost)
AI_MAX_TOKENS = 900        # output cap per narrative

ISSUES_CSV = DATA_DIR / "dq_issues.csv"   # grouped issues + remediation narratives


def get_anthropic_key() -> str:
    """Look up the Anthropic API key without committing it anywhere.
    Order: env var -> local .streamlit/secrets.toml (gitignored). Empty = no key,
    so the triage agent uses its templated fallback (zero spend)."""
    import os
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    secrets = ROOT / ".streamlit" / "secrets.toml"
    if secrets.exists():
        try:
            import tomllib
            with open(secrets, "rb") as fh:
                return str(tomllib.load(fh).get("ANTHROPIC_API_KEY", ""))
        except Exception:
            pass
    return ""


def ensure_dirs() -> None:
    """Create output directories if missing (idempotent)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

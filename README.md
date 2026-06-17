# Risk Data Quality Governance Copilot

This demo is created by AI Agent. 

A working demo of a **BCBS 239 risk-data-quality governance and reporting** workflow,
with an AI agent that triages data-quality (DQ) exceptions and drafts remediation
narratives for a Data Quality Governance Council (DQGC).

> **Built as a learning + portfolio project.** All data is **synthetic** and generated
> locally — there is **no** real firm data, no PII, and no confidential material of any
> kind. The goal is to demonstrate, honestly, how a Divisional Data Office modernises
> risk-data quality and reporting, and where AI realistically helps versus where human
> governance must stay in control.

## Why this exists

It maps directly to the mandate of a **Divisional Data
Office**: develop and monitor data-quality standards across risk domains (credit,
market, liquidity), evidence compliance with the **BCBS 239 principles**, run the
**DQGC** cadence, and renovate **risk reporting** onto a strategic platform.

It also doubles as a course: [`BCBS239_LEARNING.md`](BCBS239_LEARNING.md) is a living
document that teaches the framework step by step and collects interview prep notes.

## The four components

| # | Component | File | What it demonstrates |
|---|-----------|------|----------------------|
| 1 | Synthetic risk dataset | `generate_data.py` | Critical Data Elements (CDEs) across credit/market/liquidity, with deliberately injected DQ issues |
| 2 | BCBS 239 DQ rules engine | `dq_rules.py` | Risk-data-aggregation principles: **Accuracy, Completeness, Timeliness, Adaptability** |
| 3 | AI exception-triage agent | `ai_triage.py` | Root-cause hypotheses + DQGC remediation narratives (Claude); human-in-the-loop |
| 4 | Reporting dashboard | `app.py` | Risk-reporting principles + an "evidence of BCBS 239 compliance" scorecard (Streamlit) |

## Quick start

```bash
pip install -r requirements.txt
python generate_data.py        # writes data/risk_exposures.csv + data/issue_log.csv
python dq_rules.py             # runs the DQ checks, writes data/dq_results.csv
streamlit run app.py           # opens the governance dashboard
```

The AI triage step (`ai_triage.py`) is optional and degrades gracefully to a
templated narrative when no `ANTHROPIC_API_KEY` is configured, so the demo runs
end-to-end with zero spend.


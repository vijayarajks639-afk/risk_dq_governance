"""
Component 4 — Risk DQ Governance dashboard (Streamlit).

This is the **reporting** layer, and it deliberately embodies the BCBS 239
risk-reporting principles (7-11):

    P7  Accuracy           -> every number reconciles to the findings/exposure data
    P8  Comprehensiveness  -> all three risk domains + all DQ principles in one view
    P9  Clarity & useful   -> RAG scorecard + plain-English issues for decision-makers
    P10 Frequency          -> re-runs on demand as the data refreshes
    P11 Distribution       -> a single shareable view for the DQGC and senior management

It reads the artefacts produced by the other three components and renders the
"evidence of compliance" a Divisional Data Office takes to the council.

Run:  streamlit run app.py
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import config
import dq_rules

st.set_page_config(page_title="Risk DQ Governance", page_icon="🛡️", layout="wide")

RAG_COLORS = {"Green": "#2e7d32", "Amber": "#e65100", "Red": "#c62828"}


# ── Data loading (graceful if the pipeline hasn't been run) ──────────────────
@st.cache_data
def load_data():
    exposures = pd.read_csv(config.EXPOSURES_CSV, keep_default_na=False)
    findings = pd.read_csv(config.DQ_RESULTS_CSV, keep_default_na=False)
    issues = (pd.read_csv(config.ISSUES_CSV, keep_default_na=False)
              if config.ISSUES_CSV.exists() else pd.DataFrame())
    return exposures, findings, issues


def rag_style(val):
    color = RAG_COLORS.get(val, "")
    return f"background-color: {color}; color: white; font-weight: 600" if color else ""


def pass_rate_by_domain(exposures, findings):
    rows = []
    for domain in sorted(exposures["risk_domain"].unique()):
        total = (exposures["risk_domain"] == domain).sum()
        flagged = findings[findings["risk_domain"] == domain]["exposure_id"].nunique()
        rows.append({"risk_domain": domain,
                     "pass_rate": round((total - flagged) / total, 4) if total else 1.0})
    return pd.DataFrame(rows).set_index("risk_domain")


# ── Header ───────────────────────────────────────────────────────────────────
st.title("🛡️ Risk Data Quality Governance — BCBS 239")
st.caption(
    "Demonstration of an FRM Divisional Data Office workflow: monitor risk-data "
    "quality across credit, market and liquidity, evidence BCBS 239 compliance, and "
    "feed the DQGC remediation process. **All data is synthetic — no real firm data.**"
)

try:
    exposures, findings, issues = load_data()
except FileNotFoundError:
    st.error("Data not found. Run the pipeline first:\n\n"
             "```\npython generate_data.py\npython dq_rules.py\npython ai_triage.py\n```")
    st.stop()

# Recompute the scorecard live so the dashboard always reconciles to source (P7).
scard = dq_rules.scorecard(exposures, findings)
total_records = len(exposures)
flagged_records = findings["exposure_id"].nunique()
overall_pass = (total_records - flagged_records) / total_records if total_records else 1.0
high_issues = int((issues["priority"] == "High").sum()) if not issues.empty else 0

# ── KPI row ──────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Exposures (as-of)", f"{total_records:,}")
c2.metric("DQ findings", f"{len(findings):,}")
c3.metric("Overall pass-rate", f"{overall_pass:.1%}")
c4.metric("Governed issues", f"{len(issues):,}" if not issues.empty else "—")
c5.metric("High priority", high_issues if not issues.empty else "—")
st.caption(f"Reporting (as-of) date: **{config.REPORTING_DATE}** · "
           f"Domains: {', '.join(config.RISK_DOMAINS)}")

tab_score, tab_findings, tab_issues, tab_adapt = st.tabs(
    ["📊 Scorecard", "🔎 Findings", "🗂️ DQGC Issues", "🧭 Adaptability (P6)"])

# ── Tab 1: Scorecard (evidence of compliance — P9, P12) ──────────────────────
with tab_score:
    st.subheader("DQ Scorecard — evidence of compliance")
    st.caption("Pass-rate by BCBS 239 principle, RAG-banded "
               f"(Green ≥ {config.DQ_GREEN_THRESHOLD:.0%}, "
               f"Amber ≥ {config.DQ_AMBER_THRESHOLD:.0%}). This is the view that goes "
               "to the DQGC and to supervisors during a Principle 12 review.")
    show = scard.rename(columns={
        "principle": "BCBS 239 Principle", "records_flagged": "Records flagged",
        "pass_rate": "Pass-rate", "rag": "RAG"})
    styled = (show.style
              .format({"Pass-rate": "{:.1%}"})
              .map(rag_style, subset=["RAG"]))
    st.dataframe(styled, width="stretch", hide_index=True)

    st.markdown("**Pass-rate by risk domain** — comprehensiveness across stripes (P8)")
    st.bar_chart(pass_rate_by_domain(exposures, findings), height=260)

# ── Tab 2: Findings (P7 accuracy, P8 comprehensiveness) ──────────────────────
with tab_findings:
    st.subheader("DQ findings — where the breaks are")
    left, right = st.columns(2)
    with left:
        st.markdown("**Findings by principle**")
        st.bar_chart(findings["principle"].value_counts(), height=260)
    with right:
        st.markdown("**Findings by risk domain**")
        st.bar_chart(findings["risk_domain"].value_counts(), height=260)

    st.markdown("**Findings detail** — filter and inspect (drill-down for P9 clarity)")
    principles = ["(all)"] + sorted(findings["principle"].unique())
    pick = st.selectbox("Filter by principle", principles)
    view = findings if pick == "(all)" else findings[findings["principle"] == pick]
    st.dataframe(view[["exposure_id", "risk_domain", "principle", "rule",
                       "field", "detail"]],
                 width="stretch", hide_index=True, height=320)

# ── Tab 3: DQGC issues + remediation narratives (P13) ────────────────────────
with tab_issues:
    st.subheader("Governed issues for the DQGC")
    if issues.empty:
        st.info("No issues file yet. Run `python ai_triage.py` to triage findings "
                "into governed issues with remediation narratives.")
    else:
        st.caption("Raw findings triaged into governed issues — owner, priority, and a "
                   "remediation narrative each (Principle 13 — remedial actions). "
                   "**AI drafts; the DQGC decides.**")
        prio_filter = st.radio("Show", ["All", "High", "Medium", "Low"],
                               horizontal=True)
        rows = issues if prio_filter == "All" else issues[issues["priority"] == prio_filter]
        for _, r in rows.iterrows():
            badge = {"High": "🔴", "Medium": "🟠", "Low": "🟡"}.get(r["priority"], "⚪")
            with st.expander(
                    f"{badge} {r['issue_id']} · {r['principle']} · "
                    f"{r['record_count']} record(s) · {r['priority']} priority"):
                st.markdown(f"**Failed control:** `{r['rule']}` on CDE `{r['field']}`  ")
                st.markdown(f"**Domain(s):** {r['domains']}  ")
                st.markdown(f"**Example IDs:** {r['sample_ids']}")
                st.markdown("---")
                st.markdown(r["remediation_narrative"])

# ── Tab 4: Adaptability — ad-hoc re-aggregation on demand (P6) ────────────────
with tab_adapt:
    st.subheader("Adaptability — re-slice risk data on demand (Principle 6)")
    st.caption("BCBS 239 Principle 6: a bank must aggregate risk data flexibly to meet "
               "ad-hoc requests — a new stress scenario, a regulator's question — "
               "without re-engineering. Pick any dimensions and the total exposure "
               "re-aggregates instantly.")
    dims = st.multiselect(
        "Aggregate total exposure by:",
        options=["risk_domain", "legal_entity", "currency", "product_type",
                 "source_system"],
        default=["risk_domain"])
    if dims:
        agg = dq_rules.adaptability_demo(exposures, dims)
        agg["total_exposure"] = agg["total_exposure"].map(lambda v: f"${v:,.0f}")
        st.dataframe(agg, width="stretch", hide_index=True, height=360)
    else:
        st.info("Select at least one dimension.")

st.divider()
st.caption("Risk DQ Governance Copilot · synthetic data · a portfolio + learning "
           "project. The AI drafts; governance stays human.")

"""
Component 3 — AI exception-triage agent.

Two jobs, mirroring how a real Divisional Data Office works:

1. **Triage** — collapse the raw DQ findings into a small set of *governed issues*.
   You don't raise 120 tickets for 120 failing records; you raise **one issue per
   failing control population** ("31 records missing a mandatory currency CDE") and
   manage that through the DQGC. This grouping is the heart of DQ issue management.

2. **Draft remediation narratives** — for each issue, produce a DQGC-ready write-up:
   root-cause hypothesis, risk impact (in BCBS 239 terms), recommended remediation,
   suggested owner, and priority. Claude drafts; **the DQGC decides** — the human
   governance loop stays in control (Principle 1), and the output feeds the remedial-
   action process (Principle 13).

The agent runs at **$0 by default** using a templated fallback. If an Anthropic API
key is available (env var or local .streamlit/secrets.toml), it uses Claude for
richer, issue-specific narratives.

Run:  python ai_triage.py
Out:  data/dq_issues.csv   (grouped issues + remediation narratives)
"""

from __future__ import annotations

import textwrap

import pandas as pd

import config

# Priority weighting per principle (integrity/accuracy of CDEs tends to hurt most).
PRINCIPLE_WEIGHT = {
    "P3 Integrity": 1.0,
    "P3 Accuracy": 0.9,
    "P4 Completeness": 0.8,
    "P5 Timeliness": 0.6,
}


# ── Step 1: triage findings into governed issues ─────────────────────────────
def build_issues(findings: pd.DataFrame) -> pd.DataFrame:
    """Group findings by the control that failed (principle + rule + field)."""
    grouped = (findings.groupby(["principle", "rule", "field"])
                       .agg(record_count=("exposure_id", "nunique"),
                            domains=("risk_domain", lambda s: ", ".join(sorted(set(s)))),
                            sample_detail=("detail", "first"),
                            sample_ids=("exposure_id",
                                        lambda s: ", ".join(list(dict.fromkeys(s))[:5])))
                       .reset_index())

    # Priority score = population size x principle weight -> High/Medium/Low.
    grouped["weight"] = grouped["principle"].map(PRINCIPLE_WEIGHT).fillna(0.5)
    grouped["score"] = grouped["record_count"] * grouped["weight"]
    hi = grouped["score"].quantile(0.66) if len(grouped) > 2 else grouped["score"].max()
    lo = grouped["score"].quantile(0.33) if len(grouped) > 2 else 0
    grouped["priority"] = grouped["score"].apply(
        lambda s: "High" if s >= hi else ("Low" if s <= lo else "Medium"))

    grouped = grouped.sort_values("score", ascending=False).reset_index(drop=True)
    grouped.insert(0, "issue_id", [f"ISSUE-{i+1:03d}" for i in range(len(grouped))])
    return grouped


# ── Step 2a: templated remediation narrative (the $0 fallback) ───────────────
SUGGESTED_OWNER = {
    "P4 Completeness": "Source system owner + FRM Divisional Data Office",
    "P3 Accuracy": "Risk domain data steward + source system owner",
    "P3 Integrity": "FRM Divisional Data Office (golden-source reconciliation)",
    "P5 Timeliness": "Source system owner + Technology (feed scheduling)",
}


def templated_narrative(issue: pd.Series) -> str:
    principle = issue["principle"]
    owner = SUGGESTED_OWNER.get(principle, "FRM Divisional Data Office")
    return textwrap.dedent(f"""\
        **Root-cause hypothesis:** {issue['record_count']} record(s) in
        {issue['domains']} failed control `{issue['rule']}` on CDE `{issue['field']}`.
        Likely drivers: upstream source-system capture gaps, a broken or late feed, or
        a reference-data/mapping defect at the golden source.

        **Risk impact ({principle}):** weakens the risk-data-aggregation capability for
        the affected domain(s); if unremediated, aggregated exposures and reporting may
        be incomplete or inaccurate, undermining evidence of BCBS 239 compliance.

        **Recommended remediation:** trace the affected records to their source system
        and golden source; confirm whether the defect is at capture, transport, or
        transformation; apply a fix at source (not a downstream patch); add/strengthen
        the DQ control and backfill corrected values.

        **Suggested owner:** {owner}.
        **Priority:** {issue['priority']}.""")


# ── Step 2b: Claude-drafted narrative (when a key is available) ───────────────
SYSTEM_PROMPT = (
    "You are a risk data governance analyst supporting a Data Quality Governance "
    "Council (DQGC) at a global systemically important bank, operating under the "
    "BCBS 239 principles for risk data aggregation and reporting. You draft concise, "
    "factual remediation narratives for data-quality issues. Never invent data or "
    "numbers beyond what you are given. Be specific, senior, and practical. The AI "
    "drafts; the DQGC decides."
)


def _claude_prompt(issue: pd.Series) -> str:
    return textwrap.dedent(f"""\
        Draft a DQGC remediation narrative for this data-quality issue. Use these
        exact facts; do not invent counts.

        - Issue ID: {issue['issue_id']}
        - BCBS 239 principle violated: {issue['principle']}
        - Failed control / rule: {issue['rule']}
        - Affected CDE (data field): {issue['field']}
        - Records affected: {issue['record_count']}
        - Risk domain(s): {issue['domains']}
        - Example finding: {issue['sample_detail']}

        Produce markdown with exactly these four bold sections, each 1-3 sentences:
        **Root-cause hypothesis:** (2-3 plausible causes)
        **Risk impact ({issue['principle']}):** (tie to risk aggregation/reporting)
        **Recommended remediation:** (concrete, fix-at-source steps)
        **Suggested owner & priority:** (name a plausible owner; priority = {issue['priority']})
        Keep the whole thing under 170 words.""")


def claude_narrative(client, issue: pd.Series) -> str:
    resp = client.messages.create(
        model=config.AI_MODEL,
        max_tokens=config.AI_MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _claude_prompt(issue)}],
    )
    return "".join(block.text for block in resp.content if block.type == "text").strip()


# ── Orchestration ────────────────────────────────────────────────────────────
def triage() -> pd.DataFrame:
    findings = pd.read_csv(config.DQ_RESULTS_CSV, keep_default_na=False)
    issues = build_issues(findings)

    key = config.get_anthropic_key()
    client = None
    mode = "templated (no API key — $0)"
    if key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            mode = f"Claude ({config.AI_MODEL})"
        except Exception as exc:  # SDK missing or init failed -> graceful fallback
            print(f"  (Anthropic SDK unavailable: {exc} — using templated fallback.)")

    narratives, sources = [], []
    for i, issue in issues.iterrows():
        text, src = None, None
        if client is not None and i < config.AI_MAX_ISSUES:
            try:
                text = claude_narrative(client, issue)
                src = f"claude:{config.AI_MODEL}"
            except Exception as exc:
                print(f"  (Claude call failed for {issue['issue_id']}: {exc} "
                      f"— falling back to template.)")
        if text is None:
            text = templated_narrative(issue)
            src = "templated:rules-v1"
        narratives.append(text)
        sources.append(src)

    # Stamp AI-governance metadata on every narrative. This is what makes the AI
    # Governance tab show *real* provenance (which model, when, review status) rather
    # than a mock-up — and it's the audit trail Principle 12 (Review) expects.
    from datetime import datetime as _dt
    issues["remediation_narrative"] = narratives
    issues["narrative_source"] = sources
    issues["generated_ts"] = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
    issues["review_status"] = "Pending DQGC review"   # nothing is auto-approved
    issues["human_reviewed"] = "No"
    issues.to_csv(config.ISSUES_CSV, index=False)
    return issues, mode


def _summary(issues: pd.DataFrame, mode: str) -> None:
    print(f"\n  Triaged {issues['record_count'].sum()} findings into "
          f"{len(issues)} governed issue(s).  Narrative source: {mode}.")
    print(f"  Priority mix: " + ", ".join(
        f"{p}={n}" for p, n in issues['priority'].value_counts().items()))
    print("\n  Top issues for the DQGC:")
    for _, r in issues.head(3).iterrows():
        print(f"\n  -- {r['issue_id']}  [{r['priority']}]  {r['principle']} "
              f"| {r['record_count']} record(s) | {r['domains']}")
        print(textwrap.indent(r["remediation_narrative"], "     "))
    print(f"\n  Full issue log written to {config.ISSUES_CSV}")
    print("  Next: streamlit run app.py  to open the governance dashboard.\n")


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows console is cp1252 by default
    except Exception:
        pass
    issues, mode = triage()
    _summary(issues, mode)

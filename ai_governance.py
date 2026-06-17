"""
AI governance reference data for the dashboard's "AI Governance" tab.

This module is the "identify AI risk in the process and map it" deliverable, made
concrete. It holds three things — all **static reference data, $0 at runtime**:

1. AI_TOUCHPOINTS    — every place a model touches the risk-data/reporting flow in
                       THIS demo (here: one touchpoint, the triage agent).
2. AI_CONTROLS       — an **honest** control self-assessment of that touchpoint:
                       what's in place (Green), partial (Amber), or a gap (Red).
3. AI_PRINCIPLE_MAP  — the reference AI-risk -> control -> BCBS 239 principle map for
                       all 14 principles, tagged to the regime (EU AI Act / US MRM /
                       BIS) the control helps satisfy.

The honesty of #2 is deliberate: showing your *own* AI risks and gaps is exactly the
discipline a Divisional Data Office must apply to every model. "AI is a model."
"""

from __future__ import annotations

from collections import Counter

import config

# ── 1. AI touchpoint register ────────────────────────────────────────────────
# You cannot govern what you cannot see. Step one of AI governance is an inventory
# of every place a model touches the flow. This demo has exactly one.
AI_TOUCHPOINTS = [
    {
        "ID": "AI-TP-01",
        "Component": "ai_triage.py — DQ exception-triage agent",
        "Purpose": "Draft DQGC root-cause & remediation narratives from DQ findings",
        "Model": config.AI_MODEL,
        "Owner (1st line)": "FRM Divisional Data Office",
        "Validator (2nd line)": "Model Risk Management",
        "Data used": "Synthetic DQ findings only — no PII, no real firm data",
        "Criticality": "Medium — advisory, human-approved before any action",
        "Human-in-loop": "Yes",
    },
]

# ── 2. Control self-assessment for the demo's AI touchpoint ──────────────────
# status: Green = in place · Amber = partial · Red = gap (honest!)
AI_CONTROLS = [
    {"Control": "Hallucination guardrail", "Status": "Green",
     "BCBS 239": "P3 Accuracy",
     "Evidence / gap": "Prompt rule: 'use these exact facts; do not invent counts'"},
    {"Control": "Human-in-the-loop (no auto-action)", "Status": "Green",
     "BCBS 239": "P1 / P13",
     "Evidence / gap": "Narratives flagged 'Pending DQGC review' — AI drafts, council decides"},
    {"Control": "Provider resilience / fallback", "Status": "Green",
     "BCBS 239": "P5 / P2",
     "Evidence / gap": "Graceful $0 templated fallback when the model is unavailable"},
    {"Control": "Data privacy (no PII to model)", "Status": "Green",
     "BCBS 239": "P11 Distribution",
     "Evidence / gap": "Synthetic data only; no PII leaves the process"},
    {"Control": "Model / version audit logging", "Status": "Amber",
     "BCBS 239": "P12 Review",
     "Evidence / gap": "Model, version & timestamp now stamped per narrative; full prompt/input log still TODO"},
    {"Control": "Automated output reconciliation", "Status": "Red",
     "BCBS 239": "P7 Reporting accuracy",
     "Evidence / gap": "GAP: no automated check that narrative claims reconcile to source numbers"},
    {"Control": "Explainability / drift monitoring", "Status": "Red",
     "BCBS 239": "P9 / P10",
     "Evidence / gap": "GAP: no drift or eval monitoring (single-shot here; would matter in production)"},
]

# ── 3. Reference: the full 14-principle AI-risk map ──────────────────────────
AI_PRINCIPLE_MAP = [
    {"#": "P1",  "Principle": "Governance",            "AI risk": "Shadow AI; unclear model ownership",
     "Control to embed": "AI use-case inventory + named owner + DQGC oversight; extend Risk Data Policy", "Regime": "US MRM · EU AI Act Art.9"},
    {"#": "P2",  "Principle": "Architecture & lineage", "AI risk": "Black-box transforms break lineage; provider outage",
     "Control to embed": "Model registry; lineage around model I/O; fallback / kill-switch", "Regime": "US MRM"},
    {"#": "P3",  "Principle": "Accuracy & Integrity",   "AI risk": "Hallucination; non-determinism",
     "Control to embed": "Temp 0; 'don't invent' guardrails; automated reconciliation vs source", "Regime": "EU AI Act (accuracy)"},
    {"#": "P4",  "Principle": "Completeness",           "AI risk": "AI silently drops / imputes records",
     "Control to embed": "Flag imputed-vs-actual; coverage checks", "Regime": "US MRM"},
    {"#": "P5",  "Principle": "Timeliness",             "AI risk": "Model latency / outage breaks the cycle",
     "Control to embed": "Model SLA monitoring; templated fallback", "Regime": "Operational resilience"},
    {"#": "P6",  "Principle": "Adaptability",           "AI risk": "Ungoverned ad-hoc NL outputs used raw",
     "Control to embed": "Governed NL-query layer; log + validate before use", "Regime": "US MRM"},
    {"#": "P7",  "Principle": "Accuracy (reporting)",   "AI risk": "LLM narratives that don't reconcile",
     "Control to embed": "Numbers from data not model; 'AI-drafted, human-verified'", "Regime": "EU AI Act (human oversight)"},
    {"#": "P8",  "Principle": "Comprehensiveness",      "AI risk": "AI summary omits a material risk",
     "Control to embed": "Human material-coverage review; stripe / exposure checklist", "Regime": "US MRM"},
    {"#": "P9",  "Principle": "Clarity & usefulness",   "AI risk": "Automation bias; fluent-but-wrong",
     "Control to embed": "Confidence signals; label AI content; human sign-off", "Regime": "EU AI Act (transparency)"},
    {"#": "P10", "Principle": "Frequency",              "AI risk": "Faster output but model drift",
     "Control to embed": "Drift monitoring; periodic re-validation", "Regime": "US MRM"},
    {"#": "P11", "Principle": "Distribution",           "AI risk": "Data leakage to model / provider",
     "Control to embed": "No PII to model; access controls + DLP; vendor terms", "Regime": "GDPR · EU AI Act"},
    {"#": "P12", "Principle": "Review (supervisory)",   "AI risk": "Supervisors examine AI governance",
     "Control to embed": "Keep model docs / validation / logs review-ready; explainability", "Regime": "BIS OP24 · US MRM"},
    {"#": "P13", "Principle": "Remedial actions",       "AI risk": "AI remediation actioned unvalidated; model bias / drift",
     "Control to embed": "Human approval + audit trail; remediate the model too", "Regime": "US MRM"},
    {"#": "P14", "Principle": "Home / host cooperation","AI risk": "EU AI Act vs US MRM divergence",
     "Control to embed": "Map controls to multiple regimes; one global AI standard", "Regime": "EU AI Act + US MRM"},
]


def control_counts() -> Counter:
    """How many AI controls are Green / Amber / Red."""
    return Counter(c["Status"] for c in AI_CONTROLS)


def overall_posture() -> str:
    """Honest overall AI-governance posture for the demo's touchpoint.
    Any open gap (Red) or partial (Amber) keeps us out of 'Green' — controls you
    haven't finished are controls you can't yet evidence."""
    counts = control_counts()
    # Red only if open gaps outweigh the controls in place; otherwise any gap or
    # partial keeps us at Amber ("in active remediation, gaps known"); all-Green = Green.
    if counts.get("Red", 0) and counts.get("Red", 0) >= counts.get("Green", 0):
        return "Red"
    if counts.get("Red", 0) or counts.get("Amber", 0):
        return "Amber"
    return "Green"

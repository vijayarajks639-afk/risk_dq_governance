#!/usr/bin/env python3
"""
AI & Risk Weekly Recap  —  delivered Sunday 8:00 PM IST

Format (deliberately different from the daily digest):
  • Top 10 stories of the week   — best across all domains (when:7d)
  • Regulatory Pulse             — what moved in AI regulation this week
  • Framework Deep Dive          — one framework in depth, rotating weekly
  • Interview Q&A Spotlight      — 3 real Q&As with model answers, rotating
  • Must-Read Weekend List       — 3 long-form articles/papers

Delivery: Gmail SMTP (SSL). Triggered by GitHub Actions every Sunday.
"""

import os
import re
import json
import ssl
import time
import socket
import html as html_lib
import smtplib
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import feedparser
import pytz

IST   = pytz.timezone("Asia/Kolkata")
UA    = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_SSL  = ssl.create_default_context()
socket.setdefaulttimeout(18)

# ──────────────────────────────────────────────────────────────────────────
# Rotating content  (week-of-year index)
# ──────────────────────────────────────────────────────────────────────────

FRAMEWORK_DEEP_DIVES = [
    {
        "name": "NIST AI Risk Management Framework (AI RMF 1.0)",
        "tldr": "The US voluntary framework for managing AI risk across the lifecycle.",
        "bullets": [
            "GOVERN — policies, culture, roles & accountability for AI risk",
            "MAP    — identify context, use cases, risks and their likelihood/impact",
            "MEASURE — analyse, assess, benchmark, and track AI risks",
            "MANAGE  — prioritise, respond to, and monitor AI risks",
            "GenAI Profile (NIST AI 600-1) adds 200+ actions for LLMs & foundation models",
            "Maps to ISO/IEC 42001, EU AI Act, and Treasury FS AI RMF (230 controls)",
        ],
        "q": "Walk me through how you'd operationalise the NIST AI RMF for a retail credit-scoring model.",
        "hint": "Cover: GOVERN (policy + ownership), MAP (data inputs, model type, affected population), MEASURE (bias metrics, model performance), MANAGE (thresholds, escalation, retraining triggers).",
    },
    {
        "name": "BCBS 239 — Principles for Risk Data Aggregation & Reporting",
        "tldr": "14 BIS principles covering how banks must aggregate and report risk data.",
        "bullets": [
            "Governance & Infrastructure (P1-P2): Board ownership; data architecture & IT infrastructure",
            "Risk Data Aggregation (P3-P6): Accuracy & integrity; completeness; timeliness; adaptability",
            "Risk Reporting (P7-P11): Accuracy; comprehensiveness; clarity & usefulness; frequency; distribution",
            "Supervisory Review (P12-P14): Review; remediation; home/host cooperation",
            "AI relevance: Any AI risk model is a consumer of BCBS 239 data pipelines",
            "Hard to evidence: P4 (completeness) and P6 (adaptability) most cited in supervisory findings",
        ],
        "q": "Which BCBS 239 principles are hardest to evidence for an AI-driven risk model, and how would you measure compliance?",
        "hint": "P4 completeness (how do you prove absence?) + P6 adaptability (stress scenario testing of pipelines) + P7 accuracy (model output auditability chain back to raw data).",
    },
    {
        "name": "EU AI Act — Risk-Tiered Regulatory Framework",
        "tldr": "The world's first comprehensive binding AI law. Full enforcement August 2026.",
        "bullets": [
            "Unacceptable risk: Banned outright (social scoring, real-time biometrics in public)",
            "High risk (Annex III): Credit scoring, employment AI, critical infrastructure — full obligations",
            "High-risk obligations: Conformity assessment, technical docs (Art.11), data governance (Art.10)",
            "Transparency (Art.13), human oversight (Art.14), accuracy/robustness (Art.15)",
            "GPAI models: Transparency + usage policy obligations; systemic-risk models add more",
            "Penalties: Up to €35M or 7% of global revenue for prohibited-practice violations",
            "Timeline: GPAI rules Aug 2025; high-risk Annex III compliance Dec 2026/2027 (Digital Omnibus)",
        ],
        "q": "How would you classify and govern a generative AI tool used for internal credit analysis under the EU AI Act?",
        "hint": "Classify: likely high-risk (Annex III cat 5b — creditworthiness). Obligations: data governance (Art.10), human oversight (Art.14), conformity assessment, EU DB registration. GPAI overlay if using foundation model.",
    },
    {
        "name": "US Model Risk Management — SR 11-7 & 2026 Successor",
        "tldr": "The Fed/OCC model risk framework — revised in 2026 to cover GenAI/agentic AI.",
        "bullets": [
            "SR 11-7 (2011): Three pillars — development & implementation; validation; governance",
            "Validation: Conceptual soundness, ongoing monitoring, outcomes analysis",
            "2026 revision: Reshaped scope; GenAI/agentic AI explicitly addressed",
            "New: Model inventory requirements; third-party/vendor model governance",
            "Key tension: LLMs are probabilistic, not deterministic — traditional validation doesn't map cleanly",
            "Three lines: 1st (model owners), 2nd (model risk/validation), 3rd (internal audit)",
        ],
        "q": "How does model validation differ for a traditional logistic regression scorecard vs. an LLM used for credit decisioning?",
        "hint": "Scorecard: deterministic, explainable, PSI/CSI monitoring. LLM: non-deterministic, hallucination risk, adversarial inputs, prompt injection, no single 'output distribution' — requires red-teaming, output sampling, human-in-loop oversight. Both need conceptual soundness but the evidence looks very different.",
    },
    {
        "name": "ISO/IEC 42001 — AI Management System Standard",
        "tldr": "First certifiable AI management system standard (published Oct 2023).",
        "bullets": [
            "Plan-Do-Check-Act lifecycle: same structure as ISO 27001 (familiar to compliance teams)",
            "Clause 6: AI risk & impact assessment — identify, analyse, treat AI risks",
            "Clause 8: Operational planning — AI system objectives, data quality, lifecycle controls",
            "Annex A: 38 controls (governance, data, development, deployment, monitoring)",
            "Annex B: Implementation guidance for different org roles (provider vs. deployer)",
            "Maps to NIST AI RMF; satisfies ~60-80% of EU AI Act requirements",
            "Differentiator vs. ISO 27001: AI-specific risks (fairness, explainability, drift)",
        ],
        "q": "How does ISO 42001 complement the NIST AI RMF, and which would you implement first in a mid-size bank?",
        "hint": "NIST AI RMF = framework (what to do, flexible). ISO 42001 = certifiable standard (how to do it, auditable). In a bank: NIST AI RMF first for direction + culture; ISO 42001 to operationalise with audit evidence. ISO 42001 certification gives regulators something concrete to point to.",
    },
    {
        "name": "RBI FREE-AI Framework (India, Aug 2025)",
        "tldr": "Framework for Responsible & Ethical Enablement of AI in Indian financial services.",
        "bullets": [
            "7 Sutras (guiding principles): Fairness, Reliability, Explainability, Ethics, Efficiency, AI Security, Accountability",
            "6 Pillars: Governance; Risk Management; Data Management; Model Management; Customer Protection; Human Oversight",
            "26 Recommendations across the six pillars",
            "Voluntary guidance (as of 2025); expected to become binding",
            "Scope: All RBI-regulated entities (banks, NBFCs, payment companies)",
            "Unique: Explicitly covers agentic AI and third-party AI providers (Big Tech risk)",
            "Interview angle: Shows India's FS regulator is serious about AI governance — expect exam questions",
        ],
        "q": "What governance controls would you put around an AI model at an Indian private bank under the RBI FREE-AI framework?",
        "hint": "Pillar 2 (Risk Management): model risk policy, validation. Pillar 3 (Data): BCBS 239-aligned DQ. Pillar 4 (Model Management): inventory, version control, drift monitoring. Pillar 5 (Customer Protection): explainability for adverse decisions. Sutra: Accountability — clear ownership at Board level.",
    },
    {
        "name": "Data Quality Dimensions & Governance",
        "tldr": "The foundational 6 DQ dimensions — backbone of BCBS 239 and trustworthy AI.",
        "bullets": [
            "Accuracy: Does the data correctly represent real-world values?",
            "Completeness: Is all required data present? (BCBS P4 — hardest to evidence)",
            "Consistency: Is data the same across systems/sources? (golden source concept)",
            "Timeliness: Is data available when needed? (BCBS P6; T+0 vs T+1 for risk reporting)",
            "Validity: Does data conform to defined formats, ranges, business rules?",
            "Uniqueness: No duplicate records (especially critical for customer/counterparty data)",
            "AI relevance: Training data quality = model quality. Garbage in, garbage out — at regulatory scale.",
        ],
        "q": "How do you measure and monitor data quality feeding a regulatory risk model, and how does this connect to BCBS 239?",
        "hint": "Define DQ metrics per dimension → automated DQ rules in pipeline → DQ scorecard reported to risk committee → thresholds trigger model hold/alert. BCBS 239 P3 (accuracy), P4 (completeness), P5 (timeliness) directly map. Mention: lineage, golden source, reconciliation.",
    },
]

INTERVIEW_QAS = [
    [
        {
            "q": "What is BCBS 239 and why should an AI risk manager care about it?",
            "a": "BCBS 239 sets 14 BIS principles for Risk Data Aggregation and Reporting (RDAR). For an AI risk manager it matters because: (1) AI risk models consume data pipelines that must meet P3-P6 accuracy/completeness/timeliness/adaptability; (2) AI-generated risk reports must meet P7-P11 on reporting quality; (3) supervisory findings on BCBS 239 often expose the same weak data infrastructure that will fail AI governance audits. Think of BCBS 239 as the data plumbing — AI governance is the appliance that sits on top.",
        },
        {
            "q": "How do you explain AI explainability to a non-technical regulator?",
            "a": "Use three levels: (1) Global explainability — what factors drive the model's decisions overall (e.g. income, payment history account for 65% of credit score weight); (2) Local explainability — why THIS specific customer got THIS decision (SHAP values, LIME output translated into plain-language reasons); (3) Auditability — can you reconstruct any past decision from logs? The EU AI Act (Art.13) and SR 11-7 successor both require you to explain to affected persons in meaningful, understandable terms. Bring a one-page 'model explanation card' to the exam.",
        },
        {
            "q": "What is the three lines of defence model as applied to AI risk?",
            "a": "1st line: AI model owners and business users — own the model, embed controls, monitor daily KPIs, flag anomalies. 2nd line: Model Risk / AI Risk function — independent validation (conceptual soundness, ongoing monitoring, outcomes analysis), challenge the 1st line, maintain model inventory, set risk appetite. 3rd line: Internal Audit — periodically audit the entire MRM framework, validate that 1st and 2nd line controls are operating. Board / Risk Committee sit above all three. Key interview point: the 2nd line must be genuinely independent — organisational separation, no reporting line to the model owner.",
        },
    ],
    [
        {
            "q": "Walk me through how you'd validate an LLM used for internal risk reporting.",
            "a": "Traditional validation doesn't map cleanly. I'd structure it as: (1) Conceptual soundness — is LLM the right tool? Benchmark against rule-based alternative; (2) Input governance — prompt injection testing, input sanitisation, context window security; (3) Output testing — sample-based human review of outputs, factual accuracy rate, hallucination rate measured against ground truth; (4) Adversarial testing — red-teaming, boundary probing; (5) Ongoing monitoring — output drift detection, production sampling, human-in-loop checkpoints; (6) Human oversight — who reviews before outputs reach decision-makers? SR 11-7 successor explicitly flags that probabilistic models require adapted validation approaches.",
        },
        {
            "q": "How would you build an AI model inventory for a bank?",
            "a": "Start with a clear definition: what counts as a 'model' (include ML, LLMs, vendor models, spreadsheet-based statistical models). Then capture for each: model ID, owner, purpose, risk tier, data inputs, training date, validation date, next review date, production status, performance thresholds, and regulatory mapping (which regulation triggers this model's risk tier). Maintain in a system of record (not a spreadsheet). Key governance: model risk policy defines tiering (high/medium/low), validation frequency by tier, and escalation when thresholds breach. SR 11-7 successor and EU AI Act both require this. Regulators will ask to see it on day 1 of an exam.",
        },
        {
            "q": "What's the difference between AI bias and model risk, and do they need separate governance?",
            "a": "Model risk (SR 11-7) is about models being wrong in ways that cause financial loss or misstatement — it's accuracy/reliability focused. AI bias is about models being systematically unfair to protected groups — it's equity/ethics focused. They overlap (a biased model is also a poorly performing one on some segment) but require different governance: model risk uses statistical validation; bias requires fairness metrics (demographic parity, equalised odds, etc.), disparate impact testing, and explainability for adverse actions. In a bank: model risk sits in 2nd line risk; AI bias governance typically sits across 2nd line risk + legal/compliance + ethics. EU AI Act Art.10 and US FHA/ECOA both require bias controls — you need both, not one or the other.",
        },
    ],
    [
        {
            "q": "The EU AI Act fully enforces August 2026. What should a bank's AI governance team do NOW?",
            "a": "Immediate actions: (1) Complete AI inventory — classify every AI system against Annex III to identify high-risk; (2) Gap analysis against high-risk obligations (Art.9-15); (3) For high-risk systems: appoint conformity assessment lead, begin technical documentation (Art.11); (4) GPAI: if you use foundation model APIs (OpenAI, Anthropic etc.), check provider compliance documentation; (5) Data governance: Art.10 training data requirements need a data quality baseline now; (6) Human oversight: document who signs off on high-risk AI outputs. Key deadline: high-risk Annex III systems (incl. credit scoring) must comply by December 2026/2027 (Digital Omnibus pushed this). Don't wait.",
        },
        {
            "q": "What is model drift and how do you detect and respond to it?",
            "a": "Model drift = the model's performance degrades over time because the real world has changed from the training data. Two types: (1) Data drift / covariate shift — input feature distributions change (e.g. income patterns shift post-recession); detect with PSI (Population Stability Index), CSI (Characteristic Stability Index), KL divergence; (2) Concept drift — the relationship between inputs and target changes (e.g. default behaviour changes in new credit environment); detect by monitoring Gini, KS statistic, classification metrics on labelled outcomes. Response: alert thresholds → investigation → recalibration or full retraining → validation → re-deployment. Regulatory expectation (SR 11-7): ongoing monitoring with defined thresholds and documented response process.",
        },
        {
            "q": "What does 'responsible AI' mean in a financial services context? How is it different from 'ethical AI'?",
            "a": "Responsible AI in FS is operationally defined: meeting regulatory obligations (EU AI Act, SR 11-7, BCBS 239, RBI FREE-AI), managing model risk, ensuring explainability for regulatory and customer-facing decisions, maintaining human oversight, and preventing discriminatory outcomes. Ethical AI is broader and less defined — it includes societal impact, environmental cost, long-term effects. In a bank: responsible AI is what the risk & compliance function owns and can evidence in an audit; ethical AI is what the board and ESG function speak to. The risk: treating responsible AI as a tick-box exercise and missing the spirit. Bring NIST AI RMF's GOVERN function — culture, accountability, workforce — as the bridge between the two.",
        },
    ],
]

MUST_READS = [
    [
        {"title": "NIST AI RMF 1.0 (official)", "url": "https://nvlpubs.nist.gov/nistpubs/ai/nist.ai.100-1.pdf", "why": "Primary source — 40 pages. Read the GOVERN and MAP functions first."},
        {"title": "BIS BCBS 239 Progress Report (latest)", "url": "https://www.bis.org/bcbs/publ/d559.htm", "why": "See where banks are still failing — these are your interview talking points."},
        {"title": "EU AI Act full text (official)", "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689", "why": "Read Annex III (high-risk categories) and Articles 9-15 (obligations). 2 hours well spent."},
    ],
    [
        {"title": "RBI FREE-AI Report (Aug 2025)", "url": "https://rbidocs.rbi.org.in/rdocs/PublicationReport/Pdfs/FREEAIR130820250A24FF2D4578453F824C72ED9F5D5851.PDF", "why": "Read Chapter 3 (6 pillars) and Chapter 4 (26 recommendations). 90 min."},
        {"title": "OCC/Fed Interagency Model Risk Guidance (2023+)", "url": "https://www.occ.gov/news-issuances/bulletins/2023/bulletin-2023-37.html", "why": "SR 11-7 successor context — what changed and what stayed."},
        {"title": "McKinsey: The State of AI in Financial Services 2025", "url": "https://www.mckinsey.com/industries/financial-services/our-insights", "why": "Good for 'what is the industry actually doing' context questions."},
    ],
    [
        {"title": "ISO/IEC 42001:2023 Overview (BSI)", "url": "https://www.bsigroup.com/en-GB/insights-and-media/insights/brochures/iso-iec-42001/", "why": "Free summary. Understand Annex A controls before you study the full standard."},
        {"title": "NIST AI 600-1: GenAI Profile", "url": "https://airc.nist.gov/Docs/1", "why": "Extends AI RMF for generative AI — 200+ suggested actions. Critical for LLM governance questions."},
        {"title": "Alignment Forum — AI Risk overview", "url": "https://www.alignmentforum.org/tag/ai-risk", "why": "Deeper AI safety reasoning — differentiates you from candidates who only know the regulatory surface."},
    ],
]


# ──────────────────────────────────────────────────────────────────────────
# Helpers (self-contained copy — no import from ai_news_digest)
# ──────────────────────────────────────────────────────────────────────────

def strip_html(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html_lib.unescape(text)
    return " ".join(text.split())


def esc(text):
    return html_lib.escape(text or "", quote=True)


def gnews(query, region="US"):
    locales = {"US": ("en-US","US","US:en"), "IN": ("en-IN","IN","IN:en"), "GB": ("en-GB","GB","GB:en")}
    hl, gl, ceid = locales.get(region, locales["US"])
    return f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl={hl}&gl={gl}&ceid={ceid}"


def split_gnews_title(title):
    if " - " in title:
        head, _, pub = title.rpartition(" - ")
        if head and 0 < len(pub) <= 40 and len(pub.split()) <= 5:
            return head.strip(), pub.strip()
    return title.strip(), None


def fetch_rss(urls_with_meta, max_per=10):
    out = []
    for src in urls_with_meta:
        try:
            d = feedparser.parse(src["url"], agent=UA)
            for e in (d.entries or [])[:max_per]:
                pub = None
                for k in ("published_parsed", "updated_parsed"):
                    if getattr(e, k, None):
                        pub = datetime(*getattr(e, k)[:6], tzinfo=timezone.utc)
                        break
                title = strip_html(e.get("title", "Untitled"))
                publisher = src.get("name")
                summary = ""
                if src.get("is_gnews"):
                    title, gpub = split_gnews_title(title)
                    publisher = gpub or src.get("name", "News")
                else:
                    summary = strip_html(e.get("summary", e.get("description", "")))[:180]
                    if summary:
                        summary += "…"
                out.append({"title": title, "link": e.get("link","#"),
                            "summary": summary, "published": pub,
                            "source": publisher or "News"})
        except Exception as exc:
            print(f"  [WARN] {src.get('name','?')}: {type(exc).__name__}: {str(exc)[:60]}")
    return out


def top_stories(articles, n, seen):
    now = datetime.now(timezone.utc)
    BOOST_KEYS = ("bcbs 239","sr 11-7","model risk","nist ai","eu ai act","ai act",
                  "ai governance","responsible ai","agentic","ai regulation","free-ai",
                  "iso 42001","data quality","risk data","explainability")
    def score(a):
        s = max(0.0, 168.0 - (now - a["published"]).total_seconds()/3600) if a["published"] else 5.0
        if any(k in (a["title"]+a.get("summary","")).lower() for k in BOOST_KEYS):
            s += 80.0
        return s
    ranked = sorted(articles, key=score, reverse=True)
    result, seen_fps = [], set()
    for a in ranked:
        key = re.sub(r"[^a-z0-9]","", a["title"].lower())[:45]
        fp  = " ".join([t for t in re.sub(r"[^a-z0-9\s]","",a["title"].lower()).split()
                        if t not in {"the","a","an","is","are","to","of","in","on","for","and","or","by","at"}][:6])
        if not key or key in seen or fp in seen_fps:
            continue
        seen.add(key); seen_fps.add(fp)
        result.append(a)
        if len(result) >= n:
            break
    return result


def g(query, region="US"):
    return {"name": "Google News", "url": gnews(query, region), "is_gnews": True}


def build_weekly_stories():
    seen = set()
    # Wide net — 7-day window across all domains
    queries = [
        g('("AI risk" OR "AI governance" OR "AI regulation" OR "EU AI Act" OR "BCBS 239" OR "model risk" OR "NIST AI" OR "AI compliance" OR "responsible AI") when:7d'),
        g('(JPMorgan OR "Bank of America" OR "Wells Fargo" OR Citi OR "Morgan Stanley" OR Infosys OR Wipro OR TCS OR HCLTech) ("AI" OR "artificial intelligence") when:7d'),
        g('(Google OR Microsoft OR Meta OR Amazon OR OpenAI OR Anthropic OR "Google DeepMind") ("AI" OR "artificial intelligence" OR "model") when:7d'),
        g('(McKinsey OR BCG OR Deloitte OR Accenture OR Bain) ("AI risk" OR "generative AI" OR "AI governance") when:7d'),
        g('("AI regulation" OR "AI Act" OR "NIST" OR "model risk" OR "data governance" OR "RBI" OR "MAS" OR "FCA") when:7d', region="IN"),
    ]
    arts = fetch_rss(queries, max_per=15)
    return top_stories(arts, 10, seen)


def build_reg_pulse():
    seen = set()
    q = ('(site:bis.org OR site:europa.eu OR site:nist.gov OR site:federalreserve.gov '
         'OR site:occ.gov OR site:oecd.org OR site:eba.europa.eu OR site:fsb.org '
         'OR site:fca.org.uk OR site:rbi.org.in OR site:mas.gov.sg) '
         '("AI" OR "artificial intelligence" OR "model risk" OR "BCBS 239") when:14d')
    arts = fetch_rss([g(q), g('("EU AI Act" OR "NIST AI RMF" OR "SR 11-7" OR "FREE-AI" OR "MAS AI" OR "FCA AI") when:14d')])
    return top_stories(arts, 5, seen)


# ──────────────────────────────────────────────────────────────────────────
# HTML rendering
# ──────────────────────────────────────────────────────────────────────────

def _story_card(idx, art, accent="#6C63FF"):
    pub_str = art["published"].astimezone(IST).strftime("%d %b") if art["published"] else ""
    link, title, source = esc(art["link"]), esc(art["title"]), esc(art["source"])
    summary_row = (f'<tr><td style="padding:0 16px 8px 16px;font-size:12px;color:#555;line-height:1.5;">'
                   f'{esc(art["summary"])}</td></tr>') if art.get("summary") else ""
    return f"""<tr><td style="padding:0 0 10px 0;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
             style="background:#fff;border-radius:6px;border-left:3px solid {accent};
                    box-shadow:0 1px 3px rgba(0,0,0,.06);">
        <tr><td style="padding:10px 16px 4px 16px;">
          <span style="font-size:11px;font-weight:700;color:{accent};text-transform:uppercase;">
            #{idx} &nbsp;·&nbsp; {source} {('· ' + pub_str) if pub_str else ''}</span></td></tr>
        <tr><td style="padding:3px 16px 6px 16px;">
          <a href="{link}" style="font-size:14px;font-weight:700;color:#1a1a2e;text-decoration:none;line-height:1.35;">{title}</a>
        </td></tr>
        {summary_row}
        <tr><td style="padding:0 16px 10px 16px;">
          <a href="{link}" style="font-size:11px;color:{accent};text-decoration:none;font-weight:600;">Read →</a>
        </td></tr>
      </table></td></tr>"""


def _section_wrap(emoji, title, subtitle, accent, cards_html):
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0">
      <tr><td style="padding:4px 0 12px 0;">
        <table cellpadding="0" cellspacing="0" border="0"><tr>
          <td style="background:{accent};width:4px;border-radius:2px;">&nbsp;</td>
          <td style="padding-left:10px;">
            <h2 style="margin:0;font-size:16px;font-weight:800;color:#1a1a2e;">{emoji} {esc(title)}</h2>
            <p style="margin:1px 0 0 0;font-size:11px;color:#888;">{esc(subtitle)}</p>
          </td></tr></table></td></tr>
      {cards_html}
    </table>
    <table width="100%"><tr><td style="padding:4px 0 20px 0;">
      <hr style="border:none;border-top:1px solid #e2e8f0;margin:0;"></td></tr></table>"""


def _framework_block(dive):
    bullets = "".join(f'<li style="margin:0 0 5px 0;font-size:13px;color:#333;line-height:1.5;">{esc(b)}</li>'
                      for b in dive["bullets"])
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0">
      <tr><td style="background:#eef2ff;border:1px solid #c7d2fe;border-radius:8px;padding:18px 20px;">
        <p style="margin:0 0 6px 0;font-size:11px;font-weight:800;color:#4338ca;text-transform:uppercase;letter-spacing:.5px;">📚 Framework Deep Dive</p>
        <p style="margin:0 0 3px 0;font-size:16px;font-weight:800;color:#1a1a2e;">{esc(dive['name'])}</p>
        <p style="margin:0 0 10px 0;font-size:12px;color:#555;font-style:italic;">{esc(dive['tldr'])}</p>
        <ul style="margin:0 0 12px 0;padding-left:18px;">{bullets}</ul>
        <div style="background:#fff;border-radius:6px;padding:12px 14px;border:1px solid #c7d2fe;">
          <p style="margin:0 0 4px 0;font-size:11px;font-weight:700;color:#4338ca;text-transform:uppercase;">Likely Interview Question</p>
          <p style="margin:0 0 6px 0;font-size:13px;font-weight:700;color:#1a1a2e;">{esc(dive['q'])}</p>
          <p style="margin:0;font-size:12px;color:#555;line-height:1.6;"><b>Hint:</b> {esc(dive['hint'])}</p>
        </div>
      </td></tr>
      <tr><td style="height:20px;"></td></tr>
    </table>"""


def _qas_block(qas):
    cards = ""
    for i, qa in enumerate(qas):
        cards += f"""
        <tr><td style="padding:0 0 12px 0;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0"
                 style="background:#fff;border-radius:6px;border-left:3px solid #27AE60;
                        box-shadow:0 1px 3px rgba(0,0,0,.06);">
            <tr><td style="padding:12px 16px 6px 16px;">
              <span style="font-size:11px;font-weight:700;color:#27AE60;text-transform:uppercase;">Q{i+1}</span><br>
              <span style="font-size:14px;font-weight:700;color:#1a1a2e;line-height:1.4;">{esc(qa['q'])}</span>
            </td></tr>
            <tr><td style="padding:4px 16px 12px 16px;font-size:12px;color:#444;line-height:1.7;">{esc(qa['a'])}</td></tr>
          </table>
        </td></tr>"""
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0">
      <tr><td style="padding:4px 0 12px 0;">
        <h2 style="margin:0;font-size:16px;font-weight:800;color:#1a1a2e;">🎯 Interview Q&amp;A Spotlight</h2>
        <p style="margin:1px 0 0 0;font-size:11px;color:#888;">Rotating weekly — 3 real questions with model answers</p>
      </td></tr>
      {cards}
    </table>
    <table width="100%"><tr><td style="padding:4px 0 20px 0;">
      <hr style="border:none;border-top:1px solid #e2e8f0;margin:0;"></td></tr></table>"""


def _must_reads_block(reads):
    cards = ""
    for r in reads:
        cards += f"""<tr><td style="padding:0 0 10px 0;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0"
                 style="background:#fff;border-radius:6px;border-left:3px solid #F2994A;
                        box-shadow:0 1px 3px rgba(0,0,0,.06);padding:12px 16px;">
            <tr><td style="padding:12px 16px 4px 16px;">
              <a href="{esc(r['url'])}" style="font-size:14px;font-weight:700;color:#1a1a2e;text-decoration:none;">{esc(r['title'])}</a>
            </td></tr>
            <tr><td style="padding:2px 16px 10px 16px;font-size:12px;color:#666;font-style:italic;">{esc(r['why'])}</td></tr>
          </table></td></tr>"""
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0">
      <tr><td style="padding:4px 0 12px 0;">
        <h2 style="margin:0;font-size:16px;font-weight:800;color:#1a1a2e;">🔖 Weekend Must-Reads</h2>
        <p style="margin:1px 0 0 0;font-size:11px;color:#888;">3 primary sources worth your weekend time</p>
      </td></tr>{cards}
    </table>"""


def build_html(now_ist, top10, reg5, dive, qas, reads):
    week_str = now_ist.strftime("Week of %d %B %Y")
    top10_cards = "".join(_story_card(i+1, a, "#6C63FF") for i, a in enumerate(top10))
    reg5_cards  = "".join(_story_card(i+1, a, "#E94560") for i, a in enumerate(reg5))

    top10_section = _section_wrap("🏆", "Top 10 Stories of the Week",
                                  "Best across all AI domains — recency + interview relevance ranked",
                                  "#6C63FF", top10_cards)
    reg_section   = _section_wrap("⚖️", "Regulatory Pulse",
                                  "What moved in AI regulation & governance this week",
                                  "#E94560", reg5_cards)

    body = top10_section + reg_section + _framework_block(dive) + _qas_block(qas) + _must_reads_block(reads)

    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="x-apple-disable-message-reformatting"></head>
<body style="margin:0;padding:0;background:#f4f6fb;font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f4f6fb">
<tr><td align="center" style="padding:32px 16px;">
  <table cellpadding="0" cellspacing="0" border="0" style="max-width:660px;width:100%;">
    <tr><td style="background:linear-gradient(135deg,#0f3460 0%,#16213e 60%,#1a1a2e 100%);
               border-radius:12px 12px 0 0;padding:24px 20px;">
      <p style="margin:0 0 4px 0;font-size:12px;color:#F2994A;font-weight:700;letter-spacing:1px;text-transform:uppercase;">
        📋 Weekly Recap &nbsp;·&nbsp; {now_ist.strftime('%I:%M %p IST')}</p>
      <h1 style="margin:0 0 6px 0;font-size:26px;font-weight:800;color:#fff;line-height:1.2;">
        AI &amp; Risk Weekly Briefing</h1>
      <p style="margin:0;font-size:13px;color:#a0aec0;">{week_str} &nbsp;·&nbsp; built for interview prep</p>
    </td></tr>
    <tr><td style="background:#f4f6fb;padding:24px 20px;">{body}</td></tr>
    <tr><td style="background:#1a1a2e;border-radius:0 0 12px 12px;padding:18px 20px;">
      <p style="margin:0;font-size:11px;color:#718096;line-height:1.8;">
        Auto-generated weekly by <strong style="color:#a0aec0;">risk_dq_governance</strong>
        · Delivered <strong style="color:#a0aec0;">Sunday 8:00 PM IST</strong>.<br>
        Framework Deep Dive and Interview Q&amp;As rotate weekly. Sources: Google News + primary
        regulatory documents (BIS, NIST, EU, RBI, OCC, FSB, MAS, FCA).
      </p>
    </td></tr>
  </table>
</td></tr></table></body></html>"""


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────

def main():
    now_ist  = datetime.now(IST)
    week_idx = now_ist.timetuple().tm_yday // 7
    print(f"[{now_ist:%Y-%m-%d %H:%M:%S IST}] Building AI & Risk Weekly Recap…")

    print("  Fetching top 10 weekly stories…")
    top10 = build_weekly_stories()
    print(f"  Got {len(top10)} top stories.")

    print("  Fetching regulatory pulse…")
    reg5 = build_reg_pulse()
    print(f"  Got {len(reg5)} regulatory items.")

    dive  = FRAMEWORK_DEEP_DIVES[week_idx % len(FRAMEWORK_DEEP_DIVES)]
    qas   = INTERVIEW_QAS[week_idx % len(INTERVIEW_QAS)]
    reads = MUST_READS[week_idx % len(MUST_READS)]
    print(f"  Framework: {dive['name']}")

    html = build_html(now_ist, top10, reg5, dive, qas, reads)
    subject = f"[AI & Risk Weekly] {now_ist.strftime('Week of %d %b %Y')}"

    if os.environ.get("PREVIEW_ONLY") == "1":
        with open("weekly_preview.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("  PREVIEW_ONLY: wrote weekly_preview.html")
        return

    smtp_user     = os.environ["GMAIL_USER"]
    smtp_password = os.environ["GMAIL_APP_PASSWORD"]
    to_email      = os.environ.get("TO_EMAIL", "vijayaraj.ks639@gmail.com")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"AI & Risk Weekly <{smtp_user}>"
    msg["To"]      = to_email
    msg.attach(MIMEText("View this email in an HTML-capable client.", "plain"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    ssl_ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl_ctx) as server:
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, [to_email], msg.as_string())

    print(f"  Done — weekly recap sent to {to_email}.")


if __name__ == "__main__":
    main()

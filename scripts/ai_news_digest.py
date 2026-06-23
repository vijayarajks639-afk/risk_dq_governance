#!/usr/bin/env python3
"""
AI News Digest  —  twice-daily briefing (6 AM & 10 PM IST)

Builds a multi-section HTML email tuned for AI risk / governance interview prep:
  • Framework of the Day            (rotating study card: NIST AI RMF, BCBS 239, ...)
  1. AI Around the World
  2. AI Risk, Governance & Regulation  (EU AI Act, NIST AI RMF, ISO 42001, BIS/BCBS 239, OECD)
  3. Financial-Services AI Regulation  (Fed/OCC SR 11-7, RBI FREE-AI, SEBI, MAS, FCA, PRA)
  4. Big Tech & AI                     (Google, Microsoft, Meta, Amazon, Apple)
  5. Consulting & AI                   (McKinsey, BCG, Bain, Deloitte, Accenture)
  6. Indian IT & AI                    (TCS, Infosys, Wipro, HCLTech, Tech Mahindra)
  7. US Banks & AI                     (JPMorgan, BofA, Wells Fargo, Citi, Morgan Stanley)
  8. Social Buzz                       (Reddit + Hacker News)

Engine: Google News RSS search (supports site:/when:) + direct publisher &
        regulator RSS + Hacker News Algolia API.
Ranking: recency + authority (regulator domains) + interview-keyword boost.
Extras: deterministic "Interview angle" notes; optional Claude "Editor's Brief"
        if ANTHROPIC_API_KEY is set.
Delivery: Gmail SMTP (SSL).  Triggered by GitHub Actions.
"""

import os
import re
import json
import ssl
import time
import html as html_lib
import smtplib
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import feedparser
import pytz

IST = pytz.timezone("Asia/Kolkata")
# A plain, current browser UA. Some sources (e.g. Reddit) block custom/bot UAs.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_SSL = ssl.create_default_context()

# Domains treated as authoritative — items from these float to the top of the
# risk/governance sections even if slightly older than a fresh news item.
AUTHORITY_DOMAINS = (
    "bis.org", "europa.eu", "ec.europa.eu", "nist.gov", "federalreserve.gov",
    "occ.gov", "fdic.gov", "oecd.org", "eba.europa.eu", "esma.europa.eu",
    "fsb.org", "bankofengland.co.uk", "fca.org.uk", "rbi.org.in",
    "sebi.gov.in", "mas.gov.sg", "imda.gov.sg", "treasury.gov",
)

# Title keywords that mark an item as high-value for interview prep.
INTERVIEW_KEYWORDS = (
    "bcbs 239", "sr 11-7", "model risk", "nist ai", "ai rmf", "iso 42001",
    "iso/iec 42001", "eu ai act", "ai act", "free-ai", "ai governance",
    "responsible ai", "agentic", "ai regulation", "data governance",
    "data quality", "risk data", "explainability", "gpai", "ai compliance",
)

# Deterministic "Interview angle" notes shown on matching cards (no API needed).
INTERVIEW_ANGLES = [
    ("bcbs 239",   "BCBS 239 — know the 14 principles for risk data aggregation & reporting (governance, accuracy, completeness, timeliness, adaptability)."),
    ("sr 11-7",    "Model risk: SR 11-7 was the US MRM cornerstone (development → validation → governance); it was rescinded/revised in 2026 — be ready to discuss the successor guidance and its genAI scope."),
    ("model risk", "Model risk management — tie to the three lines of defence and independent validation."),
    ("free-ai",    "RBI FREE-AI (2025) — India's framework: 7 Sutras, 6 pillars, 26 recommendations for responsible AI in finance."),
    ("eu ai act",  "EU AI Act — risk tiers (unacceptable/high/limited/minimal); GPAI obligations live, full enforcement Aug 2026."),
    ("ai act",     "EU AI Act — risk-tiered obligations; map use cases to high-risk Annex III."),
    ("nist ai",    "NIST AI RMF — four functions: GOVERN, MAP, MEASURE, MANAGE (+ the GenAI Profile, AI 600-1)."),
    ("ai rmf",     "NIST AI RMF — GOVERN/MAP/MEASURE/MANAGE; maps to ISO 42001 & the EU AI Act."),
    ("iso 42001",  "ISO/IEC 42001 — first certifiable AI management system standard; complements NIST AI RMF."),
    ("agentic",    "Agentic AI risk — autonomy raises new control, accountability & oversight gaps regulators are now targeting."),
    ("data quality","Data quality / governance — the foundation of BCBS 239 and trustworthy AI."),
]

# Rotating study card — one per day, keyed by day-of-year.
FRAMEWORKS = [
    ("NIST AI Risk Management Framework (AI RMF 1.0)",
     "Four core functions: GOVERN, MAP, MEASURE, MANAGE. The GenAI Profile (NIST AI 600-1) adds 200+ actions for generative AI.",
     "Likely Q: 'Walk me through how you'd operationalise the NIST AI RMF for a credit-scoring model.'"),
    ("BCBS 239 — Risk Data Aggregation & Reporting",
     "14 principles across governance & infrastructure, risk-data aggregation, reporting practices, and supervisory review.",
     "Likely Q: 'Which BCBS 239 principles are hardest to evidence, and how do you measure compliance?'"),
    ("EU AI Act",
     "Risk-tiered: unacceptable (banned), high-risk (Annex III, strict obligations), limited (transparency), minimal. GPAI rules + full enforcement in 2026.",
     "Likely Q: 'How would you classify and govern a high-risk AI system under the EU AI Act?'"),
    ("US Model Risk Management (SR 11-7 → 2026 successor)",
     "Model development, implementation & use; validation; governance, policies & controls. 2026 revisions reshaped scope (incl. genAI).",
     "Likely Q: 'How does model validation differ for a traditional scorecard vs. an LLM?'"),
    ("ISO/IEC 42001 — AI Management System",
     "First certifiable AIMS standard: Plan-Do-Check-Act, AI policy, risk & impact assessment, lifecycle controls (Annex A).",
     "Likely Q: 'How does ISO 42001 complement the NIST AI RMF in an enterprise AI governance program?'"),
    ("RBI FREE-AI Framework (India, 2025)",
     "Framework for Responsible & Ethical Enablement of AI: 7 Sutras (guiding principles), 6 pillars, 26 recommendations for the financial sector.",
     "Likely Q: 'What controls would you put around AI in an Indian bank under the RBI FREE-AI guidance?'"),
    ("Data Quality Dimensions & Governance",
     "Accuracy, completeness, consistency, timeliness, validity, uniqueness — the DQ backbone of BCBS 239 and trustworthy AI.",
     "Likely Q: 'How do you measure and monitor data quality feeding a regulatory risk model?'"),
]


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html_lib.unescape(text)
    return " ".join(text.split())


def esc(text: str) -> str:
    """Escape text for safe HTML interpolation."""
    return html_lib.escape(text or "", quote=True)


def domain_of(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return ""


def gnews(query: str, region: str = "US") -> str:
    locales = {
        "US": ("en-US", "US", "US:en"),
        "IN": ("en-IN", "IN", "IN:en"),
        "GB": ("en-GB", "GB", "GB:en"),
    }
    hl, gl, ceid = locales.get(region, locales["US"])
    q = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"


def split_gnews_title(title: str):
    """Google News titles look like 'Headline - Publisher'. Split conservatively."""
    if " - " in title:
        head, _, pub = title.rpartition(" - ")
        # Treat the tail as a publisher only if it's short and word-like.
        if head and 0 < len(pub) <= 40 and len(pub.split()) <= 5:
            return head.strip(), pub.strip()
    return title.strip(), None


def parse_feed(url: str, agent: str = UA):
    """feedparser with a browser UA + bounded retry."""
    last = None
    for attempt in range(3):
        try:
            d = feedparser.parse(url, agent=agent)
            if d.entries:
                return d
            last = d
        except Exception as exc:
            print(f"      retry {attempt+1}: {type(exc).__name__}")
        time.sleep(1.0 * (attempt + 1))
    return last if last is not None else feedparser.parse(url, agent=agent)


def fetch_rss(sources, max_per_feed=10):
    out = []
    for src in sources:
        try:
            d = parse_feed(src["url"], agent=src.get("agent", UA))
            entries = getattr(d, "entries", [])
            if not entries:
                print(f"    [WARN] {src.get('name','?')}: 0 entries (feed empty or blocked)")
            for e in entries[:max_per_feed]:
                pub = None
                for key in ("published_parsed", "updated_parsed"):
                    if getattr(e, key, None):
                        pub = datetime(*getattr(e, key)[:6], tzinfo=timezone.utc)
                        break

                title = strip_html(e.get("title", "Untitled"))
                publisher = src.get("name")
                summary = ""
                if src.get("is_gnews"):
                    title, gpub = split_gnews_title(title)
                    publisher = gpub or src.get("name")
                    # Google News summaries are aggregation markup — skip them.
                else:
                    summary = strip_html(e.get("summary", e.get("description", "")))[:220]
                    if summary:
                        summary += "…"

                out.append({
                    "title": title,
                    "link": e.get("link", "#"),
                    "summary": summary,
                    "published": pub,
                    "source": publisher or "News",
                })
        except Exception as exc:
            print(f"    [WARN] {src.get('name','?')}: {type(exc).__name__}: {str(exc)[:70]}")
    return out


def fetch_hackernews(query='AI OR LLM OR "machine learning" OR "AI governance"',
                     min_points=30, limit=12):
    cutoff = int((datetime.now(timezone.utc) - timedelta(days=2)).timestamp())
    url = ("https://hn.algolia.com/api/v1/search?"
           + urllib.parse.urlencode({
               "query": query, "tags": "story",
               "numericFilters": f"points>{min_points},created_at_i>{cutoff}",
               "hitsPerPage": limit,
           }))
    out = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20, context=_SSL) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
        for hit in data.get("hits", []):
            pub = (datetime.fromtimestamp(hit["created_at_i"], tz=timezone.utc)
                   if hit.get("created_at_i") else None)
            link = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            out.append({
                "title": strip_html(hit.get("title", "Untitled")),
                "link": link,
                "summary": f"▲ {hit.get('points',0)} points · {hit.get('num_comments',0)} comments on Hacker News",
                "published": pub,
                "source": "Hacker News",
            })
    except Exception as exc:
        print(f"    [WARN] Hacker News: {type(exc).__name__}: {str(exc)[:70]}")
    return out


def _score(a, now, authority):
    """Higher = surfaced first."""
    s = 0.0
    if a["published"]:
        age_h = (now - a["published"]).total_seconds() / 3600.0
        s += max(0.0, 120.0 - age_h)          # recency, decays ~1/hour
    else:
        s += 12.0
    title_l = a["title"].lower()
    if any(k in title_l for k in INTERVIEW_KEYWORDS):
        s += 70.0                              # interview-relevant keyword boost
    if authority and any(d in domain_of(a["link"]) for d in AUTHORITY_DOMAINS):
        s += 220.0                             # authoritative regulator/source
    return s


def rank_and_dedupe(articles, n, seen_keys, recency_days=None, authority=False):
    now = datetime.now(timezone.utc)
    for a in articles:
        a["stale"] = bool(recency_days and a["published"]
                          and a["published"] < now - timedelta(days=recency_days))

    # Fresh first, then by score; stale items are kept but clearly demoted/tagged.
    ranked = sorted(articles, key=lambda a: (not a["stale"], _score(a, now, authority)),
                    reverse=True)

    result = []
    for a in ranked:
        key = re.sub(r"[^a-z0-9]", "", a["title"].lower())[:45]
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        result.append(a)
        if len(result) >= n:
            break
    return result


def annotate(art):
    """Return a deterministic 'Interview angle' note if the title matches."""
    t = (art["title"] + " " + art.get("summary", "")).lower()
    for kw, note in INTERVIEW_ANGLES:
        if kw in t:
            return note
    return None


# ──────────────────────────────────────────────────────────────────────────
# Section sources
# ──────────────────────────────────────────────────────────────────────────

DIRECT_AI_FEEDS = [
    {"name": "TechCrunch", "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"name": "VentureBeat", "url": "https://venturebeat.com/category/ai/feed/"},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"},
    {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/feed/"},
    {"name": "Wired", "url": "https://www.wired.com/feed/category/artificial-intelligence/latest/rss"},
]

# Direct regulator/authority feeds — a reliability floor under the risk sections.
REGULATOR_FEEDS = [
    {"name": "US Federal Reserve", "url": "https://www.federalreserve.gov/feeds/press_all.xml"},
    {"name": "OCC", "url": "https://www.occ.gov/rss/occ_news.xml"},
    {"name": "Bank of England", "url": "https://www.bankofengland.co.uk/boeapps/rss/feeds.aspx?feed=News"},
]


def g(query, region="US"):
    return {"name": "Google News", "url": gnews(query, region), "is_gnews": True}


def build_sections():
    seen = set()
    sections = []

    # 1 ── AI Around the World ──
    arts = fetch_rss(DIRECT_AI_FEEDS +
                     [g("artificial intelligence (model OR launch OR breakthrough OR funding) when:3d")])
    sections.append(({
        "emoji": "🌐", "accent": "#6C63FF",
        "title": "Top 5 · AI Around the World",
        "subtitle": "Global breakthroughs, launches, research & funding",
    }, rank_and_dedupe(arts, 5, seen, recency_days=4)))

    # 2 ── AI Risk, Governance & Regulation (global frameworks) ──
    risk_auth = ('(site:bis.org OR site:europa.eu OR site:nist.gov OR site:oecd.org '
                 'OR site:esma.europa.eu OR site:eba.europa.eu OR site:fsb.org) '
                 '(AI OR "artificial intelligence" OR "BCBS 239" OR "risk data") when:30d')
    risk_topic = ('("EU AI Act" OR "NIST AI" OR "AI RMF" OR "ISO 42001" OR "BCBS 239" '
                  'OR "AI governance" OR "responsible AI" OR "AI regulation" '
                  'OR "agentic AI" OR "AI compliance") when:14d')
    arts = fetch_rss([g(risk_auth), g(risk_topic),
                      {"name": "Harvard Business Review", "url": "https://hbr.org/topics/ai/rss"},
                      {"name": "MIT Sloan Mgmt Review", "url": "https://sloanreview.mit.edu/topic/artificial-intelligence/feed/"}])
    sections.append(({
        "emoji": "⚖️", "accent": "#E94560",
        "title": "Top 5 · AI Risk, Governance & Regulation",
        "subtitle": "EU AI Act · NIST AI RMF · ISO 42001 · BIS/BCBS 239 · OECD · FSB",
    }, rank_and_dedupe(arts, 5, seen, recency_days=30, authority=True)))

    # 3 ── Financial-Services AI Regulation (NEW — fills the FS/India gap) ──
    fs_query = ('("model risk" OR "SR 11-7" OR "FREE-AI" OR "AI governance" OR "AI in banking" '
                'OR "AI risk") (RBI OR "Reserve Bank of India" OR SEBI OR MAS OR FCA OR PRA '
                'OR "Federal Reserve" OR OCC OR "model risk management") when:30d')
    arts = (fetch_rss(REGULATOR_FEEDS)
            + fetch_rss([g(fs_query), g(fs_query, region="IN"),
                         g('"FREE-AI" OR "RBI" "artificial intelligence" finance when:45d', region="IN")]))
    sections.append(({
        "emoji": "🏛️", "accent": "#C0392B",
        "title": "Top 5 · Financial-Services AI Regulation",
        "subtitle": "Fed/OCC model risk (SR 11-7) · RBI FREE-AI · SEBI · MAS · FCA · PRA",
    }, rank_and_dedupe(arts, 5, seen, recency_days=45, authority=True)))

    # 4 ── Big Tech & AI ──
    arts = fetch_rss([g('(Google OR Alphabet OR Microsoft OR Meta OR Amazon OR Apple) '
                        '("AI" OR "artificial intelligence" OR "generative AI") when:4d')])
    sections.append(({
        "emoji": "💻", "accent": "#2D9CDB",
        "title": "Top 5 · Big Tech & AI",
        "subtitle": "Google · Microsoft · Meta · Amazon · Apple",
    }, rank_and_dedupe(arts, 5, seen, recency_days=7)))

    # 5 ── Consulting & AI ──
    arts = fetch_rss([g('(McKinsey OR "Boston Consulting Group" OR BCG OR Bain OR Deloitte OR Accenture) '
                        '("AI report" OR "generative AI" OR "AI risk" OR "AI governance" OR "AI adoption") when:10d')])
    sections.append(({
        "emoji": "📊", "accent": "#27AE60",
        "title": "Top 5 · Consulting & AI",
        "subtitle": "McKinsey · BCG · Bain · Deloitte · Accenture",
    }, rank_and_dedupe(arts, 5, seen, recency_days=14)))

    # 6 ── Indian IT & AI ──
    arts = fetch_rss([g('(TCS OR "Tata Consultancy" OR Infosys OR Wipro OR HCLTech OR "HCL Technologies" '
                        'OR "Tech Mahindra") ("AI" OR "generative AI") when:7d', region="IN")])
    sections.append(({
        "emoji": "🇮🇳", "accent": "#F2994A",
        "title": "Top 5 · Indian IT & AI",
        "subtitle": "TCS · Infosys · Wipro · HCLTech · Tech Mahindra",
    }, rank_and_dedupe(arts, 5, seen, recency_days=10)))

    # 7 ── US Banks & AI ──
    arts = fetch_rss([g('(JPMorgan OR "JP Morgan" OR "Bank of America" OR "Wells Fargo" '
                        'OR Citigroup OR Citi OR "Morgan Stanley") '
                        '("AI" OR "artificial intelligence") when:7d')])
    sections.append(({
        "emoji": "🏦", "accent": "#9B51E0",
        "title": "Top 5 · US Banks & AI",
        "subtitle": "JPMorgan · Bank of America · Wells Fargo · Citi · Morgan Stanley",
    }, rank_and_dedupe(arts, 5, seen, recency_days=10)))

    # 8 ── Social Buzz ──
    reddit = [
        {"name": "Reddit r/artificial",
         "url": "https://www.reddit.com/r/artificial/top/.rss?t=day"},
        {"name": "Reddit r/MachineLearning",
         "url": "https://www.reddit.com/r/MachineLearning/top/.rss?t=day"},
    ]
    arts = fetch_rss(reddit, max_per_feed=8) + fetch_hackernews()
    sections.append(({
        "emoji": "💬", "accent": "#EB5757",
        "title": "Top 5 · Social Buzz",
        "subtitle": "Most-discussed on Reddit & Hacker News (X/LinkedIn need paid APIs)",
    }, rank_and_dedupe(arts, 5, seen, recency_days=3)))

    return sections


# ──────────────────────────────────────────────────────────────────────────
# Optional AI Editor's Brief
# ──────────────────────────────────────────────────────────────────────────

def ai_editor_brief(sections):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic
        lines = []
        for meta, arts in sections:
            for a in arts[:3]:
                lines.append(f"- [{meta['title']}] {a['title']} ({a['source']})")
        prompt = ("You are an AI risk & governance analyst. From these headlines, write a "
                  "crisp 3-sentence executive brief for a banking risk leader preparing for "
                  "interviews. Lead with the most important development, then a "
                  "regulatory/governance signal, then one practical implication. No preamble.\n\n"
                  + "\n".join(lines))
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(model="claude-sonnet-4-6", max_tokens=400,
                                     messages=[{"role": "user", "content": prompt}])
        return msg.content[0].text.strip()
    except Exception as exc:
        print(f"  [WARN] Editor's brief skipped: {type(exc).__name__}: {str(exc)[:80]}")
        return None


# ──────────────────────────────────────────────────────────────────────────
# HTML rendering
# ──────────────────────────────────────────────────────────────────────────

def _card(idx, art, accent):
    pub_str = art["published"].astimezone(IST).strftime("%d %b, %I:%M %p IST") if art["published"] else ""
    if art.get("stale"):
        pub_str = (pub_str + " · older") if pub_str else "older"
    link = esc(art["link"])
    title = esc(art["title"])
    source = esc(art["source"])

    rows = ""
    if art.get("summary"):
        rows += (f'<tr><td style="padding:0 20px 8px 20px;font-size:13px;color:#555;'
                 f'line-height:1.6;">{esc(art["summary"])}</td></tr>')
    note = annotate(art)
    if note:
        rows += (f'<tr><td style="padding:0 20px 10px 20px;">'
                 f'<span style="display:inline-block;font-size:12px;color:#7a5c00;'
                 f'background:#fff6d9;border-radius:5px;padding:5px 9px;line-height:1.5;">'
                 f'💡 <b>Interview angle:</b> {esc(note)}</span></td></tr>')
    meta_left = f'<span style="font-size:11px;color:#999;">{esc(pub_str)}</span>&nbsp;&nbsp;' if pub_str else ""

    return f"""
    <tr><td style="padding:0 0 14px 0;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
             style="background:#fff;border-radius:8px;border-left:4px solid {accent};
                    box-shadow:0 1px 4px rgba(0,0,0,.07);">
        <tr><td style="padding:14px 20px 4px 20px;">
          <span style="font-size:11px;font-weight:700;color:{accent};
                       text-transform:uppercase;letter-spacing:.5px;">
            #{idx} &nbsp;·&nbsp; {source}</span>
        </td></tr>
        <tr><td style="padding:4px 20px 8px 20px;">
          <a href="{link}" style="font-size:15px;font-weight:700;color:#1a1a2e;
             text-decoration:none;line-height:1.4;">{title}</a>
        </td></tr>
        {rows}
        <tr><td style="padding:0 20px 12px 20px;">
          {meta_left}
          <a href="{link}" style="font-size:12px;color:{accent};
             text-decoration:none;font-weight:600;">Read more →</a>
        </td></tr>
      </table>
    </td></tr>"""


def _section_html(meta, arts):
    accent = meta["accent"]
    if arts:
        cards = "".join(_card(i + 1, a, accent) for i, a in enumerate(arts))
    else:
        cards = ('<tr><td style="padding:14px 20px;color:#999;font-size:13px;background:#fff;'
                 'border-radius:8px;">No fresh items in this window.</td></tr>')
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0">
      <tr><td style="padding:6px 0 14px 0;">
        <table cellpadding="0" cellspacing="0" border="0"><tr>
          <td style="background:{accent};width:4px;border-radius:2px;">&nbsp;</td>
          <td style="padding-left:12px;">
            <h2 style="margin:0;font-size:17px;font-weight:800;color:#1a1a2e;">
              {meta['emoji']} {meta['title']}</h2>
            <p style="margin:2px 0 0 0;font-size:12px;color:#888;">{meta['subtitle']}</p>
          </td>
        </tr></table>
      </td></tr>
      {cards}
    </table>
    <table width="100%" cellpadding="0" cellspacing="0" border="0">
      <tr><td style="padding:6px 0 22px 0;">
        <hr style="border:none;border-top:1px solid #e2e8f0;margin:0;"></td></tr>
    </table>"""


def _framework_card(now_ist):
    name, what, q = FRAMEWORKS[now_ist.timetuple().tm_yday % len(FRAMEWORKS)]
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0">
      <tr><td style="background:#eef2ff;border:1px solid #c7d2fe;border-radius:8px;padding:16px 20px;">
        <p style="margin:0 0 6px 0;font-size:11px;font-weight:800;color:#4338ca;
                  text-transform:uppercase;letter-spacing:.5px;">📚 Framework of the Day</p>
        <p style="margin:0 0 4px 0;font-size:15px;font-weight:800;color:#1a1a2e;">{esc(name)}</p>
        <p style="margin:0 0 8px 0;font-size:13px;color:#444;line-height:1.6;">{esc(what)}</p>
        <p style="margin:0;font-size:12px;color:#4338ca;line-height:1.6;"><b>{esc(q)}</b></p>
      </td></tr>
      <tr><td style="height:18px;"></td></tr>
    </table>"""


def build_html(sections, now_ist, brief=None):
    period = "Morning" if now_ist.hour < 12 else "Evening"
    date_str = now_ist.strftime("%A, %d %B %Y")
    time_str = now_ist.strftime("%I:%M %p IST")

    brief_block = ""
    if brief:
        brief_block = f"""
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr><td style="background:#fff8e1;border:1px solid #ffe082;border-radius:8px;padding:16px 20px;">
            <p style="margin:0 0 6px 0;font-size:11px;font-weight:800;color:#b8860b;
                      text-transform:uppercase;letter-spacing:.5px;">🧭 Editor's Brief</p>
            <p style="margin:0;font-size:13px;color:#444;line-height:1.7;">{esc(brief)}</p>
          </td></tr>
          <tr><td style="height:18px;"></td></tr>
        </table>"""

    body = brief_block + _framework_card(now_ist) + "".join(_section_html(m, a) for m, a in sections)

    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f6fb;font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f4f6fb">
<tr><td align="center" style="padding:32px 16px;">
  <table width="660" cellpadding="0" cellspacing="0" border="0" style="max-width:660px;width:100%;">
    <tr><td style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 60%,#0f3460 100%);
               border-radius:12px 12px 0 0;padding:32px 36px;">
      <p style="margin:0 0 4px 0;font-size:12px;color:#6C63FF;font-weight:700;
                letter-spacing:1px;text-transform:uppercase;">{period} Digest &nbsp;·&nbsp; {time_str}</p>
      <h1 style="margin:0 0 8px 0;font-size:27px;font-weight:800;color:#fff;line-height:1.2;">
        AI &amp; Risk Daily Briefing</h1>
      <p style="margin:0;font-size:14px;color:#a0aec0;">{date_str} &nbsp;·&nbsp; built for interview prep</p>
    </td></tr>
    <tr><td style="background:#f4f6fb;padding:26px 22px;">{body}</td></tr>
    <tr><td style="background:#1a1a2e;border-radius:0 0 12px 12px;padding:20px 36px;">
      <p style="margin:0;font-size:11px;color:#718096;line-height:1.8;">
        Auto-generated by the <strong style="color:#a0aec0;">risk_dq_governance</strong>
        GitHub workflow · delivered <strong style="color:#a0aec0;">6:00 AM</strong> &amp;
        <strong style="color:#a0aec0;">10:00 PM IST</strong> daily.<br>
        Sources: TechCrunch · VentureBeat · Verge · MIT Tech Review · Wired · HBR · MIT Sloan ·
        Fed · OCC · BoE · BIS/BCBS · EU · NIST · OECD · ESMA/EBA · FSB · RBI · Reddit · Hacker News
        (aggregated via Google News RSS). Ranked by recency + source authority + interview relevance.
      </p>
    </td></tr>
  </table>
</td></tr></table></body></html>"""


# ──────────────────────────────────────────────────────────────────────────
# Email
# ──────────────────────────────────────────────────────────────────────────

def send_email(subject, html, to_email, smtp_user, smtp_password):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"AI & Risk Digest <{smtp_user}>"
    msg["To"] = to_email
    msg.attach(MIMEText("Your AI & Risk daily briefing is best viewed as HTML.", "plain"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=_SSL) as server:
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, [to_email], msg.as_string())


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────

def main():
    now_ist = datetime.now(IST)
    period = "Morning" if now_ist.hour < 12 else "Evening"
    print(f"[{now_ist:%Y-%m-%d %H:%M:%S IST}] Building AI & Risk Digest ({period})…")

    sections = build_sections()
    total = sum(len(a) for _, a in sections)
    for meta, arts in sections:
        print(f"  {meta['title']}: {len(arts)} items")
    print(f"  Total articles: {total}")

    brief = ai_editor_brief(sections)
    if brief:
        print("  Editor's brief generated.")

    html = build_html(sections, now_ist, brief)
    subject = f"[AI & Risk Digest] {period} – {now_ist:%d %b %Y, %I:%M %p IST}"

    if os.environ.get("PREVIEW_ONLY") == "1":
        with open("digest_preview.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("  PREVIEW_ONLY: wrote digest_preview.html (email not sent).")
        return

    smtp_user = os.environ["GMAIL_USER"]
    smtp_password = os.environ["GMAIL_APP_PASSWORD"]
    to_email = os.environ.get("TO_EMAIL", "vijayaraj.ks639@gmail.com")
    print(f"  Sending to {to_email}…")
    send_email(subject, html, to_email, smtp_user, smtp_password)
    print("  Done — email delivered.")


if __name__ == "__main__":
    main()

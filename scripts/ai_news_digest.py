#!/usr/bin/env python3
"""
AI News Digest  —  twice-daily briefing (6 AM & 10 PM IST)

Builds a multi-section HTML email:
  1. AI Around the World
  2. AI Risk, Governance & Regulation  (BCBS 239 / BIS, EU AI Act, NIST, Fed, ...)
  3. Big Tech & AI                     (Google, Microsoft, Meta, Amazon, Apple)
  4. Consulting & AI                   (McKinsey, BCG, Bain, Deloitte, Accenture)
  5. Indian IT & AI                    (TCS, Infosys, Wipro, HCLTech, Tech Mahindra)
  6. US Banks & AI                     (JPMorgan, BofA, Wells Fargo, Citi, Morgan Stanley)
  7. Social Buzz                       (Reddit + Hacker News)

Engine: Google News RSS search (stable, supports site:/when: operators) +
        direct publisher RSS + Hacker News Algolia API.
Optional: if ANTHROPIC_API_KEY is set, a short AI "Editor's Brief" is added.
Delivery: Gmail SMTP (SSL).  Triggered by GitHub Actions.
"""

import os
import re
import json
import ssl
import time
import smtplib
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import feedparser
import pytz

IST = pytz.timezone("Asia/Kolkata")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) AINewsDigest/2.0"
_SSL = ssl.create_default_context()


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#39;", "'")
    return " ".join(text.split())


def gnews(query: str, region: str = "US") -> str:
    """Build a Google News RSS search URL for a free-text query."""
    locales = {
        "US": ("en-US", "US", "US:en"),
        "IN": ("en-IN", "IN", "IN:en"),
        "GB": ("en-GB", "GB", "GB:en"),
    }
    hl, gl, ceid = locales.get(region, locales["US"])
    q = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"


def split_gnews_title(title: str):
    """Google News titles look like 'Headline - Publisher'. Split them."""
    if " - " in title:
        head, _, pub = title.rpartition(" - ")
        if 0 < len(pub) <= 45:
            return head.strip(), pub.strip()
    return title.strip(), None


def parse_feed(url: str):
    """feedparser with a browser-like UA + simple retry."""
    for attempt in range(3):
        try:
            d = feedparser.parse(url, agent=UA)
            if d.entries:
                return d
        except Exception as exc:
            print(f"      retry {attempt+1}: {type(exc).__name__}")
        time.sleep(1.5 * (attempt + 1))
    return feedparser.parse(url, agent=UA)


def fetch_rss(sources, max_per_feed=10, default_source=None):
    """Pull entries from a list of {name,url[,region]} dicts."""
    out = []
    for src in sources:
        try:
            d = parse_feed(src["url"])
            for e in d.entries[:max_per_feed]:
                pub = None
                for key in ("published_parsed", "updated_parsed"):
                    if getattr(e, key, None):
                        pub = datetime(*getattr(e, key)[:6], tzinfo=timezone.utc)
                        break

                title = strip_html(e.get("title", "Untitled"))
                publisher = src.get("name")
                if src.get("is_gnews"):
                    title, gpub = split_gnews_title(title)
                    publisher = gpub or src.get("name")

                summary = strip_html(e.get("summary", e.get("description", "")))[:240]
                if summary and not src.get("is_gnews"):
                    summary += "…"
                if src.get("is_gnews"):
                    summary = ""  # Google News summaries are just markup noise

                out.append({
                    "title": title,
                    "link": e.get("link", "#"),
                    "summary": summary,
                    "published": pub,
                    "source": publisher or default_source or "News",
                })
        except Exception as exc:
            print(f"    [WARN] {src.get('name','?')}: {type(exc).__name__}: {str(exc)[:70]}")
    return out


def fetch_hackernews(query="AI OR LLM OR \"machine learning\"", min_points=40, limit=10):
    """Hacker News front-page-ish stories via the Algolia API (JSON)."""
    cutoff = int((datetime.now(timezone.utc) - timedelta(days=2)).timestamp())
    url = ("https://hn.algolia.com/api/v1/search?"
           + urllib.parse.urlencode({
               "query": query,
               "tags": "story",
               "numericFilters": f"points>{min_points},created_at_i>{cutoff}",
               "hitsPerPage": limit,
           }))
    out = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20, context=_SSL) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
        for hit in data.get("hits", []):
            pub = None
            if hit.get("created_at_i"):
                pub = datetime.fromtimestamp(hit["created_at_i"], tz=timezone.utc)
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


def rank_and_dedupe(articles, n, seen_keys, recency_days=None):
    """Sort newest-first, drop dupes (globally via seen_keys), take top n."""
    if recency_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=recency_days)
        kept = [a for a in articles if (a["published"] is None or a["published"] >= cutoff)]
        articles = kept or articles  # never let a strict filter empty a section

    dated = sorted([a for a in articles if a["published"]],
                   key=lambda x: x["published"], reverse=True)
    undated = [a for a in articles if not a["published"]]

    result = []
    for a in dated + undated:
        key = re.sub(r"[^a-z0-9]", "", a["title"].lower())[:50]
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        result.append(a)
        if len(result) >= n:
            break
    return result


# ──────────────────────────────────────────────────────────────────────────
# Section definitions  (sources reviewed for reliability)
# ──────────────────────────────────────────────────────────────────────────

DIRECT_AI_FEEDS = [
    {"name": "TechCrunch", "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"name": "VentureBeat", "url": "https://venturebeat.com/category/ai/feed/"},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"},
    {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/feed/"},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/technology-lab"},
    {"name": "Wired", "url": "https://www.wired.com/feed/category/artificial-intelligence/latest/rss"},
]


def g(query, region="US"):
    return {"name": "Google News", "url": gnews(query, region), "is_gnews": True}


def build_sections():
    """Return list of (meta, articles) tuples."""
    seen = set()  # global de-dupe across all sections
    sections = []

    # 1 ── AI Around the World ───────────────────────────────────────────────
    src = DIRECT_AI_FEEDS + [g("artificial intelligence (model OR launch OR breakthrough OR funding) when:3d")]
    arts = fetch_rss(src)
    sections.append(({
        "emoji": "🌐", "accent": "#6C63FF",
        "title": "Top 5 · AI Around the World",
        "subtitle": "Global breakthroughs, launches, research & funding",
    }, rank_and_dedupe(arts, 5, seen, recency_days=4)))

    # 2 ── AI Risk, Governance & Regulation ──────────────────────────────────
    risk_authoritative = (
        '(site:bis.org OR site:europa.eu OR site:nist.gov OR site:federalreserve.gov '
        'OR site:occ.gov OR site:oecd.org OR site:eba.europa.eu OR site:esma.europa.eu '
        'OR site:fsb.org OR site:bankofengland.co.uk) '
        '(AI OR "artificial intelligence" OR "model risk" OR "risk data" OR "BCBS 239") when:30d'
    )
    risk_topical = (
        '("AI risk" OR "AI governance" OR "AI regulation" OR "EU AI Act" '
        'OR "BCBS 239" OR "NIST AI" OR "model risk management" OR "responsible AI" '
        'OR "ISO 42001" OR "AI compliance") when:14d'
    )
    src = [
        g(risk_authoritative),
        g(risk_topical),
        {"name": "Harvard Business Review", "url": "https://hbr.org/topics/ai/rss"},
        {"name": "MIT Sloan Management Review", "url": "https://sloanreview.mit.edu/topic/artificial-intelligence/feed/"},
    ]
    arts = fetch_rss(src)
    sections.append(({
        "emoji": "⚖️", "accent": "#E94560",
        "title": "Top 5 · AI Risk, Governance & Regulation",
        "subtitle": "BCBS 239 / BIS · EU AI Act · NIST · Fed/OCC · EBA/ESMA · FSB · OECD",
    }, rank_and_dedupe(arts, 5, seen, recency_days=30)))

    # 3 ── Big Tech & AI ─────────────────────────────────────────────────────
    src = [g('(Google OR Alphabet OR Microsoft OR Meta OR Amazon OR Apple) '
             '("AI" OR "artificial intelligence" OR "generative AI") when:4d')]
    arts = fetch_rss(src)
    sections.append(({
        "emoji": "💻", "accent": "#2D9CDB",
        "title": "Top 5 · Big Tech & AI",
        "subtitle": "Google · Microsoft · Meta · Amazon · Apple",
    }, rank_and_dedupe(arts, 5, seen, recency_days=7)))

    # 4 ── Consulting & AI ───────────────────────────────────────────────────
    src = [g('(McKinsey OR "Boston Consulting Group" OR BCG OR Bain OR Deloitte OR Accenture) '
             '("AI" OR "generative AI" OR "AI risk") when:10d')]
    arts = fetch_rss(src)
    sections.append(({
        "emoji": "📊", "accent": "#27AE60",
        "title": "Top 5 · Consulting & AI",
        "subtitle": "McKinsey · BCG · Bain · Deloitte · Accenture",
    }, rank_and_dedupe(arts, 5, seen, recency_days=14)))

    # 5 ── Indian IT & AI ────────────────────────────────────────────────────
    src = [g('(TCS OR "Tata Consultancy" OR Infosys OR Wipro OR HCLTech OR "HCL Technologies" '
             'OR "Tech Mahindra") ("AI" OR "generative AI") when:7d', region="IN")]
    arts = fetch_rss(src)
    sections.append(({
        "emoji": "🇮🇳", "accent": "#F2994A",
        "title": "Top 5 · Indian IT & AI",
        "subtitle": "TCS · Infosys · Wipro · HCLTech · Tech Mahindra",
    }, rank_and_dedupe(arts, 5, seen, recency_days=10)))

    # 6 ── US Banks & AI ─────────────────────────────────────────────────────
    src = [g('(JPMorgan OR "JP Morgan" OR "Bank of America" OR "Wells Fargo" '
             'OR Citigroup OR Citi OR "Morgan Stanley" OR "Goldman Sachs") '
             '("AI" OR "artificial intelligence") when:7d')]
    arts = fetch_rss(src)
    sections.append(({
        "emoji": "🏦", "accent": "#9B51E0",
        "title": "Top 5 · US Banks & AI",
        "subtitle": "JPMorgan · Bank of America · Wells Fargo · Citi · Morgan Stanley",
    }, rank_and_dedupe(arts, 5, seen, recency_days=10)))

    # 7 ── Social Buzz ───────────────────────────────────────────────────────
    src = [
        {"name": "Reddit r/artificial", "url": "https://www.reddit.com/r/artificial/top/.rss?t=day"},
        {"name": "Reddit r/MachineLearning", "url": "https://www.reddit.com/r/MachineLearning/top/.rss?t=day"},
    ]
    arts = fetch_rss(src, max_per_feed=8) + fetch_hackernews()
    sections.append(({
        "emoji": "💬", "accent": "#EB5757",
        "title": "Top 5 · Social Buzz",
        "subtitle": "Most-discussed on Reddit & Hacker News (X/LinkedIn need paid APIs)",
    }, rank_and_dedupe(arts, 5, seen, recency_days=3)))

    return sections


# ──────────────────────────────────────────────────────────────────────────
# Optional AI Editor's Brief (only if ANTHROPIC_API_KEY is set)
# ──────────────────────────────────────────────────────────────────────────

def ai_editor_brief(sections):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic
        headlines = []
        for meta, arts in sections:
            for a in arts[:3]:
                headlines.append(f"- [{meta['title']}] {a['title']} ({a['source']})")
        prompt = (
            "You are an AI risk & governance analyst. From these headlines, write a "
            "crisp 3-sentence executive brief for a banking risk leader. Lead with the "
            "single most important development, then any regulatory/governance signal, "
            "then one practical implication. No preamble.\n\n" + "\n".join(headlines)
        )
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as exc:
        print(f"  [WARN] Editor's brief skipped: {type(exc).__name__}: {str(exc)[:80]}")
        return None


# ──────────────────────────────────────────────────────────────────────────
# HTML rendering
# ──────────────────────────────────────────────────────────────────────────

def _card(idx, art, accent):
    pub_str = ""
    if art["published"]:
        pub_str = art["published"].astimezone(IST).strftime("%d %b, %I:%M %p IST")
    summary_row = (
        f'<tr><td style="padding:0 20px 8px 20px;font-size:13px;color:#555;line-height:1.6;">'
        f'{art["summary"]}</td></tr>' if art["summary"] else ""
    )
    meta_left = (f'<span style="font-size:11px;color:#999;">{pub_str}</span>&nbsp;&nbsp;'
                 if pub_str else "")
    return f"""
    <tr><td style="padding:0 0 14px 0;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
             style="background:#fff;border-radius:8px;border-left:4px solid {accent};
                    box-shadow:0 1px 4px rgba(0,0,0,.07);">
        <tr><td style="padding:14px 20px 4px 20px;">
          <span style="font-size:11px;font-weight:700;color:{accent};
                       text-transform:uppercase;letter-spacing:.5px;">
            #{idx} &nbsp;·&nbsp; {art['source']}</span>
        </td></tr>
        <tr><td style="padding:4px 20px 8px 20px;">
          <a href="{art['link']}" style="font-size:15px;font-weight:700;color:#1a1a2e;
             text-decoration:none;line-height:1.4;">{art['title']}</a>
        </td></tr>
        {summary_row}
        <tr><td style="padding:0 20px 12px 20px;">
          {meta_left}
          <a href="{art['link']}" style="font-size:12px;color:{accent};
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


def build_html(sections, now_ist, brief=None):
    period = "Morning" if now_ist.hour < 12 else "Evening"
    date_str = now_ist.strftime("%A, %d %B %Y")
    time_str = now_ist.strftime("%I:%M %p IST")

    brief_block = ""
    if brief:
        brief_block = f"""
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr><td style="background:#fff8e1;border:1px solid #ffe082;border-radius:8px;
                         padding:16px 20px;margin-bottom:20px;">
            <p style="margin:0 0 6px 0;font-size:11px;font-weight:800;color:#b8860b;
                      text-transform:uppercase;letter-spacing:.5px;">🧭 Editor's Brief</p>
            <p style="margin:0;font-size:13px;color:#444;line-height:1.7;">{brief}</p>
          </td></tr>
          <tr><td style="height:18px;"></td></tr>
        </table>"""

    body = brief_block + "".join(_section_html(m, a) for m, a in sections)

    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f6fb;font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f4f6fb">
<tr><td align="center" style="padding:32px 16px;">
  <table width="660" cellpadding="0" cellspacing="0" border="0" style="max-width:660px;width:100%;">
    <tr><td style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 60%,#0f3460 100%);
               border-radius:12px 12px 0 0;padding:32px 36px;">
      <p style="margin:0 0 4px 0;font-size:12px;color:#6C63FF;font-weight:700;
                letter-spacing:1px;text-transform:uppercase;">
        {period} Digest &nbsp;·&nbsp; {time_str}</p>
      <h1 style="margin:0 0 8px 0;font-size:27px;font-weight:800;color:#fff;line-height:1.2;">
        AI &amp; Risk Daily Briefing</h1>
      <p style="margin:0;font-size:14px;color:#a0aec0;">{date_str}</p>
    </td></tr>
    <tr><td style="background:#f4f6fb;padding:26px 22px;">{body}</td></tr>
    <tr><td style="background:#1a1a2e;border-radius:0 0 12px 12px;padding:20px 36px;">
      <p style="margin:0;font-size:11px;color:#718096;line-height:1.8;">
        Auto-generated by the <strong style="color:#a0aec0;">risk_dq_governance</strong>
        GitHub workflow · delivered <strong style="color:#a0aec0;">6:00 AM</strong> &amp;
        <strong style="color:#a0aec0;">10:00 PM IST</strong> daily.<br>
        Sources reviewed for reliability: TechCrunch · VentureBeat · The Verge · MIT Tech Review ·
        Ars Technica · Wired · HBR · MIT Sloan · BIS/BCBS · EU · NIST · Fed/OCC · EBA/ESMA ·
        FSB · OECD · Reddit · Hacker News (aggregated via Google News RSS).
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

    smtp_user = os.environ["GMAIL_USER"]
    smtp_password = os.environ["GMAIL_APP_PASSWORD"]
    to_email = os.environ.get("TO_EMAIL", "vijayaraj.ks639@gmail.com")

    # Local dry-run support: PREVIEW_ONLY=1 writes HTML to disk, skips sending.
    if os.environ.get("PREVIEW_ONLY") == "1":
        with open("digest_preview.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("  PREVIEW_ONLY: wrote digest_preview.html (email not sent).")
        return

    print(f"  Sending to {to_email}…")
    send_email(subject, html, to_email, smtp_user, smtp_password)
    print("  Done — email delivered.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
AI News Digest
Fetches top 5 AI world news + top 5 AI risk management news and sends an HTML email.
Triggered by GitHub Actions at 6 AM and 10 PM IST daily.
"""

import os
import smtplib
import feedparser
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import pytz
import re

# ──────────────────────────────────────────────
# RSS Feed Sources
# ──────────────────────────────────────────────

AI_WORLD_FEEDS = [
    {"name": "TechCrunch AI",        "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"name": "VentureBeat AI",       "url": "https://venturebeat.com/category/ai/feed/"},
    {"name": "The Verge AI",         "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"},
    {"name": "MIT Tech Review",      "url": "https://www.technologyreview.com/feed/"},
    {"name": "Wired AI",             "url": "https://www.wired.com/feed/category/artificial-intelligence/latest/rss"},
    {"name": "CNBC Tech",            "url": "https://www.cnbc.com/id/19854910/device/rss/rss.html"},
    {"name": "ZDNet AI",             "url": "https://www.zdnet.com/topic/artificial-intelligence/rss.xml"},
    {"name": "Ars Technica AI",      "url": "https://feeds.arstechnica.com/arstechnica/technology-lab"},
]

AI_RISK_FEEDS = [
    {"name": "Harvard Business Review",  "url": "https://hbr.org/topics/ai/rss"},
    {"name": "McKinsey QuantumBlack",    "url": "https://www.mckinsey.com/capabilities/quantumblack/our-insights/rss"},
    {"name": "World Economic Forum AI",  "url": "https://www.weforum.org/agenda/artificial-intelligence/rss"},
    {"name": "MIT Sloan Management",     "url": "https://sloanreview.mit.edu/topic/artificial-intelligence/feed/"},
    {"name": "ISACA",                    "url": "https://www.isaca.org/rss"},
    {"name": "Deloitte Insights AI",     "url": "https://www2.deloitte.com/us/en/insights/topics/artificial-intelligence.rss.html"},
    {"name": "Gartner Newsroom",         "url": "https://www.gartner.com/en/newsroom/rss"},
    {"name": "Risk.net",                 "url": "https://www.risk.net/rss"},
]


def strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    return " ".join(text.split())


def fetch_articles(feeds: list, max_per_feed: int = 8) -> list:
    """Pull entries from every feed; return a unified sorted list."""
    articles = []
    for feed_info in feeds:
        try:
            parsed = feedparser.parse(feed_info["url"])
            for entry in parsed.entries[:max_per_feed]:
                pub = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

                summary_raw = entry.get("summary", entry.get("description", ""))
                summary = strip_html(summary_raw)[:280]
                if summary:
                    summary += "…"

                articles.append({
                    "title":     strip_html(entry.get("title", "Untitled")),
                    "link":      entry.get("link", "#"),
                    "summary":   summary,
                    "published": pub,
                    "source":    feed_info["name"],
                })
        except Exception as exc:
            print(f"  [WARN] Could not fetch {feed_info['name']}: {exc}")

    # Sort newest-first; undated entries go to the bottom
    dated   = sorted([a for a in articles if a["published"]], key=lambda x: x["published"], reverse=True)
    undated = [a for a in articles if not a["published"]]

    # Deduplicate by title (case-insensitive first 60 chars)
    seen, unique = set(), []
    for art in dated + undated:
        key = art["title"][:60].lower()
        if key not in seen:
            seen.add(key)
            unique.append(art)
    return unique


def top_n(feeds: list, n: int = 5) -> list:
    return fetch_articles(feeds)[:n]


# ──────────────────────────────────────────────
# HTML Email Template
# ──────────────────────────────────────────────

def _article_card(idx: int, art: dict, accent: str) -> str:
    pub_str = ""
    if art["published"]:
        ist = pytz.timezone("Asia/Kolkata")
        pub_ist = art["published"].astimezone(ist)
        pub_str = pub_ist.strftime("%d %b %Y, %I:%M %p IST")

    return f"""
    <tr>
      <td style="padding:0 0 20px 0;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0"
               style="background:#ffffff;border-radius:8px;
                      border-left:4px solid {accent};
                      box-shadow:0 1px 4px rgba(0,0,0,.08);">
          <tr>
            <td style="padding:16px 20px 4px 20px;">
              <span style="font-size:11px;font-weight:700;color:{accent};
                           text-transform:uppercase;letter-spacing:.5px;">
                #{idx} &nbsp;·&nbsp; {art['source']}
              </span>
            </td>
          </tr>
          <tr>
            <td style="padding:4px 20px 8px 20px;">
              <a href="{art['link']}"
                 style="font-size:16px;font-weight:700;color:#1a1a2e;
                        text-decoration:none;line-height:1.4;">
                {art['title']}
              </a>
            </td>
          </tr>
          {'<tr><td style="padding:0 20px 8px 20px;font-size:13px;color:#555;line-height:1.6;">' + art['summary'] + '</td></tr>' if art['summary'] else ''}
          <tr>
            <td style="padding:0 20px 14px 20px;">
              {'<span style="font-size:11px;color:#999;">' + pub_str + '</span>' if pub_str else ''}
              &nbsp;&nbsp;
              <a href="{art['link']}"
                 style="font-size:12px;color:{accent};text-decoration:none;font-weight:600;">
                Read more →
              </a>
            </td>
          </tr>
        </table>
      </td>
    </tr>"""


def build_html(ai_news: list, risk_news: list, now_ist: datetime) -> str:
    period = "Morning" if now_ist.hour < 12 else "Evening"
    date_str = now_ist.strftime("%A, %d %B %Y")
    time_str = now_ist.strftime("%I:%M %p IST")

    ai_cards   = "".join(_article_card(i + 1, a, "#6C63FF") for i, a in enumerate(ai_news))
    risk_cards = "".join(_article_card(i + 1, a, "#E94560") for i, a in enumerate(risk_news))

    no_news = "<tr><td style='padding:16px;color:#999;'>No articles found at this time.</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f6fb;font-family:'Segoe UI',Arial,sans-serif;">

<!-- Wrapper -->
<table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f4f6fb">
<tr><td align="center" style="padding:32px 16px;">

  <!-- Card -->
  <table width="640" cellpadding="0" cellspacing="0" border="0"
         style="max-width:640px;width:100%;">

    <!-- Header -->
    <tr>
      <td style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 60%,#0f3460 100%);
                 border-radius:12px 12px 0 0;padding:32px 36px;">
        <p style="margin:0 0 4px 0;font-size:12px;color:#6C63FF;
                  font-weight:700;letter-spacing:1px;text-transform:uppercase;">
          {period} Digest &nbsp;·&nbsp; {time_str}
        </p>
        <h1 style="margin:0 0 8px 0;font-size:28px;font-weight:800;color:#ffffff;line-height:1.2;">
          AI News Daily Briefing
        </h1>
        <p style="margin:0;font-size:14px;color:#a0aec0;">{date_str}</p>
      </td>
    </tr>

    <!-- Body -->
    <tr>
      <td style="background:#f4f6fb;padding:28px 24px;">

        <!-- Section 1: AI World News -->
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td style="padding:0 0 16px 0;">
              <table cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="background:#6C63FF;width:4px;border-radius:2px;">&nbsp;</td>
                  <td style="padding-left:12px;">
                    <h2 style="margin:0;font-size:18px;font-weight:800;color:#1a1a2e;">
                      🌐 Top 5 AI News Around the World
                    </h2>
                    <p style="margin:2px 0 0 0;font-size:12px;color:#888;">
                      Latest breakthroughs, launches & research
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          {ai_cards if ai_cards else no_news}
        </table>

        <!-- Divider -->
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td style="padding:8px 0 28px 0;">
              <hr style="border:none;border-top:1px solid #e2e8f0;margin:0;">
            </td>
          </tr>
        </table>

        <!-- Section 2: AI Risk Management -->
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td style="padding:0 0 16px 0;">
              <table cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="background:#E94560;width:4px;border-radius:2px;">&nbsp;</td>
                  <td style="padding-left:12px;">
                    <h2 style="margin:0;font-size:18px;font-weight:800;color:#1a1a2e;">
                      ⚠️ Top 5 AI Risk Management Insights
                    </h2>
                    <p style="margin:2px 0 0 0;font-size:12px;color:#888;">
                      Governance, compliance & risk across business domains
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          {risk_cards if risk_cards else no_news}
        </table>

      </td>
    </tr>

    <!-- Footer -->
    <tr>
      <td style="background:#1a1a2e;border-radius:0 0 12px 12px;padding:20px 36px;">
        <p style="margin:0;font-size:11px;color:#718096;line-height:1.8;">
          This digest was auto-generated and delivered via your
          <strong style="color:#a0aec0;">risk_dq_governance</strong> GitHub workflow.<br>
          Schedules: <strong style="color:#a0aec0;">6:00 AM IST</strong> &amp;
          <strong style="color:#a0aec0;">10:00 PM IST</strong> daily.<br>
          Sources: TechCrunch · VentureBeat · The Verge · MIT Tech Review · Wired · HBR · McKinsey · WEF
        </p>
      </td>
    </tr>

  </table>
</td></tr>
</table>
</body>
</html>"""


# ──────────────────────────────────────────────
# Email Sender
# ──────────────────────────────────────────────

def send_email(subject: str, html: str, to_email: str,
               smtp_user: str, smtp_password: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"AI News Digest <{smtp_user}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, [to_email], msg.as_string())


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main() -> None:
    ist     = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.now(ist)
    period  = "Morning" if now_ist.hour < 12 else "Evening"

    print(f"[{now_ist.strftime('%Y-%m-%d %H:%M:%S IST')}] Starting AI News Digest ({period})…")

    print("  Fetching AI world news…")
    ai_news = top_n(AI_WORLD_FEEDS, 5)
    print(f"  Got {len(ai_news)} AI world articles.")

    print("  Fetching AI risk management news…")
    risk_news = top_n(AI_RISK_FEEDS, 5)
    print(f"  Got {len(risk_news)} risk management articles.")

    html    = build_html(ai_news, risk_news, now_ist)
    subject = (f"[AI Digest] {period} Briefing – "
               f"{now_ist.strftime('%d %b %Y, %I:%M %p IST')}")

    smtp_user     = os.environ["GMAIL_USER"]
    smtp_password = os.environ["GMAIL_APP_PASSWORD"]
    to_email      = os.environ.get("TO_EMAIL", "vijayaraj.ks639@gmail.com")

    print(f"  Sending email to {to_email}…")
    send_email(subject, html, to_email, smtp_user, smtp_password)
    print("  Done! Email delivered successfully.")


if __name__ == "__main__":
    main()

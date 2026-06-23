#!/usr/bin/env python3
"""
AI Interview Prep Reminder

Reads reminders.json and sends an email for any reminder that is due today.
Supports three types:
  once    — fires on a specific date (YYYY-MM-DD)
  weekly  — fires on a named weekday (monday … sunday)
  monthly — fires on a day-of-month (1–31)

Triggered daily by GitHub Actions. Also supports workflow_dispatch for
on-demand nudges.
"""

import json
import os
import ssl
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import pytz

IST = pytz.timezone("Asia/Kolkata")

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def load_reminders(path: str = "reminders.json") -> list:
    p = Path(path)
    if not p.exists():
        print(f"  reminders.json not found at {path} — nothing to do.")
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def due_today(reminder: dict, today: datetime) -> bool:
    rtype = reminder.get("type", "").lower()
    if rtype == "once":
        return reminder.get("date") == today.strftime("%Y-%m-%d")
    if rtype == "weekly":
        wd = WEEKDAYS.get(reminder.get("weekday", "").lower())
        return wd is not None and today.weekday() == wd
    if rtype == "monthly":
        return reminder.get("day") == today.day
    return False


def build_html(reminder: dict, today: datetime) -> str:
    title   = reminder.get("title", "Reminder")
    message = reminder.get("message", "")
    date_str = today.strftime("%A, %d %B %Y")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="x-apple-disable-message-reformatting">
<title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#f4f4f8;font-family:Arial,Helvetica,sans-serif;">
<table cellpadding="0" cellspacing="0" border="0" style="width:100%;background:#f4f4f8;">
<tr><td style="padding:24px 8px;">

  <table cellpadding="0" cellspacing="0" border="0"
         style="max-width:600px;margin:0 auto;background:#fff;border-radius:10px;
                box-shadow:0 2px 8px rgba(0,0,0,.10);overflow:hidden;">

    <!-- Header -->
    <tr>
      <td style="background:linear-gradient(135deg,#FF6B35 0%,#F7931E 100%);
                 padding:28px 32px;text-align:center;">
        <div style="font-size:11px;color:rgba(255,255,255,.75);
                    letter-spacing:2px;text-transform:uppercase;margin-bottom:8px;">
          Interview Prep Reminder
        </div>
        <div style="font-size:22px;font-weight:700;color:#fff;line-height:1.3;">
          {title}
        </div>
        <div style="font-size:12px;color:rgba(255,255,255,.8);margin-top:6px;">
          {date_str}
        </div>
      </td>
    </tr>

    <!-- Body -->
    <tr>
      <td style="padding:32px;">
        <p style="font-size:15px;line-height:1.7;color:#333;margin:0 0 16px;">
          {message}
        </p>
        <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
        <p style="font-size:12px;color:#999;margin:0;text-align:center;">
          You are receiving this because it was configured in
          <code>reminders.json</code> in your
          <a href="https://github.com/vijayarajks639-afk/risk_dq_governance"
             style="color:#FF6B35;">risk_dq_governance</a> repo.
        </p>
      </td>
    </tr>

  </table>
</td></tr>
</table>
</body>
</html>"""


def send_reminder(reminder: dict, today: datetime,
                  smtp_user: str, smtp_password: str, to_email: str) -> None:
    title = reminder.get("title", "Reminder")
    subject = f"[Reminder] {title} — {today.strftime('%d %b %Y')}"
    html = build_html(reminder, today)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"AI Prep Reminder <{smtp_user}>"
    msg["To"]      = to_email
    msg.attach(MIMEText("View this reminder in an HTML-capable client.", "plain"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    ssl_ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl_ctx) as server:
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, [to_email], msg.as_string())
    print(f"  Sent: {subject} → {to_email}")


def main() -> None:
    today = datetime.now(IST)
    print(f"Reminder check — {today.strftime('%Y-%m-%d %A')} IST")

    reminders = load_reminders()
    if not reminders:
        return

    smtp_user     = os.environ["GMAIL_USER"]
    smtp_password = os.environ["GMAIL_APP_PASSWORD"]
    to_email      = os.environ.get("TO_EMAIL", "vijayaraj.ks639@gmail.com")

    sent = 0
    for r in reminders:
        if due_today(r, today):
            print(f"  Due: [{r['type']}] {r.get('title')}")
            send_reminder(r, today, smtp_user, smtp_password, to_email)
            sent += 1

    if sent == 0:
        print("  No reminders due today.")
    else:
        print(f"  Done — {sent} reminder(s) sent.")


if __name__ == "__main__":
    main()

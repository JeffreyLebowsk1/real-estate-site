"""Flask API backend for mdilworth.com contact forms.

Endpoints:
  POST /api/lead    - Home page consultation request
  POST /api/contact - Contact page / video page messages

Each submission is:
  1. Saved to a local SQLite database (leads.db)
  2. Emailed to the site owner via SMTP

Run:
  pip install -r requirements.txt
  cp .env.example .env   # then edit with real values
  python app.py
"""

import os
import sqlite3
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Allow requests from the Cloudflare Pages site
CORS(app, origins=[
    "https://mdilworth.com",
    "https://www.mdilworth.com",
    "http://localhost:8080",  # local dev
])

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL", "homes@mdilworth.com")
DB_PATH = os.getenv("DB_PATH", "leads.db")
PORT = int(os.getenv("PORT", "5000"))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        form_type TEXT NOT NULL,
        name TEXT,
        email TEXT,
        phone TEXT,
        interest TEXT,
        location TEXT,
        property_type TEXT,
        price_range TEXT,
        message TEXT,
        source TEXT,
        created_at TEXT NOT NULL
    );
    """)
    conn.close()
    log.info("Database initialised at %s", DB_PATH)


def save_lead(form_type: str, data: dict):
    conn = get_db()
    conn.execute(
        """INSERT INTO leads
           (form_type, name, email, phone, interest, location,
            property_type, price_range, message, source, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            form_type,
            data.get("name"),
            data.get("email"),
            data.get("phone"),
            data.get("interest"),
            data.get("location"),
            data.get("propertyType"),
            data.get("priceRange"),
            data.get("message"),
            data.get("source"),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Email helper
# ---------------------------------------------------------------------------
def send_notification(subject: str, body: str):
    if not SMTP_USER or not SMTP_PASS:
        log.warning("SMTP not configured - skipping email")
        return
    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"] = NOTIFY_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        log.info("Notification sent: %s", subject)
    except Exception as exc:
        log.error("Failed to send email: %s", exc)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/api/lead", methods=["POST"])
def lead():
    data = request.get_json(force=True)
    required = ["name", "email", "interest", "location"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    save_lead("lead", data)

    body = (
        f"New lead from mdilworth.com\n"
        f"{'='*40}\n"
        f"Name:          {data.get('name')}\n"
        f"Email:         {data.get('email')}\n"
        f"Phone:         {data.get('phone', 'N/A')}\n"
        f"Interest:      {data.get('interest')}\n"
        f"Location:      {data.get('location')}\n"
        f"Property type: {data.get('propertyType', 'N/A')}\n"
        f"Price range:   {data.get('priceRange', 'N/A')}\n"
        f"Message:       {data.get('message', 'N/A')}\n"
    )
    send_notification(f"New Lead: {data['name']}", body)
    return jsonify({"ok": True}), 200


@app.route("/api/contact", methods=["POST"])
def contact():
    data = request.get_json(force=True)
    required = ["name", "email"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    save_lead("contact", data)

    body = (
        f"New contact from mdilworth.com\n"
        f"{'='*40}\n"
        f"Name:    {data.get('name')}\n"
        f"Email:   {data.get('email')}\n"
        f"Phone:   {data.get('phone', 'N/A')}\n"
        f"Source:  {data.get('source', 'contact-page')}\n"
        f"Message: {data.get('message', 'N/A')}\n"
    )
    send_notification(f"Contact: {data['name']}", body)
    return jsonify({"ok": True}), 200


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=PORT)

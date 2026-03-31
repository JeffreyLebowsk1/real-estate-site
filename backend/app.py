"""Flask API backend for mdilworth.com.

Public endpoints:
  POST /api/lead    - Homepage consultation request
  POST /api/contact - Contact / video page messages
  GET  /api/health  - Health check

Admin endpoints (all require login):
  GET/POST /admin/login
  GET      /admin/logout
  GET      /admin              - Dashboard
  GET      /admin/leads        - Lead table (filter/search)
  GET      /admin/leads/<id>   - Lead detail with thread + notes
  POST     /admin/leads/<id>/status  - Update status
  POST     /admin/leads/<id>/notes   - Add note
  POST     /admin/leads/<id>/reply   - Email reply (logs outbound message)
  GET      /admin/export.csv   - CSV export of non-spam leads
"""

import os
import hmac as _hmac
import hashlib
import smtplib
import logging
import subprocess
from datetime import datetime, timezone

from flask import Flask, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# App + extensions
# ---------------------------------------------------------------------------
app = Flask(__name__)
SITE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", "sqlite:///leads.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")

db = SQLAlchemy(app)

CORS(app, origins=[
    "https://mdilworth.com",
    "https://www.mdilworth.com",
    "https://homes.mdilworth.com",
    "http://localhost:8081",
])

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SMTP_HOST     = os.getenv("SMTP_HOST") or "smtp.gmail.com"
SMTP_PORT     = int(os.getenv("SMTP_PORT") or "587")
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASS     = os.getenv("SMTP_PASS", "")
NOTIFY_EMAIL  = os.getenv("NOTIFY_EMAIL") or "matt@mdilworth.com"
# FROM_EMAIL / FROM_NAME let you send notifications from a different address
# (e.g. a verified Gmail alias) so Gmail doesn't treat the message as
# self-sent and deduplicate it.  Defaults to SMTP_USER when not set.
FROM_EMAIL    = os.getenv("FROM_EMAIL") or SMTP_USER
FROM_NAME     = os.getenv("FROM_NAME", "")
SPAM_THRESHOLD = float(os.getenv("SPAM_THRESHOLD") or "5")
PORT          = int(os.getenv("PORT") or "5000")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class Lead(db.Model):
    __tablename__ = "leads"

    id            = db.Column(db.Integer, primary_key=True)
    form_type     = db.Column(db.Text, nullable=False)
    name          = db.Column(db.Text)
    email         = db.Column(db.Text)
    phone         = db.Column(db.Text)
    interest      = db.Column(db.Text)
    location      = db.Column(db.Text)
    property_type = db.Column(db.Text)
    price_range   = db.Column(db.Text)
    message       = db.Column(db.Text)
    source        = db.Column(db.Text)
    status        = db.Column(db.Text, nullable=False, default="new")
    spam_score    = db.Column(db.Float, nullable=False, default=0.0)
    created_at    = db.Column(db.DateTime(timezone=True), nullable=False,
                              default=lambda: datetime.now(timezone.utc))

    notes    = db.relationship("Note",    back_populates="lead",
                               cascade="all, delete-orphan", order_by="Note.created_at")
    messages = db.relationship("Message", back_populates="lead",
                               cascade="all, delete-orphan", order_by="Message.sent_at")


class Note(db.Model):
    __tablename__ = "notes"

    id         = db.Column(db.Integer, primary_key=True)
    lead_id    = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False)
    body       = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))

    lead = db.relationship("Lead", back_populates="notes")


class Message(db.Model):
    __tablename__ = "messages"

    id        = db.Column(db.Integer, primary_key=True)
    lead_id   = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False)
    direction = db.Column(db.Text, nullable=False)  # "inbound" | "outbound"
    subject   = db.Column(db.Text)
    body      = db.Column(db.Text)
    sent_at   = db.Column(db.DateTime(timezone=True), nullable=False,
                          default=lambda: datetime.now(timezone.utc))

    lead = db.relationship("Lead", back_populates="messages")


# ---------------------------------------------------------------------------
# Spam scorer
# ---------------------------------------------------------------------------
_SPAM_KEYWORDS = [
    # Marketing / SEO pitches
    ("seo", 2), ("search engine optimiz", 2), ("rank higher", 3),
    ("rank on google", 3), ("digital marketing", 2), ("digital agency", 2),
    ("marketing agency", 2), ("marketing services", 2), ("grow your business", 2),
    ("increase your traffic", 2), ("link building", 3), ("backlinks", 2),
    ("leads for you", 3), ("generate leads", 2), ("i can help you get more", 2),
    ("social media management", 2), ("pay per click", 2), ("google ads", 1),
    # Investor / wholesale pitches
    ("wholesale", 3), ("wholesaler", 3), ("off-market", 2), ("cash offer", 2),
    ("cash buyer", 2), ("joint venture", 3), ("partner with", 2),
    ("referral fee", 3), ("bird dog", 3), ("flip", 1), ("fix and flip", 3),
    ("investment property", 2), ("passive income", 2),
    # Generic spam signals
    ("dear sir", 2), ("dear madam", 2), ("greetings of the day", 3),
    ("i am writing to", 1), ("kindly revert", 3), ("revert back", 2),
    ("please find attached", 2),
]

_FREEMAIL_DOMAINS = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
                     "icloud.com", "protonmail.com", "aol.com"}

def compute_spam_score(data: dict) -> float:
    score = 0.0
    text = " ".join(filter(None, [
        data.get("name", ""),
        data.get("email", ""),
        data.get("message", ""),
        data.get("interest", ""),
        data.get("location", ""),
    ])).lower()

    for keyword, weight in _SPAM_KEYWORDS:
        if keyword in text:
            score += weight

    # No phone number on a lead form is a mild signal
    if not data.get("phone"):
        score += 0.5

    # Very short messages on contact form
    msg = data.get("message", "")
    if msg and len(msg.strip()) < 20:
        score += 1.0

    # Cap at 10
    return min(score, 10.0)


# ---------------------------------------------------------------------------
# Email helper
# ---------------------------------------------------------------------------
def send_email(to: str, subject: str, body: str, reply_to: str = None):
    if not SMTP_USER or not SMTP_PASS:
        log.warning("SMTP not configured — skipping email")
        return
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.utils import formataddr
    msg = MIMEMultipart()
    msg["From"] = formataddr((FROM_NAME.strip(), FROM_EMAIL)) if FROM_NAME.strip() else FROM_EMAIL
    msg["To"] = to
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.attach(MIMEText(body, "plain"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        log.info("Email sent to %s: %s", to, subject)
    except Exception as exc:
        log.error("Failed to send email: %s", exc)


# ---------------------------------------------------------------------------
# Shared lead-saving helper
# ---------------------------------------------------------------------------
def save_lead(form_type: str, data: dict) -> Lead:
    score = compute_spam_score(data)
    status = "spam" if score >= SPAM_THRESHOLD else "new"

    lead = Lead(
        form_type     = form_type,
        name          = data.get("name"),
        email         = data.get("email"),
        phone         = data.get("phone"),
        interest      = data.get("interest"),
        location      = data.get("location"),
        property_type = data.get("propertyType"),
        price_range   = data.get("priceRange"),
        message       = data.get("message"),
        source        = data.get("source"),
        status        = status,
        spam_score    = score,
    )
    db.session.add(lead)
    db.session.flush()   # get lead.id before commit

    # Log inbound message in thread
    db.session.add(Message(
        lead_id   = lead.id,
        direction = "inbound",
        subject   = f"[{form_type}] {data.get('name', 'Unknown')}",
        body      = data.get("message", ""),
    ))

    db.session.commit()
    log.info("Lead saved id=%s status=%s spam_score=%.1f", lead.id, status, score)
    return lead


# ---------------------------------------------------------------------------
# Public API routes
# ---------------------------------------------------------------------------
from flask import request, jsonify

@app.route("/api/lead", methods=["POST"])
def api_lead():
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400
    required = ["name", "email", "interest", "location"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    try:
        lead = save_lead("lead", data)
        if lead.status != "spam":
            body = (
                f"New lead from mdilworth.com\n"
                f"{'='*40}\n"
                f"Name:          {lead.name}\n"
                f"Email:         {lead.email}\n"
                f"Phone:         {lead.phone or 'N/A'}\n"
                f"Interest:      {lead.interest}\n"
                f"Location:      {lead.location}\n"
                f"Property type: {lead.property_type or 'N/A'}\n"
                f"Price range:   {lead.price_range or 'N/A'}\n"
                f"Message:       {lead.message or 'N/A'}\n"
                f"\nView in admin: https://homes.mdilworth.com/admin/leads/{lead.id}"
            )
            send_email(NOTIFY_EMAIL, f"New Lead: {lead.name}", body, reply_to=lead.email)
    except SQLAlchemyError as exc:
        log.error("DB error saving lead in /api/lead: %s", exc)
        # DB save failed — still notify via email so no submission is lost
        body = (
            f"New lead from mdilworth.com (DB save failed)\n"
            f"{'='*40}\n"
            f"Name:          {data.get('name', 'N/A')}\n"
            f"Email:         {data.get('email', 'N/A')}\n"
            f"Phone:         {data.get('phone', 'N/A')}\n"
            f"Interest:      {data.get('interest', 'N/A')}\n"
            f"Location:      {data.get('location', 'N/A')}\n"
            f"Property type: {data.get('propertyType', 'N/A')}\n"
            f"Price range:   {data.get('priceRange', 'N/A')}\n"
            f"Message:       {data.get('message', 'N/A')}\n"
        )
        send_email(NOTIFY_EMAIL, f"New Lead (DB error): {data.get('name', 'Unknown')}", body, reply_to=data.get('email'))

    return jsonify({"ok": True}), 200


@app.route("/api/contact", methods=["POST"])
def api_contact():
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400
    required = ["name", "email"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    try:
        lead = save_lead("contact", data)
        if lead.status != "spam":
            body = (
                f"New contact from mdilworth.com\n"
                f"{'='*40}\n"
                f"Name:    {lead.name}\n"
                f"Email:   {lead.email}\n"
                f"Phone:   {lead.phone or 'N/A'}\n"
                f"Source:  {lead.source or 'contact-page'}\n"
                f"Message: {lead.message or 'N/A'}\n"
                f"\nView in admin: https://homes.mdilworth.com/admin/leads/{lead.id}"
            )
            send_email(NOTIFY_EMAIL, f"Contact: {lead.name}", body, reply_to=lead.email)
    except SQLAlchemyError as exc:
        log.error("DB error saving contact lead in /api/contact: %s", exc)
        # DB save failed — still notify via email so no submission is lost
        body = (
            f"New contact from mdilworth.com (DB save failed)\n"
            f"{'='*40}\n"
            f"Name:    {data.get('name', 'N/A')}\n"
            f"Email:   {data.get('email', 'N/A')}\n"
            f"Phone:   {data.get('phone', 'N/A')}\n"
            f"Source:  {data.get('source', 'contact-page')}\n"
            f"Message: {data.get('message', 'N/A')}\n"
        )
        send_email(NOTIFY_EMAIL, f"Contact (DB error): {data.get('name', 'Unknown')}", body, reply_to=data.get('email'))

    return jsonify({"ok": True}), 200


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
# Deploy webhook — called by GitHub Actions on every push to main
# ---------------------------------------------------------------------------
def _verify_github_signature(payload: bytes, sig_header: str) -> bool:
    """Return True if sig_header is a valid HMAC-SHA256 signature of payload."""
    if not GITHUB_WEBHOOK_SECRET:
        return False
    expected = "sha256=" + _hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return _hmac.compare_digest(expected, sig_header)


@app.route("/webhook/deploy", methods=["POST"])
def webhook_deploy():
    sig = request.headers.get("X-Hub-Signature-256", "")
    body = request.get_data()
    if not _verify_github_signature(body, sig):
        log.warning("Deploy webhook: invalid or missing signature from %s",
                    request.remote_addr)
        return jsonify({"error": "forbidden"}), 403

    # Run the deploy script in the background so a potential service restart
    # (mdilworth-api) does not kill this HTTP response mid-flight.
    deploy_script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "webhook-deploy.sh"
    )
    subprocess.Popen(
        ["sudo", deploy_script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    log.info("Deploy webhook accepted — webhook-deploy.sh started in background")
    return jsonify({"ok": True}), 202


# ---------------------------------------------------------------------------
# Admin blueprint
# ---------------------------------------------------------------------------
from admin import admin_bp
app.register_blueprint(admin_bp)


# ---------------------------------------------------------------------------
# Front-end static routes (served directly by Flask)
# ---------------------------------------------------------------------------
@app.route("/")
def site_index():
    return send_from_directory(SITE_ROOT, "index.html")


@app.route("/<path:filename>")
def site_static(filename: str):
    # Keep API/admin/webhook namespaces reserved for backend routes.
    if filename.startswith("api/") or filename.startswith("admin") or filename.startswith("webhook/"):
        return jsonify({"error": "not found"}), 404

    # Serve front-end assets and pages from the repo root.
    return send_from_directory(SITE_ROOT, filename)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=PORT)

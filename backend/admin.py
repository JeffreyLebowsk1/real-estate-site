"""Admin blueprint for mdilworth.com CRM.

Routes (all under /admin):
  GET/POST /admin/login
  GET      /admin/logout
  GET      /admin              - Dashboard
  GET      /admin/leads        - Lead table (filter + search)
  GET      /admin/leads/<id>   - Lead detail, thread, notes
  POST     /admin/leads/<id>/status  - Update status
  POST     /admin/leads/<id>/notes   - Add note
  POST     /admin/leads/<id>/reply   - Send email reply
  GET      /admin/export.csv   - CSV of all non-spam leads
"""

import csv
import io
import os
from datetime import datetime, timezone, timedelta
from functools import wraps
from urllib.parse import urlparse

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    session, flash, Response,
)
from werkzeug.security import check_password_hash

admin_bp = Blueprint("admin", __name__, url_prefix="/admin",
                     template_folder="templates")

# Status badge colours (Bootstrap)
STATUS_COLORS = {
    "new":        "primary",
    "contacted":  "info",
    "client":     "success",
    "spam":       "danger",
    "archived":   "secondary",
}
ALL_STATUSES = list(STATUS_COLORS.keys())


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin.login", next=request.path))
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------
@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        password_hash = os.getenv("ADMIN_PASSWORD_HASH", "")
        if password_hash and check_password_hash(password_hash, password):
            session["admin_logged_in"] = True
            session.permanent = True
            next_url = request.args.get("next", "")
            # Only allow same-site relative redirects to prevent open-redirect attacks.
            # Reject any URL with a scheme, netloc, or backslash (which some browsers
            # treat as a path separator and could be used to bypass the netloc check).
            parsed = urlparse(next_url)
            if next_url and not parsed.scheme and not parsed.netloc and "\\" not in next_url:
                return redirect(next_url)
            return redirect(url_for("admin.dashboard"))
        error = "Incorrect password."
    return render_template("admin/login.html", error=error)


@admin_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("admin.login"))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@admin_bp.route("/")
@login_required
def dashboard():
    from app import db, Lead

    counts = {}
    for status in ALL_STATUSES:
        counts[status] = Lead.query.filter_by(status=status).count()
    counts["total"] = Lead.query.count()

    # Leads per day for last 14 days (for sparkline)
    now = datetime.now(timezone.utc)
    weekly = []
    for i in range(13, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end   = day_start + timedelta(days=1)
        n = Lead.query.filter(
            Lead.status != "spam",
            Lead.created_at >= day_start,
            Lead.created_at < day_end,
        ).count()
        weekly.append({"date": day_start.strftime("%b %d"), "count": n})

    recent = (Lead.query
              .filter(Lead.status != "spam")
              .order_by(Lead.created_at.desc())
              .limit(5)
              .all())

    return render_template("admin/dashboard.html",
                           counts=counts,
                           weekly=weekly,
                           recent=recent,
                           status_colors=STATUS_COLORS)


# ---------------------------------------------------------------------------
# Lead list
# ---------------------------------------------------------------------------
@admin_bp.route("/leads")
@login_required
def leads():
    from app import db, Lead

    status_filter = request.args.get("status", "")
    search = request.args.get("q", "").strip()
    page = int(request.args.get("page", 1))
    per_page = 25

    query = Lead.query
    if status_filter and status_filter in ALL_STATUSES:
        query = query.filter_by(status=status_filter)
    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(Lead.name.ilike(like), Lead.email.ilike(like),
                   Lead.phone.ilike(like), Lead.message.ilike(like))
        )
    query = query.order_by(Lead.created_at.desc())

    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = max(1, (total + per_page - 1) // per_page)

    return render_template("admin/leads.html",
                           leads=items,
                           page=page,
                           total_pages=total_pages,
                           total=total,
                           status_filter=status_filter,
                           search=search,
                           all_statuses=ALL_STATUSES,
                           status_colors=STATUS_COLORS)


# ---------------------------------------------------------------------------
# Lead detail
# ---------------------------------------------------------------------------
@admin_bp.route("/leads/<int:lead_id>")
@login_required
def lead_detail(lead_id):
    from app import Lead
    lead = Lead.query.get_or_404(lead_id)
    return render_template("admin/lead_detail.html",
                           lead=lead,
                           all_statuses=ALL_STATUSES,
                           status_colors=STATUS_COLORS)


# ---------------------------------------------------------------------------
# Update status
# ---------------------------------------------------------------------------
@admin_bp.route("/leads/<int:lead_id>/status", methods=["POST"])
@login_required
def update_status(lead_id):
    from app import db, Lead
    lead = Lead.query.get_or_404(lead_id)
    new_status = request.form.get("status", "")
    if new_status in ALL_STATUSES:
        lead.status = new_status
        db.session.commit()
        flash(f"Status updated to '{new_status}'.", "success")
    else:
        flash("Invalid status.", "danger")
    return redirect(url_for("admin.lead_detail", lead_id=lead_id))


# ---------------------------------------------------------------------------
# Add note
# ---------------------------------------------------------------------------
@admin_bp.route("/leads/<int:lead_id>/notes", methods=["POST"])
@login_required
def add_note(lead_id):
    from app import db, Lead, Note
    lead = Lead.query.get_or_404(lead_id)
    body = request.form.get("body", "").strip()
    if body:
        db.session.add(Note(lead_id=lead.id, body=body))
        db.session.commit()
        flash("Note added.", "success")
    return redirect(url_for("admin.lead_detail", lead_id=lead_id))


# ---------------------------------------------------------------------------
# Email reply
# ---------------------------------------------------------------------------
@admin_bp.route("/leads/<int:lead_id>/reply", methods=["POST"])
@login_required
def reply(lead_id):
    from app import db, Lead, Message, send_email, SMTP_USER
    lead = Lead.query.get_or_404(lead_id)

    subject = request.form.get("subject", "").strip()
    body    = request.form.get("body", "").strip()

    if not subject or not body:
        flash("Subject and body are required.", "danger")
        return redirect(url_for("admin.lead_detail", lead_id=lead_id))

    if not lead.email:
        flash("This lead has no email address.", "danger")
        return redirect(url_for("admin.lead_detail", lead_id=lead_id))

    send_email(lead.email, subject, body)

    db.session.add(Message(
        lead_id   = lead.id,
        direction = "outbound",
        subject   = subject,
        body      = body,
    ))

    # Auto-advance status new → contacted
    if lead.status == "new":
        lead.status = "contacted"

    db.session.commit()
    flash(f"Reply sent to {lead.email}.", "success")
    return redirect(url_for("admin.lead_detail", lead_id=lead_id))


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------
@admin_bp.route("/export.csv")
@login_required
def export_csv():
    from app import Lead

    leads = (Lead.query
             .filter(Lead.status != "spam")
             .order_by(Lead.created_at.desc())
             .all())

    fields = ["id", "form_type", "status", "name", "email", "phone",
              "interest", "location", "property_type", "price_range",
              "message", "source", "spam_score", "created_at"]

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for lead in leads:
        writer.writerow({f: getattr(lead, f, "") for f in fields})

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )

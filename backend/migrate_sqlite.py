#!/usr/bin/env python3
"""One-shot migration: SQLite leads.db → PostgreSQL.

Usage:
  cd /opt/real-estate-site/backend
  source venv/bin/activate
  python3 migrate_sqlite.py

Set DATABASE_URL and DB_PATH in .env (or export them) before running.
The script is idempotent: rows already in Postgres are skipped.
"""

import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "leads.db")

# Import app after load_dotenv so DATABASE_URL is set
from app import app, db, Lead, Message  # noqa: E402

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"SQLite file not found: {DB_PATH}. Nothing to migrate.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM leads ORDER BY id").fetchall()
    conn.close()
    print(f"Found {len(rows)} row(s) in SQLite.")

    with app.app_context():
        db.create_all()
        migrated = 0
        skipped  = 0
        for row in rows:
            if Lead.query.get(row["id"]):
                skipped += 1
                continue

            lead = Lead(
                id            = row["id"],
                form_type     = row["form_type"] or "unknown",
                name          = row["name"],
                email         = row["email"],
                phone         = row["phone"],
                interest      = row["interest"],
                location      = row["location"],
                property_type = row["property_type"],
                price_range   = row["price_range"],
                message       = row["message"],
                source        = row["source"],
                status        = "new",
                spam_score    = 0.0,
                created_at    = row["created_at"],
            )
            db.session.add(lead)

            # Log original message as inbound thread entry
            if row["message"]:
                db.session.add(Message(
                    lead_id   = row["id"],
                    direction = "inbound",
                    subject   = f"[{row['form_type']}] {row['name'] or 'Unknown'}",
                    body      = row["message"],
                    sent_at   = row["created_at"],
                ))

            migrated += 1

        db.session.commit()
        print(f"Migrated: {migrated}  Skipped (already existed): {skipped}")


if __name__ == "__main__":
    migrate()

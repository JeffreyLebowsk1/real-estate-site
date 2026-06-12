"""Tests for the admin CRM blueprint."""

import json
import pytest


class TestAdminAuth:
    """Authentication and session management."""

    def test_unauthenticated_redirect_to_login(self, client):
        resp = client.get("/admin/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]

    def test_leads_requires_auth(self, client):
        resp = client.get("/admin/leads", follow_redirects=False)
        assert resp.status_code == 302

    def test_login_page_renders(self, client):
        resp = client.get("/admin/login")
        assert resp.status_code == 200
        assert b"password" in resp.data.lower()

    def test_login_wrong_password(self, client, app):
        import os
        from werkzeug.security import generate_password_hash
        os.environ["ADMIN_PASSWORD_HASH"] = generate_password_hash("correctpassword")

        resp = client.post("/admin/login",
                           data={"password": "wrongpassword"},
                           follow_redirects=True)
        assert b"Incorrect password" in resp.data

    def test_login_correct_password(self, client, app):
        import os
        from werkzeug.security import generate_password_hash
        os.environ["ADMIN_PASSWORD_HASH"] = generate_password_hash("correctpassword")

        resp = client.post("/admin/login",
                           data={"password": "correctpassword"},
                           follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin" in resp.headers["Location"]

    def test_logout_clears_session(self, admin_client):
        resp = admin_client.get("/admin/logout", follow_redirects=False)
        assert resp.status_code == 302
        # After logout, dashboard should redirect to login
        resp2 = admin_client.get("/admin/", follow_redirects=False)
        assert resp2.status_code == 302
        assert "/admin/login" in resp2.headers["Location"]

    def test_open_redirect_prevention(self, client, app):
        """Login should not redirect to external URLs."""
        import os
        from werkzeug.security import generate_password_hash
        os.environ["ADMIN_PASSWORD_HASH"] = generate_password_hash("pw")

        # Attempt open redirect via next parameter
        resp = client.post("/admin/login?next=https://evil.com",
                           data={"password": "pw"},
                           follow_redirects=False)
        loc = resp.headers.get("Location", "")
        assert "evil.com" not in loc

    def test_open_redirect_backslash_prevention(self, client, app):
        """Backslash-based open redirect should be blocked."""
        import os
        from werkzeug.security import generate_password_hash
        os.environ["ADMIN_PASSWORD_HASH"] = generate_password_hash("pw")

        resp = client.post("/admin/login?next=\\\\evil.com",
                           data={"password": "pw"},
                           follow_redirects=False)
        loc = resp.headers.get("Location", "")
        assert "evil.com" not in loc


class TestAdminDashboard:
    """Dashboard route."""

    def test_dashboard_renders(self, admin_client):
        resp = admin_client.get("/admin/")
        assert resp.status_code == 200
        assert b"Dashboard" in resp.data

    def test_dashboard_shows_stats(self, admin_client, app):
        # Add a test lead
        from app import db, Lead
        lead = Lead(form_type="lead", name="Test", email="t@t.com",
                    status="new", spam_score=0.0)
        db.session.add(lead)
        db.session.commit()

        resp = admin_client.get("/admin/")
        assert resp.status_code == 200
        assert b"Total Leads" in resp.data


class TestAdminLeads:
    """Lead listing and detail routes."""

    def _create_lead(self, app, **kwargs):
        from app import db, Lead
        defaults = dict(form_type="lead", name="Test User",
                        email="test@example.com", status="new", spam_score=0.0)
        defaults.update(kwargs)
        lead = Lead(**defaults)
        db.session.add(lead)
        db.session.commit()
        return lead

    def test_leads_list_renders(self, admin_client, app):
        self._create_lead(app)
        resp = admin_client.get("/admin/leads")
        assert resp.status_code == 200
        assert b"Test User" in resp.data

    def test_leads_filter_by_status(self, admin_client, app):
        self._create_lead(app, name="NewLead", status="new")
        self._create_lead(app, name="SpamLead", status="spam")

        resp = admin_client.get("/admin/leads?status=new")
        assert b"NewLead" in resp.data
        assert b"SpamLead" not in resp.data

    def test_leads_search(self, admin_client, app):
        self._create_lead(app, name="Alice Wonder", email="alice@example.com")
        self._create_lead(app, name="Bob Builder", email="bob@example.com")

        resp = admin_client.get("/admin/leads?q=alice")
        assert b"Alice Wonder" in resp.data
        assert b"Bob Builder" not in resp.data

    def test_lead_detail_renders(self, admin_client, app):
        lead = self._create_lead(app, name="Detail Test")
        resp = admin_client.get(f"/admin/leads/{lead.id}")
        assert resp.status_code == 200
        assert b"Detail Test" in resp.data

    def test_lead_detail_404(self, admin_client):
        resp = admin_client.get("/admin/leads/99999")
        assert resp.status_code == 404

    def test_update_status(self, admin_client, app):
        lead = self._create_lead(app, status="new")
        resp = admin_client.post(f"/admin/leads/{lead.id}/status",
                                  data={"status": "contacted"},
                                  follow_redirects=True)
        assert resp.status_code == 200
        from app import db, Lead
        updated = db.session.get(Lead, lead.id)
        assert updated.status == "contacted"

    def test_update_status_invalid(self, admin_client, app):
        lead = self._create_lead(app, status="new")
        resp = admin_client.post(f"/admin/leads/{lead.id}/status",
                                  data={"status": "invalid_status"},
                                  follow_redirects=True)
        from app import db, Lead
        updated = db.session.get(Lead, lead.id)
        assert updated.status == "new"  # unchanged

    def test_add_note(self, admin_client, app):
        lead = self._create_lead(app)
        resp = admin_client.post(f"/admin/leads/{lead.id}/notes",
                                  data={"body": "Follow up next week"},
                                  follow_redirects=True)
        assert resp.status_code == 200
        from app import Note
        note = Note.query.first()
        assert note is not None
        assert note.body == "Follow up next week"
        assert note.lead_id == lead.id

    def test_add_empty_note_ignored(self, admin_client, app):
        lead = self._create_lead(app)
        admin_client.post(f"/admin/leads/{lead.id}/notes",
                          data={"body": ""},
                          follow_redirects=True)
        from app import Note
        assert Note.query.count() == 0

    def test_csv_export(self, admin_client, app):
        self._create_lead(app, name="Export Me", status="new")
        self._create_lead(app, name="Spam Skip", status="spam")

        resp = admin_client.get("/admin/export.csv")
        assert resp.status_code == 200
        assert resp.content_type == "text/csv; charset=utf-8"
        csv_text = resp.data.decode("utf-8")
        assert "Export Me" in csv_text
        assert "Spam Skip" not in csv_text

    def test_csv_export_has_header(self, admin_client, app):
        resp = admin_client.get("/admin/export.csv")
        csv_text = resp.data.decode("utf-8")
        assert "id,form_type,status,name,email" in csv_text


class TestAdminReply:
    """Email reply functionality."""

    def _create_lead(self, app, **kwargs):
        from app import db, Lead
        defaults = dict(form_type="lead", name="Reply Test",
                        email="reply@example.com", status="new", spam_score=0.0)
        defaults.update(kwargs)
        lead = Lead(**defaults)
        db.session.add(lead)
        db.session.commit()
        return lead

    def test_reply_missing_subject(self, admin_client, app):
        lead = self._create_lead(app)
        resp = admin_client.post(f"/admin/leads/{lead.id}/reply",
                                  data={"subject": "", "body": "hello"},
                                  follow_redirects=True)
        assert b"required" in resp.data.lower()

    def test_reply_missing_body(self, admin_client, app):
        lead = self._create_lead(app)
        resp = admin_client.post(f"/admin/leads/{lead.id}/reply",
                                  data={"subject": "Re: test", "body": ""},
                                  follow_redirects=True)
        assert b"required" in resp.data.lower()

    def test_reply_no_email_on_lead(self, admin_client, app):
        lead = self._create_lead(app, email=None)
        resp = admin_client.post(f"/admin/leads/{lead.id}/reply",
                                  data={"subject": "Re: hi", "body": "Hello"},
                                  follow_redirects=True)
        assert b"no email" in resp.data.lower()

    def test_reply_creates_outbound_message(self, admin_client, app):
        lead = self._create_lead(app)
        admin_client.post(f"/admin/leads/{lead.id}/reply",
                          data={"subject": "Re: inquiry", "body": "Thanks for reaching out!"},
                          follow_redirects=True)
        from app import Message
        msg = Message.query.filter_by(direction="outbound").first()
        assert msg is not None
        assert msg.subject == "Re: inquiry"
        assert msg.body == "Thanks for reaching out!"

    def test_reply_auto_advances_status(self, admin_client, app):
        lead = self._create_lead(app, status="new")
        admin_client.post(f"/admin/leads/{lead.id}/reply",
                          data={"subject": "Re: test", "body": "body text"},
                          follow_redirects=True)
        from app import db, Lead
        updated = db.session.get(Lead, lead.id)
        assert updated.status == "contacted"


class TestLoginBruteForce:
    """Brute-force protection on admin login."""

    def test_lockout_after_max_attempts(self, client, app):
        import os
        from werkzeug.security import generate_password_hash
        os.environ["ADMIN_PASSWORD_HASH"] = generate_password_hash("correct")

        for _ in range(5):
            client.post("/admin/login", data={"password": "wrong"})

        # 6th attempt should be locked out even with correct password
        resp = client.post("/admin/login",
                           data={"password": "correct"},
                           follow_redirects=True)
        assert b"Too many attempts" in resp.data

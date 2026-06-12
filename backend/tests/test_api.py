"""Tests for public API endpoints: /api/lead, /api/contact, /api/health."""

import json
import pytest


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.get_json() == {"status": "ok"}

    def test_health_only_allows_get(self, client):
        resp = client.post("/api/health")
        assert resp.status_code == 405


class TestLeadEndpoint:
    """Tests for POST /api/lead."""

    VALID_LEAD = {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "phone": "919-555-1234",
        "interest": "buying",
        "location": "Sanford, NC",
        "propertyType": "house",
        "priceRange": "$200k-$400k",
        "message": "Looking for a 3BR house near downtown.",
    }

    def test_valid_lead_returns_200(self, client):
        resp = client.post("/api/lead",
                           data=json.dumps(self.VALID_LEAD),
                           content_type="application/json")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_lead_persisted_to_db(self, client, app):
        client.post("/api/lead",
                     data=json.dumps(self.VALID_LEAD),
                     content_type="application/json")
        from app import Lead
        lead = Lead.query.first()
        assert lead is not None
        assert lead.name == "Jane Doe"
        assert lead.email == "jane@example.com"
        assert lead.form_type == "lead"
        assert lead.interest == "buying"
        assert lead.location == "Sanford, NC"

    def test_inbound_message_logged(self, client, app):
        client.post("/api/lead",
                     data=json.dumps(self.VALID_LEAD),
                     content_type="application/json")
        from app import Message
        msg = Message.query.first()
        assert msg is not None
        assert msg.direction == "inbound"
        assert "Jane Doe" in msg.subject

    def test_missing_name_returns_400(self, client):
        data = {**self.VALID_LEAD}
        del data["name"]
        resp = client.post("/api/lead",
                           data=json.dumps(data),
                           content_type="application/json")
        assert resp.status_code == 400
        assert "name" in resp.get_json()["error"].lower()

    def test_missing_email_returns_400(self, client):
        data = {**self.VALID_LEAD}
        del data["email"]
        resp = client.post("/api/lead",
                           data=json.dumps(data),
                           content_type="application/json")
        assert resp.status_code == 400

    def test_missing_interest_returns_400(self, client):
        data = {**self.VALID_LEAD}
        del data["interest"]
        resp = client.post("/api/lead",
                           data=json.dumps(data),
                           content_type="application/json")
        assert resp.status_code == 400

    def test_missing_location_returns_400(self, client):
        data = {**self.VALID_LEAD}
        del data["location"]
        resp = client.post("/api/lead",
                           data=json.dumps(data),
                           content_type="application/json")
        assert resp.status_code == 400

    def test_empty_body_returns_400(self, client):
        resp = client.post("/api/lead",
                           data="",
                           content_type="application/json")
        # silent=True in get_json returns None for unparseable body → 400
        assert resp.status_code == 400

    def test_non_json_content_type_returns_400(self, client):
        resp = client.post("/api/lead",
                           data="not json",
                           content_type="text/plain")
        assert resp.status_code == 400

    def test_minimal_valid_lead(self, client):
        """Only required fields, no optional ones."""
        data = {
            "name": "Bob",
            "email": "bob@example.com",
            "interest": "selling",
            "location": "Spring Lake",
        }
        resp = client.post("/api/lead",
                           data=json.dumps(data),
                           content_type="application/json")
        assert resp.status_code == 200

    def test_spam_lead_gets_spam_status(self, client, app):
        """A lead with enough spam keywords should be marked as spam."""
        data = {
            **self.VALID_LEAD,
            "message": (
                "I am a digital marketing agency offering SEO services. "
                "We can help you rank higher on Google with link building "
                "and backlinks. Generate leads for you!"
            ),
        }
        resp = client.post("/api/lead",
                           data=json.dumps(data),
                           content_type="application/json")
        assert resp.status_code == 200
        from app import Lead
        lead = Lead.query.first()
        assert lead.status == "spam"
        assert lead.spam_score >= 5.0

    def test_legitimate_lead_not_spam(self, client, app):
        resp = client.post("/api/lead",
                           data=json.dumps(self.VALID_LEAD),
                           content_type="application/json")
        assert resp.status_code == 200
        from app import Lead
        lead = Lead.query.first()
        assert lead.status == "new"
        assert lead.spam_score < 5.0


class TestContactEndpoint:
    """Tests for POST /api/contact."""

    VALID_CONTACT = {
        "name": "John Smith",
        "email": "john@example.com",
        "phone": "919-555-9876",
        "message": "I have a question about listing my property for sale.",
    }

    def test_valid_contact_returns_200(self, client):
        resp = client.post("/api/contact",
                           data=json.dumps(self.VALID_CONTACT),
                           content_type="application/json")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_contact_persisted(self, client, app):
        client.post("/api/contact",
                     data=json.dumps(self.VALID_CONTACT),
                     content_type="application/json")
        from app import Lead
        lead = Lead.query.first()
        assert lead is not None
        assert lead.form_type == "contact"
        assert lead.name == "John Smith"

    def test_missing_name_returns_400(self, client):
        data = {"email": "a@b.com", "message": "hi"}
        resp = client.post("/api/contact",
                           data=json.dumps(data),
                           content_type="application/json")
        assert resp.status_code == 400

    def test_missing_email_returns_400(self, client):
        data = {"name": "Jo", "message": "hi"}
        resp = client.post("/api/contact",
                           data=json.dumps(data),
                           content_type="application/json")
        assert resp.status_code == 400

    def test_contact_without_message_still_works(self, client):
        """Message is not required for /api/contact (video form omits it)."""
        data = {"name": "Sue", "email": "sue@example.com"}
        resp = client.post("/api/contact",
                           data=json.dumps(data),
                           content_type="application/json")
        assert resp.status_code == 200

    def test_contact_with_source_field(self, client, app):
        data = {**self.VALID_CONTACT, "source": "video-page"}
        client.post("/api/contact",
                     data=json.dumps(data),
                     content_type="application/json")
        from app import Lead
        lead = Lead.query.first()
        assert lead.source == "video-page"

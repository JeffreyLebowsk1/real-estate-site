"""Tests for the spam scoring system."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import compute_spam_score


class TestSpamScorer:

    def test_clean_lead_low_score(self):
        data = {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "919-555-1234",
            "interest": "buying",
            "location": "Sanford",
            "message": "I'm looking for a 3-bedroom house in the Sanford area.",
        }
        score = compute_spam_score(data)
        assert score < 3.0, f"Clean lead should score low, got {score}"

    def test_seo_pitch_high_score(self):
        data = {
            "name": "SEO Pro",
            "email": "seo@agency.com",
            "message": (
                "I can help you rank higher on Google with SEO, "
                "link building, and digital marketing services."
            ),
        }
        score = compute_spam_score(data)
        assert score >= 5.0, f"SEO spam should score >= 5, got {score}"

    def test_wholesale_pitch_high_score(self):
        data = {
            "name": "Cash Buyer",
            "email": "investor@deals.com",
            "message": (
                "I am a wholesale cash buyer looking for off-market "
                "investment property. Joint venture referral fee."
            ),
        }
        score = compute_spam_score(data)
        assert score >= 5.0, f"Wholesale spam should score >= 5, got {score}"

    def test_no_phone_adds_half_point(self):
        with_phone = {"name": "A", "email": "a@b.com", "phone": "555-1234", "message": "Hello there, I am interested in a house."}
        without_phone = {"name": "A", "email": "a@b.com", "message": "Hello there, I am interested in a house."}
        score_with = compute_spam_score(with_phone)
        score_without = compute_spam_score(without_phone)
        assert score_without - score_with == pytest.approx(0.5)

    def test_short_message_adds_point(self):
        normal = {"name": "A", "email": "a@b.com", "phone": "555", "message": "This is a reasonably long message about buying."}
        short = {"name": "A", "email": "a@b.com", "phone": "555", "message": "hi"}
        score_normal = compute_spam_score(normal)
        score_short = compute_spam_score(short)
        assert score_short > score_normal

    def test_score_capped_at_10(self):
        data = {
            "name": "SEO digital marketing agency",
            "email": "spam@spam.com",
            "message": (
                "rank higher google seo digital marketing link building "
                "backlinks wholesale cash buyer off-market joint venture "
                "referral fee bird dog fix and flip investment property "
                "passive income dear sir greetings of the day kindly revert"
            ),
        }
        score = compute_spam_score(data)
        assert score == 10.0

    def test_empty_data_no_crash(self):
        score = compute_spam_score({})
        assert isinstance(score, float)
        assert score >= 0.0

    def test_none_values_handled(self):
        data = {"name": None, "email": None, "phone": None, "message": None}
        score = compute_spam_score(data)
        assert isinstance(score, float)

    def test_keywords_case_insensitive(self):
        data = {"name": "A", "email": "a@b.com", "phone": "555",
                "message": "I offer SEO and DIGITAL MARKETING services to RANK HIGHER"}
        score = compute_spam_score(data)
        assert score >= 5.0

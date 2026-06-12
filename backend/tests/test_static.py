"""Tests for static file serving and front-end routes."""

import pytest


class TestStaticRoutes:

    def test_index_serves(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Matt Dilworth" in resp.data

    def test_html_pages_serve(self, client):
        pages = [
            "/about.html",
            "/contact.html",
            "/services.html",
            "/find-a-home.html",
            "/list-with-us.html",
            "/testimonials.html",
            "/blog.html",
            "/videos.html",
        ]
        for page in pages:
            resp = client.get(page)
            assert resp.status_code == 200, f"{page} returned {resp.status_code}"

    def test_css_serves(self, client):
        resp = client.get("/css/style.css")
        assert resp.status_code == 200
        assert b"--primary" in resp.data

    def test_js_serves(self, client):
        resp = client.get("/js/components.js")
        assert resp.status_code == 200
        assert b"SITE_NAME" in resp.data

    def test_api_prefix_not_served_as_static(self, client):
        resp = client.get("/api/nonexistent")
        assert resp.status_code in (404, 405)

    def test_admin_prefix_not_served_as_static(self, client):
        """Requesting /admin* as static should not serve arbitrary files."""
        resp = client.get("/admin.py")
        # This should either serve the template or 404, not the Python source
        # The site_static route excludes paths starting with "admin"
        assert resp.status_code == 404

    def test_nonexistent_file_404(self, client):
        resp = client.get("/does-not-exist.html")
        assert resp.status_code == 404

"""Tests for the GitHub webhook deploy endpoint."""

import hashlib
import hmac
import json
import os
import pytest


class TestWebhookDeploy:

    def test_missing_signature_returns_403(self, client):
        resp = client.post("/webhook/deploy",
                           data=b'{"ref": "refs/heads/main"}',
                           content_type="application/json")
        assert resp.status_code == 403

    def test_invalid_signature_returns_403(self, client, app):
        os.environ["GITHUB_WEBHOOK_SECRET"] = "test-webhook-secret"
        # Reload the config value
        import app as app_module
        app_module.GITHUB_WEBHOOK_SECRET = "test-webhook-secret"

        resp = client.post("/webhook/deploy",
                           data=b'{"ref": "refs/heads/main"}',
                           headers={"X-Hub-Signature-256": "sha256=badsignature"},
                           content_type="application/json")
        assert resp.status_code == 403

    def test_valid_signature_returns_202(self, client, app, monkeypatch):
        secret = "test-webhook-secret"
        os.environ["GITHUB_WEBHOOK_SECRET"] = secret
        import app as app_module
        app_module.GITHUB_WEBHOOK_SECRET = secret

        payload = b'{"ref": "refs/heads/main"}'
        sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        # Mock subprocess.Popen so we don't actually run deploy scripts
        import subprocess
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: None)

        resp = client.post("/webhook/deploy",
                           data=payload,
                           headers={"X-Hub-Signature-256": sig},
                           content_type="application/json")
        assert resp.status_code == 202

    def test_empty_secret_rejects_all(self, client, app):
        """When GITHUB_WEBHOOK_SECRET is empty, all requests are rejected."""
        import app as app_module
        app_module.GITHUB_WEBHOOK_SECRET = ""

        resp = client.post("/webhook/deploy",
                           data=b'{}',
                           headers={"X-Hub-Signature-256": "sha256=anything"},
                           content_type="application/json")
        assert resp.status_code == 403

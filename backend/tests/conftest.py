"""Shared test fixtures for the mdilworth.com backend."""

import os
import sys
import pytest

# Ensure the backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Override env vars BEFORE importing app so SQLite in-memory is used
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["ADMIN_PASSWORD_HASH"] = (
    "scrypt:32768:8:1$test$"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000"
)
# Disable SMTP so no real emails are sent during tests
os.environ["SMTP_USER"] = ""
os.environ["SMTP_PASS"] = ""
# Disable rate limiting during tests
os.environ["RATELIMIT_ENABLED"] = "0"

from app import app as _app, db as _db


@pytest.fixture(autouse=True)
def _reset_login_attempts():
    """Clear the brute-force counter between tests."""
    from admin import _login_attempts
    _login_attempts.clear()
    yield
    _login_attempts.clear()


@pytest.fixture()
def app():
    """Create a fresh application context with an empty in-memory DB."""
    _app.config["TESTING"] = True
    _app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    _app.config["WTF_CSRF_ENABLED"] = False
    _app.config["SERVER_NAME"] = "localhost"

    with _app.app_context():
        _db.create_all()
        yield _app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture()
def db_session(app):
    """Direct access to the SQLAlchemy session."""
    return _db.session


@pytest.fixture()
def admin_client(client, app):
    """Test client already logged in as admin."""
    from werkzeug.security import generate_password_hash
    pw_hash = generate_password_hash("testpassword")
    os.environ["ADMIN_PASSWORD_HASH"] = pw_hash

    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    return client

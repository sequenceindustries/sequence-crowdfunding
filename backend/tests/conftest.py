import io

import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import EmailOutbox, User
from app.security import hash_password

PASSWORD = "Str0ngPassw0rd!"


class Client:
    """Test client that carries the session cookie and CSRF token like a browser."""

    def __init__(self, app):
        self.c = app.test_client()
        self.csrf = None

    def _headers(self):
        return {"X-CSRF-Token": self.csrf} if self.csrf else {}

    def _capture(self, resp):
        if resp.is_json and resp.json and "csrf_token" in resp.json:
            self.csrf = resp.json["csrf_token"]
        return resp

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, json=None, **kw):
        return self._capture(self.c.post(url, json=json, headers=self._headers(), **kw))

    def patch(self, url, json=None):
        return self.c.patch(url, json=json, headers=self._headers())

    def delete(self, url):
        return self.c.delete(url, headers=self._headers())

    def login(self, email, password=PASSWORD):
        return self.post("/api/auth/login", {"email": email, "password": password})

    def register(self, email, role="founder", name="Test User"):
        return self.post("/api/auth/register", {"email": email, "password": PASSWORD,
                                                "full_name": name, "role": role})


@pytest.fixture()
def app(tmp_path):
    class Cfg(TestConfig):
        UPLOAD_DIR = str(tmp_path / "uploads")

    app = create_app(Cfg)
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return Client(app)


@pytest.fixture()
def make_client(app):
    return lambda: Client(app)


def verify_user(email):
    from datetime import datetime, timezone

    u = User.query.filter_by(email=email).first()
    u.email_verified_at = datetime.now(timezone.utc)
    db.session.commit()


def token_from_outbox(to_email, subject_contains):
    """The raw token only ever exists in the email, so tests read it from the dev outbox."""
    import re

    db.session.expire_all()
    rows = EmailOutbox.query.filter(EmailOutbox.to_email == to_email,
                                    EmailOutbox.subject.contains(subject_contains)).order_by(EmailOutbox.id.desc()).all()
    assert rows, f"no '{subject_contains}' email for {to_email}"
    return re.search(r"token=([\w-]+)", rows[0].body).group(1)


@pytest.fixture()
def founder(make_client):
    c = make_client()
    assert c.register("founder@example.com").status_code == 201
    verify_user("founder@example.com")
    return c


@pytest.fixture()
def other_founder(make_client):
    c = make_client()
    assert c.register("other@example.com").status_code == 201
    verify_user("other@example.com")
    return c


@pytest.fixture()
def supporter(make_client):
    c = make_client()
    assert c.register("backer@example.com", role="supporter").status_code == 201
    verify_user("backer@example.com")
    return c


@pytest.fixture()
def published_campaign(founder, admin, submitted_campaign):
    cid = submitted_campaign
    assert admin.post(f"/api/admin/campaigns/{cid}/decision", {"action": "approve", "reason": "ok"}).status_code == 200
    r = founder.post(f"/api/campaigns/{cid}/publish")
    assert r.status_code == 200
    return {"id": cid, "slug": r.json["campaign"]["slug"]}


def send_event(app, event, secret="test-webhook-secret", provider="mock", signature=None, raw=None):
    """Deliver a webhook the way a provider would: raw JSON body plus an HMAC signature."""
    import json

    from app.payments.base import sign_payload

    raw = raw if raw is not None else json.dumps(event).encode()
    sig = signature if signature is not None else sign_payload(secret, raw)
    return app.test_client().post(f"/api/webhooks/payments/{provider}", data=raw,
                                  content_type="application/json", headers={"X-Signature": sig})


@pytest.fixture()
def admin(app, make_client):
    db.session.add(User(email="admin@example.com", full_name="Admin", role="admin",
                        password_hash=hash_password(PASSWORD)))
    db.session.commit()
    c = make_client()
    assert c.login("admin@example.com").status_code == 200
    return c


@pytest.fixture()
def reviewer(app, make_client):
    db.session.add(User(email="rev@example.com", full_name="Reviewer", role="verification_reviewer",
                        password_hash=hash_password(PASSWORD)))
    db.session.commit()
    c = make_client()
    assert c.login("rev@example.com").status_code == 200
    return c


GOOD_DESCRIPTION = "We make solar-powered phone charging kiosks for township taxi ranks. " * 3


def make_profile(c, name="Sun Kiosks"):
    r = c.post("/api/profiles", {"name": name, "industry": "Energy"})
    assert r.status_code == 201, r.json
    return r.json["profile"]


def complete_campaign_payload(profile_id, goal=1_000_000):
    return {
        "profile_id": profile_id, "title": "Solar kiosks for taxi ranks", "summary": "Charge phones, power lives.",
        "description": GOOD_DESCRIPTION, "funding_model": "business_support", "goal_cents": goal,
        "use_of_funds": [{"item": "Kiosk units", "amount_cents": goal - 100_000},
                         {"item": "Installation", "amount_cents": 100_000}],
    }


@pytest.fixture()
def submitted_campaign(founder):
    p = make_profile(founder)
    r = founder.post("/api/campaigns", complete_campaign_payload(p["id"]))
    assert r.status_code == 201, r.json
    cid = r.json["campaign"]["id"]
    assert founder.post(f"/api/campaigns/{cid}/submit").status_code == 200
    return cid


def minimal_pdf(text="Hello"):
    from pypdf import PdfWriter

    w = PdfWriter()
    w.add_blank_page(72, 72)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def text_pdf(text):
    """Build a one-page PDF containing real extractable text."""
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 10 100 Td ({safe}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 200] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return out

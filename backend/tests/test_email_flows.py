from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import EmailOutbox, EmailToken, User
from conftest import PASSWORD, complete_campaign_payload, make_profile, token_from_outbox, verify_user

NEW_PASSWORD = "BrandNewPassw0rd!"


def test_registration_sends_verification_email_and_token_is_hashed(app, make_client):
    c = make_client()
    c.register("new@example.com")
    raw = token_from_outbox("new@example.com", "Confirm")
    assert len(raw) >= 32
    assert EmailToken.query.filter_by(token_hash=raw).count() == 0  # only a hash is stored
    assert EmailToken.query.count() == 1
    assert "token=" + raw not in "".join(r.subject for r in EmailOutbox.query.all())


def test_verify_email_flow_and_single_use(app, make_client):
    c = make_client()
    c.register("v@example.com")
    assert c.get("/api/auth/me").json["user"]["email_verified"] is False
    raw = token_from_outbox("v@example.com", "Confirm")
    anon = make_client()
    assert anon.post("/api/auth/verify-email", {"token": raw}).status_code == 200
    assert c.get("/api/auth/me").json["user"]["email_verified"] is True
    assert anon.post("/api/auth/verify-email", {"token": raw}).status_code == 400  # already used


def test_bad_tokens_rejected(client):
    for bad in (None, "", "short", 123, "x" * 500, "a" * 43):
        assert client.post("/api/auth/verify-email", {"token": bad}).status_code == 400
        assert client.post("/api/auth/reset-password", {"token": bad, "password": NEW_PASSWORD}).status_code == 400


def test_expired_token_rejected(app, make_client):
    c = make_client()
    c.register("e@example.com")
    raw = token_from_outbox("e@example.com", "Confirm")
    row = EmailToken.query.first()
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.session.commit()
    assert c.post("/api/auth/verify-email", {"token": raw}).status_code == 400
    assert User.query.filter_by(email="e@example.com").first().email_verified_at is None


def test_tokens_are_purpose_bound(app, make_client):
    c = make_client()
    c.register("p@example.com")
    c.post("/api/auth/forgot-password", {"email": "p@example.com"})
    reset_raw = token_from_outbox("p@example.com", "Reset")
    verify_raw = token_from_outbox("p@example.com", "Confirm")
    assert c.post("/api/auth/verify-email", {"token": reset_raw}).status_code == 400
    assert c.post("/api/auth/reset-password", {"token": verify_raw, "password": NEW_PASSWORD}).status_code == 400
    assert c.post("/api/auth/verify-email", {"token": verify_raw}).status_code == 200


def test_resend_verification_and_hourly_throttle(app, make_client):
    c = make_client()
    c.register("r@example.com")  # token 1 already issued at registration
    assert c.post("/api/auth/request-verification").status_code == 200  # 2
    assert c.post("/api/auth/request-verification").status_code == 200  # 3
    assert c.post("/api/auth/request-verification").status_code == 429
    # only the newest link works
    assert EmailToken.query.filter(EmailToken.used_at.is_(None)).count() == 1
    assert make_client().post("/api/auth/request-verification").status_code == 401


def test_older_link_is_replaced_by_newer(app, make_client):
    c = make_client()
    c.register("o@example.com")
    first = token_from_outbox("o@example.com", "Confirm")
    c.post("/api/auth/request-verification")
    second = token_from_outbox("o@example.com", "Confirm")
    assert first != second
    assert c.post("/api/auth/verify-email", {"token": first}).status_code == 400
    assert c.post("/api/auth/verify-email", {"token": second}).status_code == 200


def test_already_verified_user_gets_no_new_email(founder):
    before = EmailOutbox.query.count()
    assert founder.post("/api/auth/request-verification").json["already_verified"] is True
    assert EmailOutbox.query.count() == before


def test_unverified_founder_cannot_submit_campaign(make_client):
    c = make_client()
    c.register("unv@example.com")
    p = make_profile(c)
    cid = c.post("/api/campaigns", complete_campaign_payload(p["id"])).json["campaign"]["id"]
    r = c.post(f"/api/campaigns/{cid}/submit")
    assert r.status_code == 403 and r.json["error"] == "email_not_verified"
    verify_user("unv@example.com")
    assert c.post(f"/api/campaigns/{cid}/submit").status_code == 200


def test_forgot_password_is_generic_and_sends_only_for_real_accounts(app, make_client, founder):
    anon = make_client()
    before = EmailOutbox.query.count()
    ghost = anon.post("/api/auth/forgot-password", {"email": "nobody@example.com"})
    real = anon.post("/api/auth/forgot-password", {"email": "founder@example.com"})
    assert ghost.status_code == real.status_code == 200 and ghost.json == real.json
    assert EmailOutbox.query.count() == before + 1
    assert anon.post("/api/auth/forgot-password", {"email": "not-an-email"}).status_code == 200
    assert anon.post("/api/auth/forgot-password", {}).status_code == 200
    assert EmailOutbox.query.count() == before + 1


def test_password_reset_end_to_end_and_signs_out_other_sessions(app, make_client):
    phone, laptop = make_client(), make_client()
    phone.register("reset@example.com")
    laptop.login("reset@example.com")
    assert laptop.get("/api/auth/me").json["user"] is not None
    make_client().post("/api/auth/forgot-password", {"email": "reset@example.com"})
    raw = token_from_outbox("reset@example.com", "Reset")
    r = make_client().post("/api/auth/reset-password", {"token": raw, "password": NEW_PASSWORD})
    assert r.status_code == 200
    assert laptop.get("/api/auth/me").json["user"] is None and phone.get("/api/auth/me").json["user"] is None
    fresh = make_client()
    assert fresh.login("reset@example.com", PASSWORD).status_code == 401
    assert fresh.login("reset@example.com", NEW_PASSWORD).status_code == 200
    assert make_client().post("/api/auth/reset-password", {"token": raw, "password": NEW_PASSWORD}).status_code == 400
    assert User.query.filter_by(email="reset@example.com").first().email_verified_at is not None


def test_weak_new_password_does_not_burn_the_link(app, make_client, founder):
    anon = make_client()
    anon.post("/api/auth/forgot-password", {"email": "founder@example.com"})
    raw = token_from_outbox("founder@example.com", "Reset")
    assert anon.post("/api/auth/reset-password", {"token": raw, "password": "weak"}).status_code == 400
    assert anon.post("/api/auth/reset-password", {"token": raw, "password": NEW_PASSWORD}).status_code == 200


def test_deleted_account_cannot_reset(app, make_client):
    c = make_client()
    c.register("gone@example.com")
    make_client().post("/api/auth/forgot-password", {"email": "gone@example.com"})
    raw = token_from_outbox("gone@example.com", "Reset")
    c.delete("/api/auth/account")
    assert make_client().post("/api/auth/reset-password", {"token": raw, "password": NEW_PASSWORD}).status_code == 400


def test_reset_requests_throttled_per_user(app, make_client, founder):
    anon = make_client()
    for _ in range(5):
        anon.post("/api/auth/forgot-password", {"email": "founder@example.com"})
    sent = EmailOutbox.query.filter(EmailOutbox.to_email == "founder@example.com",
                                    EmailOutbox.subject.contains("Reset")).count()
    assert sent == 3

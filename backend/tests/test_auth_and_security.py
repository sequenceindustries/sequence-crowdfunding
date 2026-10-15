from app.models import User
from conftest import PASSWORD


def test_register_login_logout(make_client):
    c = make_client()
    r = c.register("a@example.com")
    assert r.status_code == 201 and r.json["user"]["role"] == "founder"
    assert c.get("/api/auth/me").json["user"]["email"] == "a@example.com"
    c.post("/api/auth/logout")
    assert c.get("/api/auth/me").json["user"] is None
    assert c.login("a@example.com").status_code == 200


def test_passwords_are_hashed_not_stored(app, founder):
    u = User.query.filter_by(email="founder@example.com").first()
    assert PASSWORD not in u.password_hash and u.password_hash.startswith("$argon2")


def test_weak_password_and_duplicate_email_rejected(client):
    r = client.post("/api/auth/register", {"email": "x@example.com", "password": "short",
                                           "full_name": "X", "role": "founder"})
    assert r.status_code == 400
    assert client.register("dup@example.com").status_code == 201
    assert client.register("dup@example.com").status_code == 409


def test_cannot_self_register_as_admin(client):
    r = client.post("/api/auth/register", {"email": "evil@example.com", "password": PASSWORD,
                                           "full_name": "Evil", "role": "admin"})
    assert r.status_code == 400
    assert User.query.filter_by(email="evil@example.com").first() is None


def test_bad_login_is_generic(client, founder):
    assert client.login("founder@example.com", "WrongPassw0rd!").status_code == 401
    assert client.login("nobody@example.com").status_code == 401


def test_csrf_required_for_authenticated_writes(founder):
    saved = founder.csrf
    founder.csrf = None
    assert founder.post("/api/profiles", {"name": "No Token"}).status_code == 403
    founder.csrf = "wrong"
    assert founder.post("/api/profiles", {"name": "Bad Token"}).status_code == 403
    founder.csrf = saved
    assert founder.post("/api/profiles", {"name": "Good Token"}).status_code == 201


def test_role_enforcement_on_backend(make_client, founder, admin):
    supporter = make_client()
    supporter.register("s@example.com", role="supporter")
    assert supporter.post("/api/profiles", {"name": "Nope"}).status_code == 403
    assert founder.get("/api/admin/overview").status_code == 403
    assert supporter.get("/api/admin/review-queue").status_code == 403
    assert make_client().get("/api/admin/overview").status_code == 401
    assert admin.get("/api/admin/overview").status_code == 200


def test_account_deletion_anonymises(app, founder):
    assert founder.delete("/api/auth/account").status_code == 200
    u = db_user("deleted-")
    assert u.full_name == "Deleted user" and not u.is_active
    assert founder.get("/api/auth/me").json["user"] is None


def db_user(prefix):
    return User.query.filter(User.email.like(f"{prefix}%")).first()


def test_security_headers_present(client):
    r = client.get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"

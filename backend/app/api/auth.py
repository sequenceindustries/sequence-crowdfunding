import re
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request, session

from ..extensions import db, limiter
from ..models import User
from ..security import (
    current_user, hash_password, login_required, start_session,
    validate_password_strength, verify_password,
)
from ..services.audit import audit
from ..services.mail import send_mail
from ..services.tokens import consume_token, issue_token

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SELF_SERVICE_ROLES = ("founder", "supporter")
# Constant-time-ish decoy so unknown emails cost the same as wrong passwords.
_DECOY_HASH = hash_password("decoy-password-A1-never-used")


def user_dict(u: User):
    return {"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role,
            "email_verified": u.email_verified_at is not None}


def _send_verification(user: User) -> bool:
    raw = issue_token(user, "verify_email")
    if raw is None:
        return False
    link = f"{current_app.config['FRONTEND_ORIGIN']}/verify-email?token={raw}"
    send_mail(user.email, "Confirm your email address",
              f"Hello {user.full_name},\n\nConfirm your email address:\n{link}\n\n"
              "This link works once and expires in 24 hours. If you did not create an account, ignore this email.")
    return True


@bp.post("/register")
@limiter.limit("10 per hour")
def register():
    body = request.get_json(silent=True) or {}
    email = str(body.get("email", "")).strip().lower()
    name = str(body.get("full_name", "")).strip()
    role = body.get("role", "supporter")
    password = body.get("password", "")
    if not EMAIL_RE.match(email) or len(email) > 255:
        return jsonify(error="invalid_email"), 400
    if not (1 <= len(name) <= 200):
        return jsonify(error="invalid_name"), 400
    if role not in SELF_SERVICE_ROLES:  # admin/reviewer can never be self-assigned
        return jsonify(error="invalid_role"), 400
    problem = validate_password_strength(password)
    if problem:
        return jsonify(error="weak_password", message=problem), 400
    if User.query.filter_by(email=email).first():
        return jsonify(error="email_taken"), 409
    user = User(email=email, full_name=name, role=role, password_hash=hash_password(password))
    db.session.add(user)
    db.session.flush()
    audit(user.id, "user.register", "user", user.id)
    _send_verification(user)
    db.session.commit()
    start_session(user)
    return jsonify(user=user_dict(user), csrf_token=session["csrf"]), 201


@bp.post("/login")
@limiter.limit("10 per minute")
def login():
    body = request.get_json(silent=True) or {}
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))
    user = User.query.filter_by(email=email).first()
    ok = verify_password(user.password_hash if user else _DECOY_HASH, password)
    if not (user and ok and user.is_active and user.deleted_at is None):
        return jsonify(error="invalid_credentials"), 401
    start_session(user)
    audit(user.id, "user.login", "user", user.id)
    db.session.commit()
    return jsonify(user=user_dict(user), csrf_token=session["csrf"])


@bp.post("/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@bp.get("/me")
def me():
    user = current_user()
    if user is None:
        return jsonify(user=None)
    return jsonify(user=user_dict(user), csrf_token=session.get("csrf"))


@bp.delete("/account")
@login_required
def delete_account():
    """POPIA-style erasure request: deactivate and anonymise personal fields."""
    user = current_user()
    audit(user.id, "user.delete_account", "user", user.id)
    user.email = f"deleted-{user.id}@deleted.invalid"
    user.full_name = "Deleted user"
    user.is_active = False
    user.session_version += 1
    user.deleted_at = datetime.now(timezone.utc)
    db.session.commit()
    session.clear()
    return jsonify(ok=True)


@bp.post("/request-verification")
@login_required
@limiter.limit("10 per hour")
def request_verification():
    user = current_user()
    if user.email_verified_at is not None:
        return jsonify(already_verified=True)
    sent = _send_verification(user)
    db.session.commit()
    if not sent:
        return jsonify(error="too_many_requests", message="Please wait before requesting another email."), 429
    return jsonify(ok=True)


@bp.post("/verify-email")
@limiter.limit("20 per hour")
def verify_email():
    user = consume_token((request.get_json(silent=True) or {}).get("token"), "verify_email")
    if user is None:
        db.session.rollback()
        return jsonify(error="invalid_or_expired_token"), 400
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(timezone.utc)
    audit(user.id, "user.verify_email", "user", user.id)
    db.session.commit()
    return jsonify(ok=True)


@bp.post("/forgot-password")
@limiter.limit("5 per hour")
def forgot_password():
    """Always answers the same way so the endpoint cannot be used to discover which emails have accounts."""
    email = str((request.get_json(silent=True) or {}).get("email", "")).strip().lower()
    user = User.query.filter_by(email=email).first() if EMAIL_RE.match(email) else None
    if user is not None and user.is_active and user.deleted_at is None:
        raw = issue_token(user, "reset_password")
        if raw is not None:
            link = f"{current_app.config['FRONTEND_ORIGIN']}/reset-password?token={raw}"
            send_mail(user.email, "Reset your password",
                      f"Hello {user.full_name},\n\nChoose a new password:\n{link}\n\n"
                      "This link works once and expires in 1 hour. If you did not ask for this, ignore this email; "
                      "your password has not changed.")
            audit(user.id, "user.forgot_password", "user", user.id)
        db.session.commit()
    return jsonify(ok=True, message="If an account exists for that email, a reset link has been sent.")


@bp.post("/reset-password")
@limiter.limit("10 per hour")
def reset_password():
    body = request.get_json(silent=True) or {}
    # Check the password first so a typo does not burn the one-time link.
    problem = validate_password_strength(body.get("password", ""))
    if problem:
        return jsonify(error="weak_password", message=problem), 400
    user = consume_token(body.get("token"), "reset_password")
    if user is None:
        db.session.rollback()
        return jsonify(error="invalid_or_expired_token"), 400
    user.password_hash = hash_password(body["password"])
    user.session_version += 1  # signs out every existing session
    if user.email_verified_at is None:  # receiving the link proves control of the mailbox
        user.email_verified_at = datetime.now(timezone.utc)
    audit(user.id, "user.reset_password", "user", user.id)
    db.session.commit()
    session.clear()
    return jsonify(ok=True)

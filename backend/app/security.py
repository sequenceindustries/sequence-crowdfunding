import secrets
from functools import wraps

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from flask import jsonify, request, session

from .extensions import db
from .models import User

_ph = PasswordHasher()

MIN_PASSWORD_LENGTH = 10


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return _ph.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def validate_password_strength(password: str):
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if password.lower() == password or password.upper() == password:
        return "Password must mix upper and lower case letters."
    if not any(c.isdigit() for c in password):
        return "Password must contain a digit."
    return None


def start_session(user: User):
    session.clear()
    session["user_id"] = user.id
    session["sv"] = user.session_version
    session["csrf"] = secrets.token_urlsafe(32)
    session.permanent = True


def current_user():
    # Cache on the request itself (not flask.g, which can outlive a request when an
    # app context is already active) so one request can never see another's user.
    if "cf.current_user" in request.environ:
        return request.environ["cf.current_user"]
    user = None
    uid = session.get("user_id")
    if uid:
        user = db.session.get(User, uid)
        if user is not None and (not user.is_active or user.deleted_at is not None
                                 or session.get("sv") != user.session_version):
            user = None
    request.environ["cf.current_user"] = user
    return user


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            return jsonify(error="authentication_required"), 401
        return fn(*args, **kwargs)

    return wrapper


def roles_required(*roles):
    """Authorisation is enforced here, on the server, for every protected route."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return jsonify(error="authentication_required"), 401
            if user.role not in roles:
                return jsonify(error="forbidden"), 403
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def enforce_csrf():
    """Header token check for state-changing requests made with a session cookie."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    if "user_id" not in session:
        return None
    sent = request.headers.get("X-CSRF-Token", "")
    expected = session.get("csrf", "")
    if not expected or not secrets.compare_digest(sent, expected):
        return jsonify(error="csrf_failed"), 403
    return None

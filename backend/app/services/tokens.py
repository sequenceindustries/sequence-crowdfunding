"""Single-use email tokens. The raw token exists only in the email; the database keeps a hash."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from ..extensions import db
from ..models import EmailToken, User

TTL = {"verify_email": timedelta(hours=24), "reset_password": timedelta(hours=1)}
MAX_PER_HOUR = 3


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _now():
    return datetime.now(timezone.utc)


def issue_token(user: User, purpose: str):
    """Return a raw token, or None when the user has asked for too many in the last hour."""
    now = _now()
    recent = EmailToken.query.filter(
        EmailToken.user_id == user.id, EmailToken.purpose == purpose,
        EmailToken.created_at >= now - timedelta(hours=1),
    ).count()
    if recent >= MAX_PER_HOUR:
        return None
    # A newer token replaces any older unused one.
    EmailToken.query.filter_by(user_id=user.id, purpose=purpose, used_at=None).update(
        {"used_at": now}, synchronize_session=False)
    raw = secrets.token_urlsafe(32)
    db.session.add(EmailToken(user_id=user.id, purpose=purpose, token_hash=_hash(raw),
                              expires_at=now + TTL[purpose]))
    return raw


def consume_token(raw, purpose: str):
    """Return the user the token belongs to and mark it used, or None if invalid, expired or used."""
    if not isinstance(raw, str) or not (10 <= len(raw) <= 200):
        return None
    row = EmailToken.query.filter_by(token_hash=_hash(raw), purpose=purpose).first()
    now = _now()
    if row is None or row.used_at is not None or row.expires_at < now:
        return None
    user = db.session.get(User, row.user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        return None
    # Atomic claim so two simultaneous requests cannot both use the same token.
    claimed = EmailToken.query.filter(EmailToken.id == row.id, EmailToken.used_at.is_(None)).update(
        {"used_at": now}, synchronize_session=False)
    return user if claimed == 1 else None

from ..extensions import db
from ..models import AuditLog


def audit(actor_id, action, target_type=None, target_id=None, detail=None):
    """Append an audit record. Caller commits as part of its own transaction."""
    db.session.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail or {},
        )
    )

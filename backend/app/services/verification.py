"""Verification state is derived only from documents a human reviewer approved."""
from ..models import VerificationDocument


def has_approved(owner_id: int, kind: str) -> bool:
    return VerificationDocument.query.filter_by(owner_id=owner_id, kind=kind, status="approved").first() is not None


def verification_flags(owner_id: int) -> dict:
    return {
        "identity_checked": has_approved(owner_id, "identity"),
        "business_documents_reviewed": has_approved(owner_id, "business_registration"),
    }

import io

from flask import Blueprint, jsonify, request, send_file

from ..extensions import db, limiter
from ..models import VERIFICATION_KINDS, User, VerificationDocument, utcnow
from ..security import current_user, login_required, roles_required
from ..services.audit import audit
from ..services.mail import send_mail
from ..storage.private import (
    VERIFICATION_ALLOWED, UploadRejected, make_verification_token, read_private,
    read_verification_token, remove_private, save_private, validate_upload,
)

bp = Blueprint("verification", __name__, url_prefix="/api")

REVIEW_ROLES = ("admin", "verification_reviewer")
MAX_OPEN_DOCS = 12
# action -> (statuses it may be applied to, resulting status)
ACTIONS = {
    "approve": (("pending", "escalated"), "approved"),
    "reject": (("pending", "escalated"), "rejected"),
    "request_info": (("pending", "escalated"), "info_requested"),
    "escalate": (("pending",), "escalated"),
}


def _doc_dict(d: VerificationDocument, staff=False):
    out = {"id": d.id, "kind": d.kind, "filename": d.original_filename, "size_bytes": d.size_bytes,
           "status": d.status, "reviewer_note": d.reviewer_note,
           "reviewed_at": d.reviewed_at.isoformat() if d.reviewed_at else None,
           "created_at": d.created_at.isoformat()}
    if staff:
        owner = db.session.get(User, d.owner_id)
        out["owner"] = {"id": owner.id, "email": owner.email, "full_name": owner.full_name}
        out["sha256"] = d.sha256
    return out


# ---- owner -------------------------------------------------------------------------------------
@bp.post("/verification/documents")
@roles_required("founder")
@limiter.limit("20 per hour")
def upload():
    user = current_user()
    kind = request.form.get("kind")
    if kind not in VERIFICATION_KINDS:
        return jsonify(error="invalid_kind", kinds=list(VERIFICATION_KINDS)), 400
    f = request.files.get("file")
    if f is None:
        return jsonify(error="file_required"), 400
    if VerificationDocument.query.filter_by(owner_id=user.id).count() >= MAX_OPEN_DOCS:
        return jsonify(error="too_many_documents"), 409
    data = f.read()
    try:
        ext, content_type = validate_upload(f.filename, data, VERIFICATION_ALLOWED)
    except UploadRejected as exc:
        return jsonify(error="upload_rejected", message=str(exc)), 400
    key, digest = save_private(data, ext)
    d = VerificationDocument(owner_id=user.id, kind=kind, original_filename=(f.filename or "document")[:255],
                             storage_key=key, content_type=content_type, size_bytes=len(data), sha256=digest)
    db.session.add(d)
    db.session.flush()
    audit(user.id, "verification.upload", "verification_document", d.id, {"kind": kind})
    db.session.commit()
    return jsonify(document=_doc_dict(d)), 201


@bp.get("/verification/documents")
@roles_required("founder")
def my_documents():
    rows = (VerificationDocument.query.filter_by(owner_id=current_user().id)
            .order_by(VerificationDocument.id.desc()).all())
    return jsonify(documents=[_doc_dict(d) for d in rows])


@bp.delete("/verification/documents/<int:doc_id>")
@roles_required("founder")
def delete_own(doc_id):
    d = db.session.get(VerificationDocument, doc_id)
    if d is None or d.owner_id != current_user().id:
        return jsonify(error="not_found"), 404
    if d.status == "approved":
        return jsonify(error="approved_documents_cannot_be_deleted",
                       message="Approved evidence is kept for the record. Contact support to have it removed."), 409
    remove_private(d.storage_key)
    audit(current_user().id, "verification.delete", "verification_document", d.id)
    db.session.delete(d)
    db.session.commit()
    return jsonify(ok=True)


# ---- staff -------------------------------------------------------------------------------------
@bp.get("/admin/verification/queue")
@roles_required(*REVIEW_ROLES)
def queue():
    statuses = ["pending"] + (["escalated"] if current_user().role == "admin" else [])
    rows = (VerificationDocument.query.filter(VerificationDocument.status.in_(statuses))
            .order_by(VerificationDocument.created_at).all())
    return jsonify(documents=[_doc_dict(d, staff=True) for d in rows])


@bp.post("/admin/verification/documents/<int:doc_id>/download-link")
@roles_required(*REVIEW_ROLES)
def staff_download_link(doc_id):
    user = current_user()
    d = db.session.get(VerificationDocument, doc_id)
    # Reviewers see only documents awaiting their decision; escalated ones are admin-only.
    visible = {"pending"} if user.role == "verification_reviewer" else {"pending", "escalated", "approved", "info_requested", "rejected"}
    if d is None or d.status not in visible:
        return jsonify(error="not_found"), 404
    audit(user.id, "verification.download_link", "verification_document", d.id)
    db.session.commit()
    return jsonify(url=f"/api/verification/download/{make_verification_token(d.id, user.id)}", expires_in=300)


@bp.get("/verification/download/<token>")
@login_required
def download(token):
    payload = read_verification_token(token)
    user = current_user()
    if not payload or payload["u"] != user.id or user.role not in REVIEW_ROLES:
        return jsonify(error="invalid_or_expired"), 403
    d = db.session.get(VerificationDocument, payload["d"])
    if d is None:
        return jsonify(error="not_found"), 404
    audit(user.id, "verification.download", "verification_document", d.id)
    db.session.commit()
    resp = send_file(io.BytesIO(read_private(d.storage_key)), mimetype=d.content_type,
                     as_attachment=True, download_name=f"verification-{d.id}{d.storage_key[d.storage_key.rfind('.'):]}")
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@bp.post("/admin/verification/documents/<int:doc_id>/decision")
@roles_required(*REVIEW_ROLES)
def decide(doc_id):
    user = current_user()
    body = request.get_json(silent=True) or {}
    action = body.get("action")
    reason = str(body.get("reason", "")).strip()
    if action not in ACTIONS:
        return jsonify(error="invalid_action"), 400
    if not reason:
        return jsonify(error="reason_required"), 400
    d = db.session.get(VerificationDocument, doc_id)
    if d is None:
        return jsonify(error="not_found"), 404
    allowed_from, new_status = ACTIONS[action]
    if d.status == "escalated" and user.role != "admin":
        return jsonify(error="not_found"), 404
    if d.status not in allowed_from:
        return jsonify(error="invalid_transition", message=f"Cannot {action} a document that is {d.status}."), 409
    d.status, d.reviewer_note, d.reviewed_by, d.reviewed_at = new_status, reason, user.id, utcnow()
    audit(user.id, f"verification.{action}", "verification_document", d.id, {"reason": reason, "kind": d.kind})
    if action in ("approve", "reject", "request_info"):
        owner = db.session.get(User, d.owner_id)
        send_mail(owner.email, f"Your {d.kind.replace('_', ' ')} document: {new_status.replace('_', ' ')}",
                  f"Your uploaded document '{d.original_filename}' is now: {new_status.replace('_', ' ')}.\n\n"
                  f"Reviewer note: {reason}\n")
    db.session.commit()
    return jsonify(document=_doc_dict(d, staff=True))

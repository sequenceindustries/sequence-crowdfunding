"""Image upload endpoints for campaign covers and business logos.

Images are stored privately (same local-disk store as verification docs) and
served via short-lived signed URLs so the raw storage path is never exposed.
Campaigns and profiles may hold at most one image each; uploading replaces it.
"""
from flask import Blueprint, jsonify, request, send_file
from io import BytesIO

from ..extensions import db, limiter
from ..models import BusinessProfile, Campaign
from ..security import current_user, login_required, roles_required
from ..services.audit import audit
from ..storage.private import (
    IMAGE_ALLOWED,
    IMAGE_MAX_MB,
    make_image_token,
    read_image_token,
    read_private,
    remove_private,
    save_private,
    validate_upload,
    UploadRejected,
)

bp = Blueprint("images", __name__, url_prefix="/api")


def _validate_image(file_storage):
    """Read, size-check, magic-byte validate; return (data, ext, content_type)."""
    data = file_storage.read(IMAGE_MAX_MB * 1024 * 1024 + 1)
    if len(data) > IMAGE_MAX_MB * 1024 * 1024:
        raise UploadRejected(f"Image must be {IMAGE_MAX_MB} MB or smaller.")
    # WebP: RIFF + 4-byte size + WEBP
    filename = file_storage.filename or ""
    ext, content_type = validate_upload(filename, data, allowed=IMAGE_ALLOWED)
    if ext == ".webp" and data[8:12] != b"WEBP":
        raise UploadRejected("The file content does not match its extension.")
    return data, ext, content_type


# ── Campaign cover ────────────────────────────────────────────────────────────

@bp.post("/campaigns/<int:campaign_id>/cover-image")
@roles_required("founder")
@limiter.limit("20 per hour")
def upload_campaign_cover(campaign_id):
    c = db.session.get(Campaign, campaign_id)
    if c is None or c.owner_id != current_user().id:
        return jsonify(error="not_found"), 404
    if "image" not in request.files:
        return jsonify(error="no_file", message="Send the image as multipart field 'image'."), 400
    try:
        data, ext, content_type = _validate_image(request.files["image"])
    except UploadRejected as e:
        return jsonify(error="invalid_image", message=str(e)), 400
    old_key = c.cover_image_key
    key, _ = save_private(data, ext)
    c.cover_image_key = key
    audit(current_user().id, "campaign.cover_image_uploaded", "campaign", c.id)
    db.session.commit()
    if old_key:
        remove_private(old_key)
    token = make_public_image_token(key)
    return jsonify(token=token), 201


@bp.delete("/campaigns/<int:campaign_id>/cover-image")
@roles_required("founder")
def delete_campaign_cover(campaign_id):
    c = db.session.get(Campaign, campaign_id)
    if c is None or c.owner_id != current_user().id:
        return jsonify(error="not_found"), 404
    old_key = c.cover_image_key
    if old_key:
        c.cover_image_key = None
        audit(current_user().id, "campaign.cover_image_deleted", "campaign", c.id)
        db.session.commit()
        remove_private(old_key)
    return jsonify(ok=True)


# ── Business logo ─────────────────────────────────────────────────────────────

@bp.post("/profiles/<int:profile_id>/logo")
@roles_required("founder")
@limiter.limit("20 per hour")
def upload_profile_logo(profile_id):
    p = db.session.get(BusinessProfile, profile_id)
    if p is None or p.owner_id != current_user().id:
        return jsonify(error="not_found"), 404
    if "image" not in request.files:
        return jsonify(error="no_file", message="Send the image as multipart field 'image'."), 400
    try:
        data, ext, content_type = _validate_image(request.files["image"])
    except UploadRejected as e:
        return jsonify(error="invalid_image", message=str(e)), 400
    old_key = p.logo_key
    key, _ = save_private(data, ext)
    p.logo_key = key
    audit(current_user().id, "profile.logo_uploaded", "business_profile", p.id)
    db.session.commit()
    if old_key:
        remove_private(old_key)
    token = make_public_image_token(key)
    return jsonify(token=token), 201


@bp.delete("/profiles/<int:profile_id>/logo")
@roles_required("founder")
def delete_profile_logo(profile_id):
    p = db.session.get(BusinessProfile, profile_id)
    if p is None or p.owner_id != current_user().id:
        return jsonify(error="not_found"), 404
    old_key = p.logo_key
    if old_key:
        p.logo_key = None
        audit(current_user().id, "profile.logo_deleted", "business_profile", p.id)
        db.session.commit()
        remove_private(old_key)
    return jsonify(ok=True)


# ── Serve images ──────────────────────────────────────────────────────────────

@bp.get("/images/<token>")
@login_required
def serve_image(token):
    payload = read_image_token(token)
    if payload is None:
        return jsonify(error="expired_or_invalid"), 403
    # Token is user-bound so a link cannot be passed to someone else.
    if payload.get("u") != current_user().id:
        return jsonify(error="forbidden"), 403
    key = payload.get("k", "")
    try:
        data = read_private(key)
    except FileNotFoundError:
        return jsonify(error="not_found"), 404
    ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
    mime = {
        "png": "image/png", "jpg": "image/jpeg",
        "jpeg": "image/jpeg", "webp": "image/webp",
    }.get(ext, "application/octet-stream")
    return send_file(BytesIO(data), mimetype=mime, max_age=0)


# ── Public image tokens for published campaigns ───────────────────────────────
# Campaign cover images on published campaigns need to be viewable without
# auth (for the public listing page). We issue a short-lived anonymous token.
# The image itself is still served from our storage — we just widen the window.

from itsdangerous import URLSafeTimedSerializer
from flask import current_app


def _anon_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="public-image")


def make_public_image_token(key: str) -> str:
    return _anon_serializer().dumps({"k": key})


def read_public_image_token(token: str, max_age=300):
    from itsdangerous import BadSignature, SignatureExpired
    try:
        return _anon_serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


@bp.get("/public/images/<token>")
def serve_public_image(token):
    payload = read_public_image_token(token)
    if payload is None:
        return jsonify(error="expired_or_invalid"), 403
    key = payload.get("k", "")
    try:
        data = read_private(key)
    except FileNotFoundError:
        return jsonify(error="not_found"), 404
    ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
    mime = {
        "png": "image/png", "jpg": "image/jpeg",
        "jpeg": "image/jpeg", "webp": "image/webp",
    }.get(ext, "application/octet-stream")
    return send_file(BytesIO(data), mimetype=mime, max_age=0)

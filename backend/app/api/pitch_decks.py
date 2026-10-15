from flask import Blueprint, current_app, jsonify, request, send_file
import io

from ..ai import run_pitch_deck_analysis
from ..ai.base import AiProviderError
from ..extensions import db, limiter
from ..models import Campaign, PitchDeck, PitchDeckAnalysis
from ..security import current_user, login_required, roles_required
from ..services.audit import audit
from ..services.documents import ExtractionError, extract_text
from ..services.payments import fee_satisfied
from .payments import fee_settings
from ..storage.private import (
    UploadRejected, make_download_token, read_download_token, read_private, save_private,
    validate_upload,
)

bp = Blueprint("pitch_decks", __name__, url_prefix="/api")


def _deck_dict(d: PitchDeck):
    return {"id": d.id, "filename": d.original_filename, "size_bytes": d.size_bytes,
            "page_count": d.page_count, "status": d.processing_status,
            "error": d.processing_error, "campaign_id": d.campaign_id,
            "created_at": d.created_at.isoformat()}


def _owned_deck(deck_id):
    d = db.session.get(PitchDeck, deck_id)
    if d is None or d.owner_id != current_user().id:
        return None
    return d


@bp.post("/pitch-decks")
@roles_required("founder")
@limiter.limit("20 per hour")
def upload_deck():
    f = request.files.get("file")
    if f is None:
        return jsonify(error="file_required"), 400
    campaign_id = request.form.get("campaign_id", type=int)
    if campaign_id is not None:
        c = db.session.get(Campaign, campaign_id)
        if c is None or c.owner_id != current_user().id:
            return jsonify(error="campaign_not_found"), 404
    data = f.read()
    try:
        ext, content_type = validate_upload(f.filename, data)
    except UploadRejected as exc:
        return jsonify(error="upload_rejected", message=str(exc)), 400
    key, digest = save_private(data, ext)
    deck = PitchDeck(owner_id=current_user().id, campaign_id=campaign_id,
                     original_filename=(f.filename or "deck")[:255], storage_key=key,
                     content_type=content_type, size_bytes=len(data), sha256=digest)
    try:
        text, pages = extract_text(data, ext)
        deck.extracted_text, deck.page_count = text, pages
        deck.processing_status = "ready" if text else "no_text"
        if not text:
            deck.processing_error = "No readable text found (the file may be scanned images)."
    except ExtractionError as exc:
        deck.processing_status, deck.processing_error = "failed", str(exc)
    db.session.add(deck)
    db.session.flush()
    audit(current_user().id, "pitch_deck.upload", "pitch_deck", deck.id)
    db.session.commit()
    return jsonify(pitch_deck=_deck_dict(deck)), 201


@bp.get("/pitch-decks/<int:deck_id>")
@roles_required("founder")
def get_deck(deck_id):
    d = _owned_deck(deck_id)
    if d is None:
        return jsonify(error="not_found"), 404
    return jsonify(pitch_deck=_deck_dict(d))


@bp.post("/pitch-decks/<int:deck_id>/analyse")
@roles_required("founder")
@limiter.limit("30 per hour")
def analyse(deck_id):
    d = _owned_deck(deck_id)
    if d is None:
        return jsonify(error="not_found"), 404
    fee = fee_settings()
    if fee["charging_enabled"] and not fee_satisfied(d.id):
        return jsonify(error="fee_required", amount_cents=fee["amount_cents"], covers=fee["covers"],
                       message="Analysis of this deck is unlocked by the pitch-deck fee."), 402
    if d.processing_status != "ready":
        return jsonify(error="not_ready", message="The deck has no readable text to analyse."), 409
    consent = bool((request.get_json(silent=True) or {}).get("consent_external_processing"))
    try:
        provider, report = run_pitch_deck_analysis(current_user().id, d.extracted_text, consent)
    except AiProviderError as exc:
        code = str(exc)
        status = {"consent_required": 409, "usage_limit_reached": 429}.get(code, 502)
        return jsonify(error=code if code in ("consent_required", "usage_limit_reached") else "ai_unavailable"), status
    row = PitchDeckAnalysis(pitch_deck_id=d.id, provider=provider,
                            methodology_version=report["methodology_version"], report=report)
    db.session.add(row)
    audit(current_user().id, "pitch_deck.analyse", "pitch_deck", d.id, {"provider": provider})
    db.session.commit()
    return jsonify(analysis_id=row.id, report=report), 201


@bp.get("/pitch-decks/<int:deck_id>/analyses")
@roles_required("founder")
def list_analyses(deck_id):
    d = _owned_deck(deck_id)
    if d is None:
        return jsonify(error="not_found"), 404
    rows = PitchDeckAnalysis.query.filter_by(pitch_deck_id=d.id).order_by(PitchDeckAnalysis.id.desc()).all()
    return jsonify(analyses=[{"id": r.id, "report": r.report, "created_at": r.created_at.isoformat()}
                             for r in rows])


@bp.post("/pitch-decks/<int:deck_id>/download-link")
@login_required
def download_link(deck_id):
    """Issue a short-lived link. Owners may always fetch; staff only while a linked campaign is in review."""
    user = current_user()
    d = db.session.get(PitchDeck, deck_id)
    if d is None:
        return jsonify(error="not_found"), 404
    allowed = d.owner_id == user.id
    if not allowed and user.role in ("admin", "verification_reviewer") and d.campaign_id:
        c = db.session.get(Campaign, d.campaign_id)
        allowed = c is not None and c.status in ("submitted", "changes_requested", "approved", "published")
    if not allowed:
        return jsonify(error="not_found"), 404
    audit(user.id, "pitch_deck.download_link", "pitch_deck", d.id)
    db.session.commit()
    return jsonify(url=f"/api/pitch-decks/download/{make_download_token(d.id, user.id)}", expires_in=300)


@bp.get("/pitch-decks/download/<token>")
@login_required
def download(token):
    payload = read_download_token(token)
    user = current_user()
    # The link only works for the user it was issued to.
    if not payload or payload["u"] != user.id:
        return jsonify(error="invalid_or_expired"), 403
    d = db.session.get(PitchDeck, payload["d"])
    if d is None:
        return jsonify(error="not_found"), 404
    resp = send_file(io.BytesIO(read_private(d.storage_key)), mimetype=d.content_type,
                     as_attachment=True, download_name=d.original_filename)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp

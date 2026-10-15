from flask import Blueprint, jsonify, request

from ..ai import run_campaign_feature
from ..ai.base import AiProviderError
from ..extensions import db, limiter
from ..models import Campaign, CampaignTransparency, utcnow
from ..security import current_user, roles_required
from ..services.audit import audit
from ..services.campaigns import campaign_to_dict
from ..services.transparency import clean_notes, live_verification_section, source_hash

bp = Blueprint("assistant", __name__, url_prefix="/api/campaigns")

AI_ERRORS = {"consent_required": 409, "usage_limit_reached": 429, "not_supported": 501, "provider_failed": 502}


def _owned(campaign_id):
    c = db.session.get(Campaign, campaign_id)
    return c if c is not None and c.owner_id == current_user().id else None


def _ai_error(exc):
    code = str(exc) if str(exc) in AI_ERRORS else "provider_failed"
    return jsonify(error=code), AI_ERRORS[code]


def _t_dict(t, c):
    if t is None:
        return None
    return {"status": t.status, "sections": t.sections, "owner_notes": t.owner_notes, "provider": t.provider,
            "stale": t.source_hash != source_hash(c, t.owner_notes or {}),
            "approved_at": t.approved_at.isoformat() if t.approved_at else None,
            "live_sections": [live_verification_section(c)]}


@bp.post("/<int:campaign_id>/assistant/review")
@roles_required("founder")
@limiter.limit("30 per hour")
def review(campaign_id):
    c = _owned(campaign_id)
    if c is None:
        return jsonify(error="not_found"), 404
    try:
        _, report = run_campaign_feature(current_user().id, "campaign_review", "review_campaign", campaign_to_dict(c))
    except AiProviderError as exc:
        return _ai_error(exc)
    return jsonify(report=report)


@bp.get("/<int:campaign_id>/transparency")
@roles_required("founder")
def get_transparency(campaign_id):
    c = _owned(campaign_id)
    if c is None:
        return jsonify(error="not_found"), 404
    return jsonify(transparency=_t_dict(CampaignTransparency.query.filter_by(campaign_id=c.id).first(), c))


@bp.post("/<int:campaign_id>/transparency/draft")
@roles_required("founder")
@limiter.limit("30 per hour")
def draft(campaign_id):
    c = _owned(campaign_id)
    if c is None:
        return jsonify(error="not_found"), 404
    body = request.get_json(silent=True) or {}
    notes, err = clean_notes(body.get("owner_notes"))
    if err:
        return jsonify(error="invalid_notes", message=err), 400
    try:
        provider, result = run_campaign_feature(current_user().id, "transparency_draft", "draft_transparency", campaign_to_dict(c))
    except AiProviderError as exc:
        return _ai_error(exc)
    if not result.get("sections"):
        return jsonify(error="not_enough_information",
                       message="Add a goal, use of funds and funding model first; there is nothing to build the statement from."), 409
    digest = source_hash(c, notes)  # computed first: it reads relations, which would autoflush a half-built row
    t = CampaignTransparency.query.filter_by(campaign_id=c.id).first()
    if t is None:
        t = CampaignTransparency(campaign_id=c.id)
        db.session.add(t)
    # A new draft always needs a fresh approval, even if the old one was approved.
    t.sections, t.owner_notes, t.provider = result["sections"], notes, provider
    t.source_hash, t.status, t.approved_at = digest, "draft", None
    audit(current_user().id, "transparency.draft", "campaign", c.id)
    db.session.commit()
    return jsonify(transparency=_t_dict(t, c)), 201


@bp.post("/<int:campaign_id>/transparency/approve")
@roles_required("founder")
def approve(campaign_id):
    c = _owned(campaign_id)
    t = CampaignTransparency.query.filter_by(campaign_id=c.id).first() if c else None
    if t is None:
        return jsonify(error="not_found"), 404
    if t.source_hash != source_hash(c, t.owner_notes or {}):
        return jsonify(error="stale_draft", message="The campaign changed after this draft was made. Generate a new draft."), 409
    t.status, t.approved_at = "approved", utcnow()
    audit(current_user().id, "transparency.approve", "campaign", c.id)
    db.session.commit()
    return jsonify(transparency=_t_dict(t, c))


@bp.delete("/<int:campaign_id>/transparency")
@roles_required("founder")
def withdraw(campaign_id):
    c = _owned(campaign_id)
    t = CampaignTransparency.query.filter_by(campaign_id=c.id).first() if c else None
    if t is None:
        return jsonify(error="not_found"), 404
    audit(current_user().id, "transparency.withdraw", "campaign", c.id)
    db.session.delete(t)
    db.session.commit()
    return jsonify(ok=True)

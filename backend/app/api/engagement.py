from flask import Blueprint, jsonify, request

from ..extensions import db, limiter
from ..models import Campaign, CampaignUpdate, Follow
from ..security import current_user, login_required, roles_required
from ..services.audit import audit
from ..services.campaigns import campaign_to_dict

bp = Blueprint("engagement", __name__, url_prefix="/api")

OWNER_LABEL = "Reported by the campaign owner. Not independently verified."


def _published(slug):
    return Campaign.query.filter_by(slug=slug, status="published").first()


@bp.post("/campaigns/<slug>/follow")
@login_required
def follow(slug):
    c = _published(slug)
    if c is None:
        return jsonify(error="not_found"), 404
    exists = Follow.query.filter_by(user_id=current_user().id, campaign_id=c.id).first()
    if exists is None:
        db.session.add(Follow(user_id=current_user().id, campaign_id=c.id))
        db.session.commit()
    return jsonify(following=True), 200 if exists else 201


@bp.delete("/campaigns/<slug>/follow")
@login_required
def unfollow(slug):
    c = Campaign.query.filter_by(slug=slug).first()
    if c is not None:
        Follow.query.filter_by(user_id=current_user().id, campaign_id=c.id).delete()
        db.session.commit()
    return jsonify(following=False)


@bp.get("/follows/mine")
@login_required
def my_follows():
    rows = (Campaign.query.join(Follow, Follow.campaign_id == Campaign.id)
            .filter(Follow.user_id == current_user().id, Campaign.status == "published")
            .order_by(Follow.id.desc()).all())
    return jsonify(campaigns=[campaign_to_dict(c, public=True) for c in rows])


def _update_dict(u: CampaignUpdate):
    return {"id": u.id, "title": u.title, "body": u.body, "created_at": u.created_at.isoformat(),
            "label": OWNER_LABEL}


@bp.post("/campaigns/<int:campaign_id>/updates")
@roles_required("founder")
@limiter.limit("20 per hour")
def post_update(campaign_id):
    c = db.session.get(Campaign, campaign_id)
    if c is None or c.owner_id != current_user().id:
        return jsonify(error="not_found"), 404
    if c.status != "published":
        return jsonify(error="not_published", message="Updates can be posted on published campaigns."), 409
    body = request.get_json(silent=True) or {}
    title, text = body.get("title"), body.get("body")
    if not isinstance(title, str) or not isinstance(text, str) or not title.strip() or not text.strip() \
            or len(title) > 200 or len(text) > 5000:
        return jsonify(error="invalid", message="A title (200 characters max) and body (5000 max) are required."), 400
    u = CampaignUpdate(campaign_id=c.id, author_id=current_user().id, title=title.strip(), body=text.strip())
    db.session.add(u)
    db.session.flush()
    audit(current_user().id, "campaign.update_posted", "campaign_update", u.id)
    db.session.commit()
    return jsonify(update=_update_dict(u)), 201


@bp.get("/campaigns/<int:campaign_id>/updates")
@roles_required("founder")
def my_campaign_updates(campaign_id):
    """List updates for a campaign the current founder owns (includes hidden)."""
    c = db.session.get(Campaign, campaign_id)
    if c is None or c.owner_id != current_user().id:
        return jsonify(error="not_found"), 404
    rows = CampaignUpdate.query.filter_by(campaign_id=c.id).order_by(CampaignUpdate.id.desc()).limit(100).all()
    return jsonify(updates=[{**_update_dict(u), "hidden": u.hidden} for u in rows])


@bp.delete("/campaigns/<int:campaign_id>/updates/<int:update_id>")
@roles_required("founder")
def delete_update(campaign_id, update_id):
    """Founders can retract their own updates before they are hidden by staff."""
    c = db.session.get(Campaign, campaign_id)
    if c is None or c.owner_id != current_user().id:
        return jsonify(error="not_found"), 404
    u = db.session.get(CampaignUpdate, update_id)
    if u is None or u.campaign_id != c.id:
        return jsonify(error="not_found"), 404
    db.session.delete(u)
    audit(current_user().id, "campaign.update_deleted", "campaign_update", update_id)
    db.session.commit()
    return jsonify(ok=True)


@bp.get("/public/campaigns/<slug>/updates")
def public_updates(slug):
    c = _published(slug)
    if c is None:
        return jsonify(error="not_found"), 404
    rows = CampaignUpdate.query.filter_by(campaign_id=c.id, hidden=False).order_by(CampaignUpdate.id.desc()).limit(50).all()
    return jsonify(updates=[_update_dict(u) for u in rows])


@bp.post("/admin/updates/<int:update_id>/hide")
@roles_required("admin", "verification_reviewer")
def hide_update(update_id):
    u = db.session.get(CampaignUpdate, update_id)
    reason = str((request.get_json(silent=True) or {}).get("reason", "")).strip()
    if u is None:
        return jsonify(error="not_found"), 404
    if not reason:
        return jsonify(error="reason_required"), 400
    u.hidden, u.hidden_reason = True, reason
    audit(current_user().id, "campaign.update_hidden", "campaign_update", u.id, {"reason": reason})
    db.session.commit()
    return jsonify(ok=True)

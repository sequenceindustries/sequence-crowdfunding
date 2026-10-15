import re
from datetime import date, datetime, timezone

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import case, func, literal, or_

from ..extensions import db
from ..models import BusinessProfile, Campaign, CampaignMilestone, Follow, User
from ..security import current_user, roles_required
from ..services.audit import audit
from ..services.campaigns import (
    DRAFT_FIELDS, EDITABLE_STATUSES, FUNDING_MODEL_RULES, campaign_to_dict, slugify,
    submission_problems, validate_use_of_funds,
)
from ..services.mail import send_mail

bp = Blueprint("campaigns", __name__, url_prefix="/api")

STR_LIMITS = {"title": 200, "category": 100, "summary": 400, "description": 20000,
              "location": 160, "stage": 60, "objectives": 5000, "funding_purpose": 5000}


def _owned(campaign_id):
    c = db.session.get(Campaign, campaign_id)
    if c is None or c.owner_id != current_user().id:
        return None
    return c


def _apply_draft(c: Campaign, body: dict):
    for f, limit in STR_LIMITS.items():
        if f in body:
            v = body[f]
            if v is not None and not isinstance(v, str):
                return f"{f} must be text."
            setattr(c, f, v.strip()[:limit] if isinstance(v, str) else None)
    if "funding_model" in body:
        model = body["funding_model"]
        if model is not None and model not in FUNDING_MODEL_RULES:
            return "Unknown funding model."
        # Disabled models (investment) cannot even be saved on a draft.
        if model is not None and model not in current_app.config["ENABLED_FUNDING_MODELS"]:
            return "That funding model is not available."
        c.funding_model = model
    for f in ("goal_cents", "duration_days"):
        if f in body:
            v = body[f]
            if v is not None and (not isinstance(v, int) or isinstance(v, bool) or v <= 0):
                return f"{f} must be a positive whole number."
            if f == "duration_days" and v is not None and v > 365:
                return "duration_days cannot exceed 365."
            setattr(c, f, v)
    if "currency" in body:
        if body["currency"] != "ZAR":
            return "Only ZAR is supported."
        c.currency = "ZAR"
    if "use_of_funds" in body:
        cleaned, err = validate_use_of_funds(body["use_of_funds"])
        if err:
            return err
        c.use_of_funds = cleaned or []
    if "milestones" in body:
        ms = body["milestones"]
        if not isinstance(ms, list) or len(ms) > 20:
            return "milestones must be a list of at most 20 items."
        c.milestones.clear()
        for i, m in enumerate(ms):
            title = str(m.get("title", "")).strip()[:200] if isinstance(m, dict) else ""
            if not title:
                return "Each milestone needs a title."
            try:
                td = date.fromisoformat(m["target_date"]) if m.get("target_date") else None
            except (TypeError, ValueError):
                return "Milestone target_date must be YYYY-MM-DD."
            c.milestones.append(CampaignMilestone(
                position=i, title=title, detail=str(m.get("detail", ""))[:2000] or None, target_date=td))
    return None


@bp.post("/campaigns")
@roles_required("founder")
def create_campaign():
    body = request.get_json(silent=True) or {}
    profile = db.session.get(BusinessProfile, body.get("profile_id"))
    if profile is None or profile.owner_id != current_user().id:
        return jsonify(error="profile_not_found"), 404
    c = Campaign(owner_id=current_user().id, profile_id=profile.id,
                 title=str(body.get("title", "")).strip()[:200] or "Untitled campaign")
    err = _apply_draft(c, body)
    if err:
        return jsonify(error="invalid", message=err), 400
    db.session.add(c)
    db.session.flush()
    audit(current_user().id, "campaign.create", "campaign", c.id)
    db.session.commit()
    return jsonify(campaign=campaign_to_dict(c)), 201


@bp.get("/campaigns/mine")
@roles_required("founder")
def my_campaigns():
    rows = Campaign.query.filter_by(owner_id=current_user().id).order_by(Campaign.updated_at.desc()).all()
    return jsonify(campaigns=[campaign_to_dict(c) for c in rows])


@bp.get("/campaigns/<int:campaign_id>")
@roles_required("founder")
def get_my_campaign(campaign_id):
    c = _owned(campaign_id)
    if c is None:
        return jsonify(error="not_found"), 404
    return jsonify(campaign=campaign_to_dict(c))


@bp.patch("/campaigns/<int:campaign_id>")
@roles_required("founder")
def update_campaign(campaign_id):
    c = _owned(campaign_id)
    if c is None:
        return jsonify(error="not_found"), 404
    if c.status not in EDITABLE_STATUSES:
        return jsonify(error="not_editable", message=f"A {c.status} campaign cannot be edited."), 409
    err = _apply_draft(c, request.get_json(silent=True) or {})
    if err:
        return jsonify(error="invalid", message=err), 400
    audit(current_user().id, "campaign.update", "campaign", c.id)
    db.session.commit()
    return jsonify(campaign=campaign_to_dict(c))


@bp.post("/campaigns/<int:campaign_id>/submit")
@roles_required("founder")
def submit_campaign(campaign_id):
    c = _owned(campaign_id)
    if c is None:
        return jsonify(error="not_found"), 404
    if c.status not in EDITABLE_STATUSES:
        return jsonify(error="not_submittable"), 409
    if current_user().email_verified_at is None:
        return jsonify(error="email_not_verified", message="Confirm your email address before submitting."), 403
    problems = submission_problems(c, current_app.config["ENABLED_FUNDING_MODELS"])
    if problems:
        return jsonify(error="incomplete", problems=problems), 422
    c.status = "submitted"
    c.submitted_at = datetime.now(timezone.utc)
    audit(current_user().id, "campaign.submit", "campaign", c.id)
    db.session.commit()
    return jsonify(campaign=campaign_to_dict(c))


@bp.post("/campaigns/<int:campaign_id>/publish")
@roles_required("founder")
def publish_campaign(campaign_id):
    """Only a campaign a reviewer has approved can go live."""
    c = _owned(campaign_id)
    if c is None:
        return jsonify(error="not_found"), 404
    if c.status != "approved":
        return jsonify(error="not_approved", message="Only approved campaigns can be published."), 409
    c.status = "published"
    c.published_at = datetime.now(timezone.utc)
    c.slug = c.slug or slugify(c.title)
    audit(current_user().id, "campaign.publish", "campaign", c.id)
    # Notify followers that this campaign is now live.
    followers = (User.query.join(Follow, Follow.user_id == User.id)
                 .filter(Follow.campaign_id == c.id).all())
    for follower in followers:
        send_mail(follower.email, f"Campaign '{c.title}' is now live",
                  f"A campaign you follow, '{c.title}', has just been published and is now live.\n\n"
                  f"View it at: /campaigns/{c.slug or slugify(c.title)}")
    db.session.commit()
    return jsonify(campaign=campaign_to_dict(c))


# ---------- public discovery ----------

def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


STOPWORDS = {"a", "an", "the", "in", "for", "of", "to", "and", "or", "near", "me", "my", "with", "on", "at", "is", "that"}
# (label, column getter, relevance weight)
SEARCH_FIELDS = (
    ("title", lambda: Campaign.title, 5),
    ("category", lambda: Campaign.category, 3),
    ("business", lambda: BusinessProfile.name, 3),
    ("location", lambda: Campaign.location, 3),
    ("summary", lambda: Campaign.summary, 2),
    ("description", lambda: Campaign.description, 1),
)
SORTS = ("relevance", "recent", "title", "goal_asc", "goal_desc")


def _search_terms(text: str):
    words = [w for w in re.split(r"[^\w'-]+", text.lower()) if w and w not in STOPWORDS]
    return [w[:40] for w in dict.fromkeys(words)][:8]


@bp.get("/public/stats")
def public_stats():
    """Aggregate counts for the homepage. Only confirmed payment data shown."""
    from ..models import User
    published = Campaign.query.filter_by(status="published").count()
    total_campaigns = Campaign.query.count()
    founders = User.query.filter_by(role="founder").count()
    categories = (db.session.query(Campaign.category, func.count(Campaign.id))
                  .filter(Campaign.status == "published", Campaign.category.isnot(None), Campaign.category != "")
                  .group_by(Campaign.category).order_by(func.count(Campaign.id).desc()).limit(5).all())
    return jsonify(stats={
        "published_campaigns": published,
        "total_campaigns": total_campaigns,
        "founders": founders,
        "top_categories": [{"category": c, "count": n} for c, n in categories],
    })


@bp.get("/public/categories")
def public_categories():
    rows = (db.session.query(Campaign.category, func.count(Campaign.id))
            .filter(Campaign.status == "published", Campaign.category.isnot(None), Campaign.category != "")
            .group_by(Campaign.category).order_by(func.count(Campaign.id).desc(), Campaign.category).all())
    return jsonify(categories=[{"category": c, "count": n} for c, n in rows])


@bp.get("/public/campaigns")
def public_campaigns():
    q = Campaign.query.join(BusinessProfile, Campaign.profile_id == BusinessProfile.id).filter(Campaign.status == "published")
    args = request.args
    terms = _search_terms(args.get("q", "")[:200])
    relevance = literal(0)
    for t in terms:
        like = f"%{_escape_like(t)}%"
        # every term must appear somewhere (AND), so adding words narrows the result
        q = q.filter(or_(*[col().ilike(like, escape="\\") for _, col, _ in SEARCH_FIELDS]))
        for _, col, weight in SEARCH_FIELDS:
            relevance = relevance + case((col().ilike(like, escape="\\"), weight), else_=0)
    for field in ("category", "funding_model", "stage"):
        if args.get(field):
            q = q.filter(getattr(Campaign, field) == args[field])
    sort = args.get("sort") or ("relevance" if terms else "recent")
    if sort not in SORTS:
        return jsonify(error="invalid_sort", sorts=list(SORTS)), 400
    if sort == "relevance" and terms:
        q = q.order_by(relevance.desc(), Campaign.published_at.desc())
    elif sort == "title":
        q = q.order_by(Campaign.title.asc())
    elif sort == "goal_asc":
        q = q.order_by(Campaign.goal_cents.asc().nulls_last(), Campaign.id)
    elif sort == "goal_desc":
        q = q.order_by(Campaign.goal_cents.desc().nulls_last(), Campaign.id)
    else:
        q = q.order_by(Campaign.published_at.desc())
    try:
        page = max(int(args.get("page", 1)), 1)
        per_page = min(max(int(args.get("per_page", 12)), 1), 50)
    except ValueError:
        return jsonify(error="invalid_pagination"), 400
    total = q.count()
    rows = q.offset((page - 1) * per_page).limit(per_page).all()
    out = []
    for c in rows:
        d = campaign_to_dict(c, public=True)
        if terms:
            # Explanation: which fields actually contain the searched words (nothing inferred).
            d["match"] = {"terms": terms, "fields": [label for label, col, _ in SEARCH_FIELDS
                                                      if any(t in _value(c, label).lower() for t in terms)]}
        out.append(d)
    return jsonify(campaigns=out, page=page, per_page=per_page, total=total, query_terms=terms)


def _value(c, label):
    return {"title": c.title, "category": c.category, "business": c.profile.name, "location": c.location,
            "summary": c.summary, "description": c.description}[label] or ""


@bp.get("/public/campaigns/<slug>")
def public_campaign(slug):
    c = Campaign.query.filter_by(slug=slug, status="published").first()
    if c is None:
        return jsonify(error="not_found"), 404
    return jsonify(campaign=campaign_to_dict(c, public=True))

from datetime import date

from flask import Blueprint, jsonify, request

from ..extensions import db
from ..models import BusinessProfile, BusinessProfileRevision
from ..security import current_user, roles_required
from ..services.audit import audit
from ..services.campaigns import slugify

bp = Blueprint("profiles", __name__, url_prefix="/api")

TEXT_LIMITS = {
    "name": 200, "industry": 100, "stage": 60, "country": 80, "province": 80, "city": 80,
    "website": 255, "description": 5000, "problem": 3000, "solution": 3000,
    "target_customers": 3000, "business_model": 3000, "competitive_advantage": 3000,
    "public_contact_email": 255,
}


def _logo_token(p: BusinessProfile):
    if p.logo_key:
        from ..api.images import make_public_image_token
        return make_public_image_token(p.logo_key)
    return None


def _owner_dict(p: BusinessProfile):
    d = {f: getattr(p, f) for f in BusinessProfile.PUBLIC_FIELDS}
    d.update(id=p.id, founded_on=p.founded_on.isoformat() if p.founded_on else None,
             public_contact_email=p.public_contact_email, contact_is_public=p.contact_is_public,
             logo_image_token=_logo_token(p))
    return d


def public_profile_dict(p: BusinessProfile):
    d = {f: getattr(p, f) for f in BusinessProfile.PUBLIC_FIELDS}
    d["founded_on"] = p.founded_on.isoformat() if p.founded_on else None
    d["logo_image_token"] = _logo_token(p)
    # Contact details are only exposed when the owner has explicitly opted in.
    if p.contact_is_public and p.public_contact_email:
        d["contact_email"] = p.public_contact_email
    return d


def _apply(profile, body):
    changed = {}
    for field, limit in TEXT_LIMITS.items():
        if field in body:
            value = body[field]
            if value is not None and not isinstance(value, str):
                return None, f"{field} must be text."
            value = value.strip()[:limit] if isinstance(value, str) else None
            if getattr(profile, field) != value:
                changed[field] = {"from": getattr(profile, field), "to": value}
                setattr(profile, field, value)
    if "contact_is_public" in body:
        flag = bool(body["contact_is_public"])
        if profile.contact_is_public != flag:
            changed["contact_is_public"] = {"from": profile.contact_is_public, "to": flag}
            profile.contact_is_public = flag
    if "founded_on" in body:
        try:
            val = date.fromisoformat(body["founded_on"]) if body["founded_on"] else None
        except (TypeError, ValueError):
            return None, "founded_on must be YYYY-MM-DD."
        if profile.founded_on != val:
            changed["founded_on"] = {"from": str(profile.founded_on), "to": str(val)}
            profile.founded_on = val
    return changed, None


@bp.get("/profiles/mine")
@roles_required("founder")
def my_profiles():
    rows = BusinessProfile.query.filter_by(owner_id=current_user().id).order_by(BusinessProfile.id).all()
    return jsonify(profiles=[_owner_dict(p) for p in rows])


@bp.post("/profiles")
@roles_required("founder")
def create_profile():
    body = request.get_json(silent=True) or {}
    if not str(body.get("name", "")).strip():
        return jsonify(error="name_required"), 400
    profile = BusinessProfile(owner_id=current_user().id, name="x", slug=slugify(body["name"]))
    changed, err = _apply(profile, body)
    if err:
        return jsonify(error="invalid", message=err), 400
    db.session.add(profile)
    db.session.flush()
    audit(current_user().id, "profile.create", "business_profile", profile.id)
    db.session.commit()
    return jsonify(profile=_owner_dict(profile)), 201


@bp.patch("/profiles/<int:profile_id>")
@roles_required("founder")
def update_profile(profile_id):
    profile = db.session.get(BusinessProfile, profile_id)
    # 404 (not 403) so other users' resource ids are not disclosed.
    if profile is None or profile.owner_id != current_user().id:
        return jsonify(error="not_found"), 404
    changed, err = _apply(profile, request.get_json(silent=True) or {})
    if err:
        return jsonify(error="invalid", message=err), 400
    if changed:
        db.session.add(BusinessProfileRevision(
            profile_id=profile.id, changed_by=current_user().id, changed_fields=changed))
        audit(current_user().id, "profile.update", "business_profile", profile.id,
              {"fields": list(changed)})
    db.session.commit()
    return jsonify(profile=_owner_dict(profile))


@bp.get("/profiles/<int:profile_id>/history")
@roles_required("founder")
def profile_history(profile_id):
    profile = db.session.get(BusinessProfile, profile_id)
    if profile is None or profile.owner_id != current_user().id:
        return jsonify(error="not_found"), 404
    revs = BusinessProfileRevision.query.filter_by(profile_id=profile_id).order_by(
        BusinessProfileRevision.id.desc()).all()
    return jsonify(history=[{"id": r.id, "changed_fields": r.changed_fields,
                             "created_at": r.created_at.isoformat()} for r in revs])


@bp.get("/public/businesses/<slug>")
def public_business(slug):
    """Public profile: only shown when the business has at least one published campaign."""
    from ..models import Campaign

    profile = BusinessProfile.query.filter_by(slug=slug).first()
    if profile is None or not Campaign.query.filter_by(profile_id=profile.id, status="published").first():
        return jsonify(error="not_found"), 404
    return jsonify(profile=public_profile_dict(profile))

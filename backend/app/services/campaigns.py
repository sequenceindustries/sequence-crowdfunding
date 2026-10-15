"""Campaign rules. Funding models are kept in a registry so one model's rules
cannot change another's behaviour."""
import re
import secrets

from flask import current_app

from ..extensions import db
from ..models import Campaign, User
from ..payments import active_mode
from .payments import funding_summary

EDITABLE_STATUSES = ("draft", "changes_requested")

# Per-model rules. 'investment' is registered but never enabled by configuration.
FUNDING_MODEL_RULES = {
    "donation": {"requires_reward_text": False, "returns_promised": False},
    "reward": {"requires_reward_text": True, "returns_promised": False},
    "business_support": {"requires_reward_text": False, "returns_promised": False},
    "investment": {"requires_reward_text": False, "returns_promised": True},
}

# Transitions: action -> (allowed from, resulting status)
MODERATION_TRANSITIONS = {
    "approve": (("submitted",), "approved"),
    "reject": (("submitted", "approved"), "rejected"),
    "request_changes": (("submitted",), "changes_requested"),
    "suspend": (("approved", "published"), "suspended"),
}

DRAFT_FIELDS = (
    "title", "category", "summary", "description", "location", "stage", "objectives",
    "funding_model", "currency", "goal_cents", "duration_days", "funding_purpose",
)


def slugify(text: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:60] or "item"
    return f"{base}-{secrets.token_hex(3)}"


def validate_use_of_funds(items):
    if items is None:
        return None, None
    if not isinstance(items, list) or len(items) > 30:
        return None, "use_of_funds must be a list of at most 30 items."
    cleaned = []
    for it in items:
        if not isinstance(it, dict):
            return None, "Each use_of_funds entry must be an object."
        label = str(it.get("item", "")).strip()[:200]
        amount = it.get("amount_cents")
        if not label or not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
            return None, "Each use_of_funds entry needs an item and a non-negative integer amount_cents."
        cleaned.append({"item": label, "amount_cents": amount})
    return cleaned, None


def submission_problems(campaign: Campaign, enabled_models):
    """Return blocking problems that stop a draft being submitted for review."""
    problems = []
    if not (campaign.title or "").strip():
        problems.append("A title is required.")
    if not (campaign.summary or "").strip():
        problems.append("A short summary is required.")
    if not (campaign.description or "").strip() or len(campaign.description) < 100:
        problems.append("A description of at least 100 characters is required.")
    if campaign.funding_model not in enabled_models:
        problems.append("Choose an available funding model.")
    if not campaign.goal_cents or campaign.goal_cents <= 0:
        problems.append("A funding goal greater than zero is required.")
    funds = campaign.use_of_funds or []
    if not funds:
        problems.append("A use-of-funds breakdown is required.")
    elif campaign.goal_cents and sum(i["amount_cents"] for i in funds) != campaign.goal_cents:
        problems.append("The use-of-funds total must equal the funding goal.")
    return problems


from .verification import verification_flags  # noqa: E402


def _owner_email_verified(c: Campaign) -> bool:
    owner = db.session.get(User, c.owner_id)
    return owner is not None and owner.email_verified_at is not None


def _logo_token(profile):
    if profile.logo_key:
        from ..api.images import make_public_image_token
        return make_public_image_token(profile.logo_key)
    return None


def campaign_to_dict(c: Campaign, public=False):
    data = {
        "id": c.id,
        "slug": c.slug,
        "title": c.title,
        "category": c.category,
        "summary": c.summary,
        "description": c.description,
        "location": c.location,
        "stage": c.stage,
        "objectives": c.objectives,
        "funding_model": c.funding_model,
        "currency": c.currency,
        "goal_cents": c.goal_cents,
        "duration_days": c.duration_days,
        "funding_purpose": c.funding_purpose,
        "use_of_funds": c.use_of_funds or [],
        "status": c.status,
        "published_at": c.published_at.isoformat() if c.published_at else None,
        "milestones": [
            {
                "title": m.title,
                "detail": m.detail,
                "target_date": m.target_date.isoformat() if m.target_date else None,
            }
            for m in c.milestones
        ],
        "business": {
            "slug": c.profile.slug,
            "name": c.profile.name,
            "industry": c.profile.industry,
            "logo_image_token": _logo_token(c.profile),
        },
        # Built only from confirmed, non-simulated payment records; zero until a live provider exists.
        "funding": {**funding_summary(c.id), "contributions_mode": active_mode()},
        "verification": {
            "email_verified": _owner_email_verified(c),
            **verification_flags(c.owner_id),
            "campaign_reviewed": c.status in ("approved", "published"),
            "financial_information_verified": False,
        },
    }
    from .transparency import public_view

    data["transparency"] = public_view(c)

    # Provide a short-lived signed token so the frontend can fetch the cover image
    # without exposing the raw storage key. Published campaigns use the public token
    # (no auth required); draft/private views use the same token for simplicity since
    # the token itself is the access control.
    if c.cover_image_key:
        from ..api.images import make_public_image_token
        data["cover_image_token"] = make_public_image_token(c.cover_image_key)
    else:
        data["cover_image_token"] = None

    if not public:
        data["review_note"] = c.review_note
        data["owner_id"] = c.owner_id
        data["profile_id"] = c.profile_id
    return data

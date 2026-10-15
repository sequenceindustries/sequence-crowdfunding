from flask import Blueprint, jsonify, request
from sqlalchemy import func

from ..extensions import db
from ..models import (
    AiUsage, AuditLog, Campaign, Follow, ModerationDecision, Payment, PaymentEvent, PitchDeck, User,
)
from ..security import current_user, roles_required
from ..services.audit import audit
from ..services.campaigns import MODERATION_TRANSITIONS, campaign_to_dict, slugify
from ..services.mail import send_mail

bp = Blueprint("admin", __name__, url_prefix="/api/admin")

REVIEW_ROLES = ("admin", "verification_reviewer")


@bp.get("/overview")
@roles_required("admin")
def overview():
    def count(status):
        return Campaign.query.filter_by(status=status).count()

    return jsonify(
        users=User.query.count(),
        founders=User.query.filter_by(role="founder").count(),
        campaigns=Campaign.query.count(),
        published=count("published"),
        drafts=count("draft"),
        awaiting_review=count("submitted"),
        suspended=count("suspended"),
        pitch_deck_uploads=PitchDeck.query.count(),
        ai_requests=AiUsage.query.count(),
        # Platform revenue = confirmed, real (non-simulated) pitch-deck fees. Contributions belong to
        # campaigns, not to the platform, and refunded or simulated payments are excluded.
        confirmed_revenue_cents=int(db.session.query(func.coalesce(func.sum(Payment.amount_cents), 0)).filter(
            Payment.kind == "pitch_deck_fee", Payment.status == "succeeded", Payment.simulated.is_(False)).scalar()),
        simulated_payments=Payment.query.filter_by(simulated=True).count(),
        unresolved_payment_events=PaymentEvent.query.filter(PaymentEvent.error.isnot(None)).count(),
    )


@bp.get("/review-queue")
@roles_required(*REVIEW_ROLES)
def review_queue():
    rows = Campaign.query.filter_by(status="submitted").order_by(Campaign.submitted_at).all()
    return jsonify(campaigns=[campaign_to_dict(c) for c in rows])


@bp.get("/campaigns/<int:campaign_id>")
@roles_required(*REVIEW_ROLES)
def campaign_detail(campaign_id):
    c = db.session.get(Campaign, campaign_id)
    if c is None:
        return jsonify(error="not_found"), 404
    history = ModerationDecision.query.filter_by(campaign_id=c.id).order_by(ModerationDecision.id).all()
    return jsonify(
        campaign=campaign_to_dict(c),
        moderation_history=[{"action": h.action, "reason": h.reason, "reviewer_id": h.reviewer_id,
                             "created_at": h.created_at.isoformat()} for h in history],
    )


@bp.post("/campaigns/<int:campaign_id>/decision")
@roles_required(*REVIEW_ROLES)
def decide(campaign_id):
    body = request.get_json(silent=True) or {}
    action = body.get("action")
    reason = str(body.get("reason", "")).strip()
    if action not in MODERATION_TRANSITIONS:
        return jsonify(error="invalid_action"), 400
    if not reason:  # every decision must carry a recorded reason
        return jsonify(error="reason_required"), 400
    c = db.session.get(Campaign, campaign_id)
    if c is None:
        return jsonify(error="not_found"), 404
    allowed_from, new_status = MODERATION_TRANSITIONS[action]
    if c.status not in allowed_from:
        return jsonify(error="invalid_transition",
                       message=f"Cannot {action} a campaign that is {c.status}."), 409
    reviewer = current_user()
    c.status = new_status
    c.review_note = reason
    c.slug = c.slug or slugify(c.title)
    db.session.add(ModerationDecision(campaign_id=c.id, reviewer_id=reviewer.id, action=action, reason=reason))
    audit(reviewer.id, f"campaign.{action}", "campaign", c.id, {"reason": reason})
    # Notify the campaign owner by email.
    owner = db.session.get(User, c.owner_id)
    if owner:
        if action == "approve":
            send_mail(owner.email, f"Your campaign '{c.title}' has been approved",
                      f"Good news — your campaign '{c.title}' has been approved by our review team.\n\n"
                      f"Log in to your dashboard and click Publish to make it live.\n\n"
                      f"Reviewer note: {reason}")
        elif action == "reject":
            send_mail(owner.email, f"Your campaign '{c.title}' was not approved",
                      f"Unfortunately your campaign '{c.title}' was not approved at this time.\n\n"
                      f"Reviewer note: {reason}\n\n"
                      f"You may edit your campaign and resubmit if you believe you can address this feedback.")
        elif action == "request_changes":
            send_mail(owner.email, f"Changes requested for your campaign '{c.title}'",
                      f"Our review team has reviewed '{c.title}' and is requesting changes before it can be approved.\n\n"
                      f"Reviewer note: {reason}\n\n"
                      f"Log in to your dashboard to edit your campaign and resubmit.")
    db.session.commit()
    return jsonify(campaign=campaign_to_dict(c))


@bp.get("/audit-log")
@roles_required("admin")
def audit_log():
    rows = AuditLog.query.order_by(AuditLog.id.desc()).limit(200).all()
    return jsonify(entries=[{"id": r.id, "actor_id": r.actor_id, "action": r.action,
                             "target_type": r.target_type, "target_id": r.target_id,
                             "created_at": r.created_at.isoformat()} for r in rows])


@bp.get("/users")
@roles_required("admin")
def list_users():
    rows = User.query.order_by(User.id).limit(500).all()
    return jsonify(users=[{"id": u.id, "email": u.email, "role": u.role, "is_active": u.is_active}
                          for u in rows])

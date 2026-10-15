import json
import re

import click
from flask import Blueprint, current_app, jsonify, request

from ..extensions import db, limiter
from ..models import Campaign, Payment, PaymentEvent, PitchDeck, Refund
from ..payments import active_mode, get_provider
from ..payments.base import sign_payload, signature_valid
from ..security import current_user, login_required, roles_required
from ..services.audit import audit
from ..services.campaigns import FUNDING_MODEL_RULES
from ..services.payments import (
    EventInvalid, IdempotencyConflict, create_payment, process_event, reconcile, request_refund,
)

bp = Blueprint("payments", __name__, url_prefix="/api")

KEY_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
MAX_WEBHOOK_BYTES = 64 * 1024
FEE_SERVICES = ("upload", "analysis", "package")  # services whose fee unlocks analysis of a deck


def payment_dict(p: Payment, include_ref=False):
    d = {"id": p.id, "kind": p.kind, "amount_cents": p.amount_cents, "currency": p.currency,
         "status": p.status, "simulated": p.simulated, "campaign_id": p.campaign_id,
         "pitch_deck_id": p.pitch_deck_id, "created_at": p.created_at.isoformat(),
         "label": "Test payment: no money moved." if p.simulated else None}
    if include_ref:
        d["provider_ref"] = p.provider_ref
    return d


def _idempotency_key():
    key = request.headers.get("Idempotency-Key", "")
    return key if KEY_RE.match(key) else None


def _amount(body):
    v = body.get("amount_cents")
    return v if isinstance(v, int) and not isinstance(v, bool) else None


@bp.post("/campaigns/<slug>/contributions")
@roles_required("supporter")
@limiter.limit("20 per hour")
def contribute(slug):
    mode = active_mode()
    if mode == "off":
        return jsonify(error="contributions_not_open",
                       message="Contributions are not open yet."), 409
    user = current_user()
    if user.email_verified_at is None:
        return jsonify(error="email_not_verified", message="Confirm your email address first."), 403
    campaign = Campaign.query.filter_by(slug=slug, status="published").first()
    if campaign is None:
        return jsonify(error="not_found"), 404
    rules = FUNDING_MODEL_RULES.get(campaign.funding_model)
    if rules is None or campaign.funding_model not in current_app.config["ENABLED_FUNDING_MODELS"]:
        return jsonify(error="funding_model_unavailable"), 409
    key = _idempotency_key()
    if key is None:
        return jsonify(error="idempotency_key_required",
                       message="Send an Idempotency-Key header of 8 to 64 letters, digits, _ or -."), 400
    body = request.get_json(silent=True) or {}
    amount = _amount(body)
    cfg = current_app.config
    if amount is None or not (cfg["CONTRIBUTION_MIN_CENTS"] <= amount <= cfg["CONTRIBUTION_MAX_CENTS"]):
        return jsonify(error="invalid_amount",
                       message=f"Amount must be between {cfg['CONTRIBUTION_MIN_CENTS']} and "
                               f"{cfg['CONTRIBUTION_MAX_CENTS']} cents."), 400
    if body.get("accept_terms") is not True:  # the supporter must knowingly agree
        return jsonify(error="terms_not_accepted",
                       message="Confirm you understand this supports a project and is not an investment."), 400
    try:
        payment, created = create_payment(kind="contribution", user=user, amount_cents=amount,
                                          idempotency_key=key, campaign=campaign)
    except IdempotencyConflict:
        db.session.rollback()
        return jsonify(error="idempotency_conflict",
                       message="That key was already used for a different request."), 409
    db.session.commit()
    out = {"contribution": payment_dict(payment, include_ref=payment.simulated),
           "checkout_url": payment.checkout_url, "mode": mode}
    return jsonify(out), 201 if created else 200


@bp.get("/contributions/mine")
@login_required
def my_contributions():
    rows = (db.session.query(Payment, Campaign.title, Campaign.slug)
            .join(Campaign, Campaign.id == Payment.campaign_id)
            .filter(Payment.user_id == current_user().id, Payment.kind == "contribution")
            .order_by(Payment.id.desc()).all())
    return jsonify(contributions=[{**payment_dict(p), "campaign_title": t, "campaign_slug": s} for p, t, s in rows])


# ---------- pitch-deck fee ----------

def fee_settings():
    cfg = current_app.config
    service = cfg["PITCH_DECK_FEE_SERVICE"]
    return {"amount_cents": cfg["PITCH_DECK_FEE_ZAR_CENTS"], "currency": "ZAR", "service": service,
            "covers": {"upload": ["analysis"], "analysis": ["analysis"], "package": ["analysis", "improvement_report"]}.get(
                service, []),
            "charging_enabled": bool(cfg["PITCH_DECK_FEE_CHARGING_ENABLED"] and service in FEE_SERVICES
                                     and active_mode() != "off"),
            "provisional": True}


@bp.get("/config/pitch-deck-fee")
def fee_config():
    s = fee_settings()
    s["note"] = ("No charge is made at present." if not s["charging_enabled"] else
                 "Charged once per deck, only after you confirm the amount.")
    return jsonify(s)


@bp.post("/pitch-decks/<int:deck_id>/fee-order")
@roles_required("founder")
@limiter.limit("10 per hour")
def fee_order(deck_id):
    s = fee_settings()
    if not s["charging_enabled"]:
        return jsonify(error="fees_not_enabled", message="There is nothing to pay for right now."), 409
    deck = db.session.get(PitchDeck, deck_id)
    if deck is None or deck.owner_id != current_user().id:
        return jsonify(error="not_found"), 404
    key = _idempotency_key()
    if key is None:
        return jsonify(error="idempotency_key_required"), 400
    body = request.get_json(silent=True) or {}
    # The founder confirms the exact amount, so a price change can never charge them unknowingly.
    if _amount(body) != s["amount_cents"] or body.get("accept_terms") is not True:
        return jsonify(error="confirmation_required", amount_cents=s["amount_cents"], covers=s["covers"],
                       message="Confirm the amount and what it covers."), 400
    active = Payment.query.filter(Payment.kind == "pitch_deck_fee", Payment.pitch_deck_id == deck.id,
                                  Payment.status.in_(("pending", "succeeded")),
                                  Payment.idempotency_key != key).first()
    if active is not None:
        return jsonify(error="fee_already_ordered"), 409
    try:
        payment, created = create_payment(kind="pitch_deck_fee", user=current_user(), amount_cents=s["amount_cents"],
                                          idempotency_key=key, deck=deck)
    except IdempotencyConflict:
        db.session.rollback()
        return jsonify(error="idempotency_conflict"), 409
    db.session.commit()
    return jsonify(payment=payment_dict(payment, include_ref=payment.simulated),
                   checkout_url=payment.checkout_url), 201 if created else 200


# ---------- webhook ----------

@bp.post("/webhooks/payments/<provider>")
@limiter.exempt
def webhook(provider):
    """The only way a payment's status can change."""
    if request.content_length is not None and request.content_length > MAX_WEBHOOK_BYTES:
        return jsonify(error="too_large"), 413
    raw = request.get_data(cache=False)
    secret = current_app.config["PAYMENT_WEBHOOK_SECRET"]
    if not secret:
        return jsonify(error="webhook_not_configured"), 503
    if not signature_valid(secret, raw, request.headers.get("X-Signature", "")):
        return jsonify(error="invalid_signature"), 401
    if provider != current_app.config["PAYMENT_PROVIDER"]:
        return jsonify(error="unknown_provider"), 404
    try:
        event = json.loads(raw)
        result = process_event(provider, event)
    except (ValueError, EventInvalid):  # json.JSONDecodeError is a ValueError
        db.session.rollback()
        return jsonify(error="invalid_event"), 400
    db.session.commit()
    return jsonify(result)


# ---------- admin ----------

@bp.get("/admin/payments")
@roles_required("admin")
def admin_payments():
    q = Payment.query
    for field in ("status", "kind"):
        if request.args.get(field):
            q = q.filter(getattr(Payment, field) == request.args[field])
    rows = q.order_by(Payment.id.desc()).limit(200).all()
    return jsonify(payments=[{**payment_dict(p, include_ref=True), "user_id": p.user_id} for p in rows])


@bp.post("/admin/payments/<int:payment_id>/refund")
@roles_required("admin")
def admin_refund(payment_id):
    payment = db.session.get(Payment, payment_id)
    reason = str((request.get_json(silent=True) or {}).get("reason", "")).strip()
    if payment is None:
        return jsonify(error="not_found"), 404
    if not reason:
        return jsonify(error="reason_required"), 400
    try:
        refund = request_refund(payment, reason, current_user().id)
    except ValueError as exc:
        db.session.rollback()
        return jsonify(error="refund_not_allowed", message=str(exc)), 409
    db.session.commit()
    return jsonify(refund={"id": refund.id, "status": refund.status, "amount_cents": refund.amount_cents}), 201


@bp.post("/admin/payments/reconcile")
@roles_required("admin")
def admin_reconcile():
    try:
        result = reconcile((request.get_json(silent=True) or {}).get("statement"),
                           current_app.config["PAYMENT_PROVIDER"])
    except ValueError as exc:
        return jsonify(error="invalid_statement", message=str(exc)), 400
    audit(current_user().id, "payment.reconcile", detail={"discrepancies": len(result["discrepancies"])})
    db.session.commit()
    return jsonify(result)


@bp.get("/admin/payment-events")
@roles_required("admin")
def admin_events():
    rows = PaymentEvent.query.filter(PaymentEvent.error.isnot(None)).order_by(PaymentEvent.id.desc()).limit(100).all()
    return jsonify(events=[{"id": e.id, "event_id": e.event_id, "type": e.event_type, "error": e.error,
                            "received_at": e.received_at.isoformat()} for e in rows])


def register_cli(app):
    @app.cli.command("mock-pay")
    @click.argument("provider_ref")
    @click.option("--event", "etype", default="payment.succeeded",
                  type=click.Choice(["payment.succeeded", "payment.failed", "payment.cancelled",
                                     "refund.succeeded", "refund.failed"]))
    def mock_pay(provider_ref, etype):
        """Deliver a signed mock-provider webhook (development only)."""
        import secrets

        if app.config["PAYMENT_PROVIDER"] != "mock":
            raise click.ClickException("Only available with the mock provider.")
        payment = Payment.query.filter_by(provider="mock", provider_ref=provider_ref).first()
        if payment is None:
            raise click.ClickException("No such mock payment.")
        raw = json.dumps({"id": "evt_" + secrets.token_hex(8), "type": etype, "provider_ref": provider_ref,
                          "amount_cents": payment.amount_cents}).encode()
        resp = app.test_client().post("/api/webhooks/payments/mock", data=raw, content_type="application/json",
                                      headers={"X-Signature": sign_payload(app.config["PAYMENT_WEBHOOK_SECRET"], raw)})
        click.echo(f"{resp.status_code} {resp.get_data(as_text=True).strip()}")

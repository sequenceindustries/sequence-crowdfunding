"""Payment state, webhooks, refunds and reconciliation.

Rules:
- A payment changes state only through a signed webhook event, never a browser redirect.
- Each event id is processed once.
- Amounts in an event must match the amount we recorded.
- Simulated payments are excluded from every figure shown as money raised or earned."""
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import Payment, PaymentEvent, Refund
from ..payments import get_provider
from .audit import audit

PAYMENT_EVENTS = {"payment.succeeded": "succeeded", "payment.failed": "failed", "payment.cancelled": "cancelled"}
REFUND_EVENTS = ("refund.succeeded", "refund.failed")
STATEMENT_STATUSES = ("pending", "succeeded", "failed", "cancelled", "refunded")


class EventInvalid(ValueError):
    pass


class IdempotencyConflict(Exception):
    pass


def _now():
    return datetime.now(timezone.utc)


def create_payment(*, kind, user, amount_cents, idempotency_key, campaign=None, deck=None):
    """Create a pending payment. Returns (payment, created). Replaying the same key returns the original."""
    existing = Payment.query.filter_by(user_id=user.id, idempotency_key=idempotency_key).first()

    def same(p):
        return (p.kind, p.amount_cents, p.campaign_id, p.pitch_deck_id) == (
            kind, amount_cents, campaign.id if campaign else None, deck.id if deck else None)

    if existing is not None:
        if not same(existing):
            raise IdempotencyConflict()
        return existing, False
    provider = get_provider()
    payment = Payment(kind=kind, user_id=user.id, amount_cents=amount_cents, status="pending",
                      provider=provider.name, simulated=provider.simulated, idempotency_key=idempotency_key,
                      campaign_id=campaign.id if campaign else None, pitch_deck_id=deck.id if deck else None,
                      provider_ref="pending")
    checkout = provider.create_checkout(payment)
    payment.provider_ref, payment.checkout_url = checkout["provider_ref"], checkout.get("checkout_url")
    db.session.add(payment)
    try:
        db.session.flush()
    except IntegrityError:  # two identical requests raced; the other one won
        db.session.rollback()
        winner = Payment.query.filter_by(user_id=user.id, idempotency_key=idempotency_key).first()
        if winner is None or not same(winner):
            raise IdempotencyConflict()
        return winner, False
    audit(user.id, f"payment.create.{kind}", "payment", payment.id,
          {"amount_cents": amount_cents, "simulated": payment.simulated})
    return payment, True


def process_event(provider_name: str, event) -> dict:
    """Apply one verified webhook event. The caller commits."""
    if not isinstance(event, dict):
        raise EventInvalid("Event must be an object.")
    eid, etype, ref, amount = (event.get("id"), event.get("type"), event.get("provider_ref"),
                               event.get("amount_cents"))
    if not (isinstance(eid, str) and 0 < len(eid) <= 120 and isinstance(ref, str) and 0 < len(ref) <= 80):
        raise EventInvalid("Event needs a string id and provider_ref.")
    if etype not in PAYMENT_EVENTS and etype not in REFUND_EVENTS:
        raise EventInvalid("Unsupported event type.")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        raise EventInvalid("amount_cents must be a non-negative whole number.")

    record = PaymentEvent(provider=provider_name, event_id=eid, event_type=etype, payload=event)
    db.session.add(record)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return {"status": "duplicate"}

    payment = Payment.query.filter_by(provider=provider_name, provider_ref=ref).with_for_update().first()
    if payment is None:
        record.error = "unknown_payment"
        return {"status": "unmatched"}
    if amount != payment.amount_cents:
        # Never apply an event that disagrees with what we asked the customer to pay.
        record.error = "amount_mismatch"
        audit(None, "payment.amount_mismatch", "payment", payment.id,
              {"expected": payment.amount_cents, "received": amount, "event": eid})
        return {"status": "rejected", "reason": "amount_mismatch"}

    if etype in PAYMENT_EVENTS:
        if payment.status != "pending":
            record.error = "ignored_out_of_order"
            record.processed = True
            return {"status": "ignored", "reason": f"payment is already {payment.status}"}
        payment.status = PAYMENT_EVENTS[etype]
        if payment.status == "succeeded":
            payment.confirmed_at = _now()
    else:
        refund = Refund.query.filter_by(payment_id=payment.id, status="requested").first()
        if refund is None or payment.status != "succeeded":
            record.error = "refund_not_expected"
            record.processed = True
            return {"status": "ignored", "reason": "no matching refund request"}
        refund.completed_at = _now()
        if etype == "refund.succeeded":
            refund.status, payment.status = "succeeded", "refunded"
        else:
            refund.status = "failed"
    record.processed = True
    audit(None, f"payment.{etype}", "payment", payment.id, {"event": eid, "simulated": payment.simulated})
    return {"status": "applied", "payment_status": payment.status}


def request_refund(payment: Payment, reason: str, admin_id: int) -> Refund:
    if payment.status != "succeeded":
        raise ValueError("Only a succeeded payment can be refunded.")
    if Refund.query.filter(Refund.payment_id == payment.id, Refund.status.in_(("requested", "succeeded"))).first():
        raise ValueError("A refund is already requested or completed for this payment.")
    get_provider().request_refund(payment, payment.amount_cents)
    refund = Refund(payment_id=payment.id, amount_cents=payment.amount_cents, reason=reason, requested_by=admin_id)
    db.session.add(refund)
    db.session.flush()
    audit(admin_id, "payment.refund_requested", "payment", payment.id, {"reason": reason})
    return refund


def funding_summary(campaign_id: int) -> dict:
    """Money for a campaign, from real (non-simulated) contribution records only."""
    rows = db.session.query(Payment.status, func.coalesce(func.sum(Payment.amount_cents), 0)).filter(
        Payment.campaign_id == campaign_id, Payment.kind == "contribution", Payment.simulated.is_(False),
    ).group_by(Payment.status).all()
    by = {status: int(total) for status, total in rows}
    return {
        "confirmed_raised_cents": by.get("succeeded", 0),
        "pending_cents": by.get("pending", 0),
        "refunded_cents": by.get("refunded", 0),
        "cancelled_or_failed_cents": by.get("failed", 0) + by.get("cancelled", 0),
        "pledged_cents": 0,
    }


def fee_satisfied(deck_id: int) -> bool:
    return db.session.query(Payment.id).filter(
        Payment.kind == "pitch_deck_fee", Payment.pitch_deck_id == deck_id, Payment.status == "succeeded",
    ).first() is not None


def reconcile(statement, provider_name: str) -> dict:
    """Compare a provider settlement statement with our records."""
    if not isinstance(statement, list) or len(statement) > 5000:
        raise ValueError("statement must be a list of at most 5000 rows.")
    local = {p.provider_ref: p for p in Payment.query.filter_by(provider=provider_name)}
    seen, findings, matched = set(), [], 0
    for row in statement:
        if not isinstance(row, dict) or not isinstance(row.get("provider_ref"), str) \
                or isinstance(row.get("amount_cents"), bool) or not isinstance(row.get("amount_cents"), int) \
                or row.get("status") not in STATEMENT_STATUSES:
            raise ValueError("Each row needs provider_ref, whole-number amount_cents and a valid status.")
        ref = row["provider_ref"]
        if ref in seen:
            findings.append({"code": "duplicate_in_statement", "provider_ref": ref})
            continue
        seen.add(ref)
        payment = local.get(ref)
        if payment is None:
            findings.append({"code": "missing_locally", "provider_ref": ref})
            continue
        problems = []
        if payment.amount_cents != row["amount_cents"]:
            problems.append({"code": "amount_mismatch", "provider_ref": ref,
                             "local": payment.amount_cents, "provider": row["amount_cents"]})
        if payment.status != row["status"]:
            problems.append({"code": "status_mismatch", "provider_ref": ref,
                             "local": payment.status, "provider": row["status"]})
        findings.extend(problems)
        matched += 0 if problems else 1
    for ref, payment in local.items():
        if ref not in seen and payment.status in ("succeeded", "refunded"):
            findings.append({"code": "missing_at_provider", "provider_ref": ref, "local_status": payment.status})
    return {"rows_checked": len(statement), "matched": matched, "discrepancies": findings}

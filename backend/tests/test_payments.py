import json

import pytest

from app.extensions import db
from app.models import Payment, PaymentEvent, Refund
from app.payments import register_provider
from app.payments.base import PaymentProvider
from conftest import send_event, text_pdf
from test_pitch_decks import GOOD_TEXT, upload


class FakeLive(PaymentProvider):
    """Stands in for an approved real provider so live-money accounting can be tested."""

    name, simulated = "fakelive", False
    counter = 0

    def create_checkout(self, payment):
        FakeLive.counter += 1
        return {"provider_ref": f"live_{FakeLive.counter:04d}", "checkout_url": "https://pay.example/checkout"}

    def request_refund(self, payment, amount_cents):
        return {"provider_refund_ref": "rf"}


def pay(client, slug, amount=10_000, key="key-0001-abcd", **extra):
    return client.c.post(f"/api/campaigns/{slug}/contributions", json={"amount_cents": amount, "accept_terms": True, **extra},
                         headers={"X-CSRF-Token": client.csrf, "Idempotency-Key": key})


def evt(ref, etype="payment.succeeded", amount=10_000, eid=None):
    return {"id": eid or f"evt_{ref}_{etype}", "type": etype, "provider_ref": ref, "amount_cents": amount}


@pytest.fixture()
def simulated(app):
    app.config["CONTRIBUTIONS_MODE"] = "simulated"


@pytest.fixture()
def live(app):
    register_provider("fakelive", FakeLive)
    app.config.update(PAYMENT_PROVIDER="fakelive", CONTRIBUTIONS_MODE="live")


def ref_of(resp):
    return db.session.get(Payment, resp.json["contribution"]["id"]).provider_ref


# ----- modes -----

def test_contributions_closed_by_default(supporter, published_campaign):
    r = pay(supporter, published_campaign["slug"])
    assert r.status_code == 409 and r.json["error"] == "contributions_not_open"
    assert Payment.query.count() == 0


def test_mode_must_match_provider_kind(app, supporter, published_campaign):
    app.config["CONTRIBUTIONS_MODE"] = "live"  # mock provider is simulated, so "live" is refused
    assert pay(supporter, published_campaign["slug"]).status_code == 409
    register_provider("fakelive", FakeLive)
    app.config.update(PAYMENT_PROVIDER="fakelive", CONTRIBUTIONS_MODE="simulated")  # live provider can't be "test mode"
    assert pay(supporter, published_campaign["slug"]).status_code == 409
    app.config["CONTRIBUTIONS_MODE"] = "banana"
    assert pay(supporter, published_campaign["slug"]).status_code == 409


# ----- creating contributions -----

def test_simulated_contribution_is_pending_labelled_and_never_counted(app, simulated, supporter, client, published_campaign):
    slug = published_campaign["slug"]
    r = pay(supporter, slug)
    assert r.status_code == 201
    c = r.json["contribution"]
    assert c["status"] == "pending" and c["simulated"] is True and "no money moved" in c["label"]
    assert send_event(app, evt(c["provider_ref"])).json["status"] == "applied"
    mine = supporter.get("/api/contributions/mine").json["contributions"][0]
    assert mine["status"] == "succeeded" and mine["simulated"] is True and mine["campaign_slug"] == slug
    f = client.get(f"/api/public/campaigns/{slug}").json["campaign"]["funding"]
    assert f["confirmed_raised_cents"] == 0 and f["pending_cents"] == 0  # simulated money is not money
    assert f["contributions_mode"] == "simulated"


def test_validation(app, simulated, supporter, founder, client, published_campaign):
    slug = published_campaign["slug"]
    assert pay(supporter, slug, amount=1999).status_code == 400
    assert pay(supporter, slug, amount=5_000_001).status_code == 400
    assert pay(supporter, slug, amount=100.5).status_code == 400
    assert pay(supporter, slug, amount=True).status_code == 400
    assert pay(supporter, slug, amount="500").status_code == 400
    assert supporter.c.post(f"/api/campaigns/{slug}/contributions", json={"amount_cents": 5000, "accept_terms": True},
                            headers={"X-CSRF-Token": supporter.csrf}).json["error"] == "idempotency_key_required"
    assert supporter.c.post(f"/api/campaigns/{slug}/contributions", json={"amount_cents": 5000, "accept_terms": True},
                            headers={"X-CSRF-Token": supporter.csrf, "Idempotency-Key": "bad key!"}).status_code == 400
    r = supporter.c.post(f"/api/campaigns/{slug}/contributions", json={"amount_cents": 5000},
                         headers={"X-CSRF-Token": supporter.csrf, "Idempotency-Key": "key-0002-abcd"})
    assert r.status_code == 400 and r.json["error"] == "terms_not_accepted"
    assert pay(supporter, "no-such-campaign").status_code == 404
    assert pay(founder, slug).status_code == 403  # founders do not contribute
    assert client.post(f"/api/campaigns/{slug}/contributions", {"amount_cents": 5000}).status_code == 401
    assert Payment.query.count() == 0


def test_unpublished_or_unverified_blocked(app, simulated, make_client, founder, submitted_campaign):
    cid = submitted_campaign  # submitted, not published
    slug = founder.get(f"/api/campaigns/{cid}").json["campaign"]["slug"]
    s = make_client()
    s.register("unverified@example.com", role="supporter")
    assert pay(s, slug or "x").status_code == 403  # email not confirmed comes first
    from conftest import verify_user
    verify_user("unverified@example.com")
    assert pay(s, slug or "x").status_code == 404  # not published


def test_idempotency(app, simulated, supporter, published_campaign):
    slug = published_campaign["slug"]
    first = pay(supporter, slug, key="same-key-1234")
    again = pay(supporter, slug, key="same-key-1234")
    assert first.status_code == 201 and again.status_code == 200
    assert first.json["contribution"]["id"] == again.json["contribution"]["id"]
    assert Payment.query.count() == 1
    clash = pay(supporter, slug, amount=99_999, key="same-key-1234")
    assert clash.status_code == 409 and clash.json["error"] == "idempotency_conflict"
    assert pay(supporter, slug, key="other-key-5678").status_code == 201 and Payment.query.count() == 2


def test_users_only_see_their_own_contributions(app, simulated, make_client, supporter, published_campaign):
    pay(supporter, published_campaign["slug"])
    from conftest import verify_user
    other = make_client()
    other.register("other-backer@example.com", role="supporter")
    verify_user("other-backer@example.com")
    assert other.get("/api/contributions/mine").json["contributions"] == []
    assert len(supporter.get("/api/contributions/mine").json["contributions"]) == 1


# ----- webhook security -----

def test_webhook_rejects_unsigned_and_tampered(app, simulated, supporter, published_campaign):
    ref = ref_of(pay(supporter, published_campaign["slug"]))
    body = json.dumps(evt(ref)).encode()
    assert send_event(app, None, raw=body, signature="").status_code == 401
    assert send_event(app, None, raw=body, signature="sha256=" + "0" * 64).status_code == 401
    assert send_event(app, None, raw=body, signature="é").status_code == 401  # non-ascii header must not crash
    assert send_event(app, evt(ref), secret="wrong-secret").status_code == 401
    good = send_event(app, evt(ref)).get_data()
    tampered = body.replace(b"10000", b"10001")
    from app.payments.base import sign_payload
    assert send_event(app, None, raw=tampered, signature=sign_payload("test-webhook-secret", body)).status_code == 401
    assert Payment.query.first().status == "succeeded" and good


def test_webhook_refuses_everything_without_a_configured_secret(app, simulated, supporter, published_campaign):
    ref = ref_of(pay(supporter, published_campaign["slug"]))
    app.config["PAYMENT_WEBHOOK_SECRET"] = ""
    assert send_event(app, evt(ref), secret="").status_code == 503
    assert send_event(app, evt(ref), secret="anything").status_code == 503
    assert Payment.query.first().status == "pending"


def test_webhook_unknown_provider_and_malformed_events(app, simulated, supporter, published_campaign):
    ref = ref_of(pay(supporter, published_campaign["slug"]))
    assert send_event(app, evt(ref), provider="stripe").status_code == 404
    for bad in (b"not json", b"[]", b"{}", json.dumps({**evt(ref), "type": "payment.exploded"}).encode(),
                json.dumps({**evt(ref), "amount_cents": "10000"}).encode(),
                json.dumps({**evt(ref), "amount_cents": True}).encode(),
                json.dumps({**evt(ref), "amount_cents": -5}).encode(),
                json.dumps({**evt(ref), "id": ""}).encode()):
        assert send_event(app, None, raw=bad).status_code == 400, bad
    assert send_event(app, None, raw=b"x" * 70_000).status_code == 413
    assert Payment.query.first().status == "pending" and PaymentEvent.query.count() == 0


def test_browser_requests_cannot_confirm_payments(app, simulated, supporter, published_campaign):
    r = pay(supporter, published_campaign["slug"])
    pid = r.json["contribution"]["id"]
    for path in (f"/api/contributions/{pid}/confirm", f"/api/payments/{pid}/succeeded", "/api/webhooks/payments/mock"):
        assert supporter.post(path, {"status": "succeeded"}).status_code in (401, 404, 405)
    assert supporter.get("/api/contributions/mine").json["contributions"][0]["status"] == "pending"


# ----- webhook processing -----

def test_duplicate_events_apply_once(app, simulated, supporter, published_campaign):
    ref = ref_of(pay(supporter, published_campaign["slug"]))
    assert send_event(app, evt(ref, eid="evt_1")).json["status"] == "applied"
    assert send_event(app, evt(ref, eid="evt_1")).json["status"] == "duplicate"
    assert PaymentEvent.query.count() == 1
    assert Payment.query.first().status == "succeeded"


def test_out_of_order_and_conflicting_outcomes_ignored(app, simulated, supporter, published_campaign):
    ref = ref_of(pay(supporter, published_campaign["slug"]))
    send_event(app, evt(ref, "payment.succeeded", eid="e1"))
    late_fail = send_event(app, evt(ref, "payment.failed", eid="e2")).json
    assert late_fail["status"] == "ignored" and Payment.query.first().status == "succeeded"


def test_failed_and_cancelled_payments(app, simulated, supporter, published_campaign):
    r1 = pay(supporter, published_campaign["slug"], key="fail-key-0001")
    r2 = pay(supporter, published_campaign["slug"], key="cancel-key-001")
    send_event(app, evt(ref_of(r1), "payment.failed"))
    send_event(app, evt(ref_of(r2), "payment.cancelled"))
    assert sorted(p.status for p in Payment.query.all()) == ["cancelled", "failed"]
    assert all(p.confirmed_at is None for p in Payment.query.all())


def test_amount_mismatch_is_rejected_and_surfaced(app, simulated, admin, supporter, published_campaign):
    ref = ref_of(pay(supporter, published_campaign["slug"], amount=10_000))
    r = send_event(app, evt(ref, amount=999_999)).json
    assert r["status"] == "rejected" and r["reason"] == "amount_mismatch"
    assert Payment.query.first().status == "pending"
    events = admin.get("/api/admin/payment-events").json["events"]
    assert events[0]["error"] == "amount_mismatch"
    assert admin.get("/api/admin/overview").json["unresolved_payment_events"] == 1


def test_unknown_payment_recorded_not_applied(app, simulated, admin):
    assert send_event(app, evt("mock_doesnotexist")).json["status"] == "unmatched"
    assert admin.get("/api/admin/payment-events").json["events"][0]["error"] == "unknown_payment"


# ----- live money accounting (fake approved provider) -----

def test_live_money_is_counted_and_buckets_stay_distinct(app, live, client, supporter, published_campaign):
    slug = published_campaign["slug"]
    ok = pay(supporter, slug, 100_000, "live-key-0001")
    pending = pay(supporter, slug, 20_000, "live-key-0002")
    failed = pay(supporter, slug, 30_000, "live-key-0003")
    assert ok.json["contribution"]["simulated"] is False and ok.json["contribution"]["label"] is None
    assert "provider_ref" not in ok.json["contribution"] and ok.json["checkout_url"].startswith("https://")
    send_event(app, evt(ref_of(ok), amount=100_000), provider="fakelive")
    send_event(app, evt(ref_of(failed), "payment.failed", amount=30_000), provider="fakelive")
    f = client.get(f"/api/public/campaigns/{slug}").json["campaign"]["funding"]
    assert (f["confirmed_raised_cents"], f["pending_cents"], f["cancelled_or_failed_cents"], f["refunded_cents"]) == (
        100_000, 20_000, 30_000, 0)
    assert f["contributions_mode"] == "live" and pending.status_code == 201


def test_refund_flow_waits_for_provider_confirmation(app, live, admin, client, supporter, published_campaign):
    slug = published_campaign["slug"]
    r = pay(supporter, slug, 100_000)
    ref, pid = ref_of(r), r.json["contribution"]["id"]
    assert admin.post(f"/api/admin/payments/{pid}/refund", {"reason": "x"}).status_code == 409  # still pending
    send_event(app, evt(ref, amount=100_000), provider="fakelive")
    assert admin.post(f"/api/admin/payments/{pid}/refund", {}).status_code == 400  # reason required
    assert admin.post(f"/api/admin/payments/{pid}/refund", {"reason": "Supporter request"}).status_code == 201
    assert admin.post(f"/api/admin/payments/{pid}/refund", {"reason": "again"}).status_code == 409
    funding = lambda: client.get(f"/api/public/campaigns/{slug}").json["campaign"]["funding"]
    assert funding()["confirmed_raised_cents"] == 100_000  # not refunded until the provider says so
    send_event(app, evt(ref, "refund.succeeded", amount=100_000, eid="rf1"), provider="fakelive")
    assert funding()["confirmed_raised_cents"] == 0 and funding()["refunded_cents"] == 100_000
    assert Refund.query.first().status == "succeeded" and Payment.query.first().status == "refunded"


def test_refund_failure_keeps_payment_and_unexpected_refund_ignored(app, live, admin, supporter, published_campaign):
    r = pay(supporter, published_campaign["slug"], 100_000)
    ref, pid = ref_of(r), r.json["contribution"]["id"]
    send_event(app, evt(ref, amount=100_000), provider="fakelive")
    assert send_event(app, evt(ref, "refund.succeeded", amount=100_000, eid="rf0"), provider="fakelive").json["status"] == "ignored"
    assert Payment.query.first().status == "succeeded"  # nobody asked for a refund
    admin.post(f"/api/admin/payments/{pid}/refund", {"reason": "try"})
    send_event(app, evt(ref, "refund.failed", amount=100_000, eid="rf2"), provider="fakelive")
    assert Payment.query.first().status == "succeeded" and Refund.query.first().status == "failed"
    assert admin.post(f"/api/admin/payments/{pid}/refund", {"reason": "retry"}).status_code == 201


def test_refunds_and_payment_lists_are_admin_only(app, live, founder, supporter, reviewer, published_campaign):
    pid = pay(supporter, published_campaign["slug"]).json["contribution"]["id"]
    for who in (founder, supporter, reviewer):
        assert who.post(f"/api/admin/payments/{pid}/refund", {"reason": "x"}).status_code == 403
        assert who.get("/api/admin/payments").status_code == 403
        assert who.post("/api/admin/payments/reconcile", {"statement": []}).status_code == 403


# ----- reconciliation -----

def test_reconciliation_finds_every_kind_of_discrepancy(app, live, admin, supporter, published_campaign):
    slug = published_campaign["slug"]
    a, b, c, d = (pay(supporter, slug, 10_000 + i, f"rec-key-000{i}") for i in range(4))
    refs = [ref_of(x) for x in (a, b, c, d)]
    for ref, amt in zip(refs[:3], (10_000, 10_001, 10_002)):
        send_event(app, evt(ref, amount=amt), provider="fakelive")
    statement = [
        {"provider_ref": refs[0], "amount_cents": 10_000, "status": "succeeded"},   # matches
        {"provider_ref": refs[1], "amount_cents": 99, "status": "succeeded"},       # amount differs
        {"provider_ref": refs[0], "amount_cents": 10_000, "status": "succeeded"},   # duplicate row
        {"provider_ref": "live_9999", "amount_cents": 5, "status": "succeeded"},    # we have no record
        {"provider_ref": refs[3], "amount_cents": 10_003, "status": "succeeded"},   # we think it's pending
    ]                                                                               # refs[2] is absent: succeeded here only
    out = admin.post("/api/admin/payments/reconcile", {"statement": statement}).json
    codes = sorted(f["code"] for f in out["discrepancies"])
    assert codes == ["amount_mismatch", "duplicate_in_statement", "missing_at_provider", "missing_locally", "status_mismatch"]
    assert out["matched"] == 1 and out["rows_checked"] == 5


def test_reconciliation_clean_and_input_validation(app, live, admin, supporter, published_campaign):
    r = pay(supporter, published_campaign["slug"])
    send_event(app, evt(ref_of(r)), provider="fakelive")
    ok = admin.post("/api/admin/payments/reconcile",
                    {"statement": [{"provider_ref": ref_of(r), "amount_cents": 10_000, "status": "succeeded"}]}).json
    assert ok["discrepancies"] == [] and ok["matched"] == 1
    for bad in (None, "x", [1], [{"provider_ref": "a"}], [{"provider_ref": "a", "amount_cents": 1.5, "status": "succeeded"}],
                [{"provider_ref": "a", "amount_cents": 1, "status": "weird"}]):
        assert admin.post("/api/admin/payments/reconcile", {"statement": bad}).status_code == 400


# ----- pitch-deck fee -----

@pytest.fixture()
def fees_on(app, simulated):
    app.config["PITCH_DECK_FEE_CHARGING_ENABLED"] = True


def order(c, deck_id, amount=50_000, key="fee-key-0001", terms=True):
    body = {"amount_cents": amount}
    if terms:
        body["accept_terms"] = True
    return c.c.post(f"/api/pitch-decks/{deck_id}/fee-order", json=body,
                    headers={"X-CSRF-Token": c.csrf, "Idempotency-Key": key})


def test_no_charging_and_free_analysis_while_disabled(founder):
    did = upload(founder, text_pdf(GOOD_TEXT)).json["pitch_deck"]["id"]
    assert order(founder, did).status_code == 409
    assert founder.post(f"/api/pitch-decks/{did}/analyse", {}).status_code == 201
    cfg = founder.get("/api/config/pitch-deck-fee").json
    assert cfg["charging_enabled"] is False and cfg["amount_cents"] == 50_000 and cfg["covers"] == ["analysis", "improvement_report"]


def test_charging_needs_flag_service_and_a_payment_mode(app, founder):
    app.config["PITCH_DECK_FEE_CHARGING_ENABLED"] = True
    assert founder.get("/api/config/pitch-deck-fee").json["charging_enabled"] is False  # mode is off
    app.config["CONTRIBUTIONS_MODE"] = "simulated"
    assert founder.get("/api/config/pitch-deck-fee").json["charging_enabled"] is True
    app.config["PITCH_DECK_FEE_SERVICE"] = "unconfigured"
    assert founder.get("/api/config/pitch-deck-fee").json["charging_enabled"] is False
    app.config["PITCH_DECK_FEE_SERVICE"] = "generation"  # not implemented, so it must not charge
    assert founder.get("/api/config/pitch-deck-fee").json["charging_enabled"] is False


def test_fee_must_be_paid_before_analysis_and_is_never_charged_unknowingly(app, fees_on, founder):
    did = upload(founder, text_pdf(GOOD_TEXT)).json["pitch_deck"]["id"]
    blocked = founder.post(f"/api/pitch-decks/{did}/analyse", {})
    assert blocked.status_code == 402 and blocked.json["amount_cents"] == 50_000
    assert order(founder, did, terms=False).status_code == 400
    assert order(founder, did, amount=49_999).status_code == 400  # stale price is refused
    assert order(founder, did, amount=65_000).json["error"] == "confirmation_required"
    assert Payment.query.count() == 0
    r = order(founder, did)
    assert r.status_code == 201 and r.json["payment"]["status"] == "pending"
    assert founder.post(f"/api/pitch-decks/{did}/analyse", {}).status_code == 402  # pending is not paid
    assert order(founder, did, key="fee-key-0002").json["error"] == "fee_already_ordered"
    assert order(founder, did).status_code == 200  # same key replays, no second charge
    send_event(app, evt(Payment.query.first().provider_ref, amount=50_000))
    assert founder.post(f"/api/pitch-decks/{did}/analyse", {}).status_code == 201
    assert order(founder, did, key="fee-key-0003").json["error"] == "fee_already_ordered"


def test_failed_fee_payment_allows_a_new_order(app, fees_on, founder):
    did = upload(founder, text_pdf(GOOD_TEXT)).json["pitch_deck"]["id"]
    order(founder, did)
    send_event(app, evt(Payment.query.first().provider_ref, "payment.failed", amount=50_000))
    assert founder.post(f"/api/pitch-decks/{did}/analyse", {}).status_code == 402
    assert order(founder, did, key="fee-key-0009").status_code == 201


def test_fee_is_per_deck_and_owner_only(app, fees_on, founder, other_founder):
    d1 = upload(founder, text_pdf(GOOD_TEXT)).json["pitch_deck"]["id"]
    d2 = upload(founder, text_pdf(GOOD_TEXT)).json["pitch_deck"]["id"]
    assert order(other_founder, d1).status_code == 404
    order(founder, d1)
    send_event(app, evt(Payment.query.first().provider_ref, amount=50_000))
    assert founder.post(f"/api/pitch-decks/{d1}/analyse", {}).status_code == 201
    assert founder.post(f"/api/pitch-decks/{d2}/analyse", {}).status_code == 402


def test_revenue_counts_only_confirmed_real_fees(app, live, admin, founder):
    app.config["PITCH_DECK_FEE_CHARGING_ENABLED"] = True
    d1 = upload(founder, text_pdf(GOOD_TEXT)).json["pitch_deck"]["id"]
    d2 = upload(founder, text_pdf(GOOD_TEXT)).json["pitch_deck"]["id"]
    order(founder, d1, key="rev-key-0001")
    order(founder, d2, key="rev-key-0002")
    p1, p2 = Payment.query.order_by(Payment.id).all()
    assert admin.get("/api/admin/overview").json["confirmed_revenue_cents"] == 0  # nothing confirmed yet
    send_event(app, evt(p1.provider_ref, amount=50_000), provider="fakelive")
    assert admin.get("/api/admin/overview").json["confirmed_revenue_cents"] == 50_000
    assert p2.status == "pending"
    admin.post(f"/api/admin/payments/{p1.id}/refund", {"reason": "dispute"})
    send_event(app, evt(p1.provider_ref, "refund.succeeded", amount=50_000, eid="rr"), provider="fakelive")
    assert admin.get("/api/admin/overview").json["confirmed_revenue_cents"] == 0


def test_simulated_fees_unlock_testing_but_are_never_revenue(app, fees_on, admin, founder):
    did = upload(founder, text_pdf(GOOD_TEXT)).json["pitch_deck"]["id"]
    order(founder, did)
    send_event(app, evt(Payment.query.first().provider_ref, amount=50_000))
    ov = admin.get("/api/admin/overview").json
    assert ov["confirmed_revenue_cents"] == 0 and ov["simulated_payments"] == 1


def test_admin_payment_list_filters(app, simulated, admin, supporter, published_campaign):
    pay(supporter, published_campaign["slug"])
    rows = admin.get("/api/admin/payments?kind=contribution&status=pending").json["payments"]
    assert len(rows) == 1 and rows[0]["simulated"] is True
    assert admin.get("/api/admin/payments?status=refunded").json["payments"] == []


def test_mock_pay_cli_delivers_a_signed_webhook(app, simulated, supporter, published_campaign):
    ref = ref_of(pay(supporter, published_campaign["slug"]))
    result = app.test_cli_runner().invoke(args=["mock-pay", ref])
    assert result.exit_code == 0 and "applied" in result.output
    assert Payment.query.first().status == "succeeded"
    bad = app.test_cli_runner().invoke(args=["mock-pay", "mock_nope"])
    assert bad.exit_code != 0

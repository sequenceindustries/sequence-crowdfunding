from app.ai import register_provider
from app.ai.base import AiProvider
from app.models import AiUsage, AuditLog
from conftest import complete_campaign_payload, make_profile, minimal_pdf

import io


def mk(founder, **over):
    p = make_profile(founder)
    payload = {**complete_campaign_payload(p["id"]), **over}
    return founder.post("/api/campaigns", payload).json["campaign"]["id"]


def review(c, cid):
    return c.post(f"/api/campaigns/{cid}/assistant/review", {})


def test_review_flags_return_claims_and_unsourced_figures(founder):
    cid = mk(founder, description="Guaranteed returns of 20% for early backers, risk-free! Act now. " * 6)
    rep = review(founder, cid).json["report"]
    phrases = {f["phrase"] for f in rep["compliance_flags"]}
    assert "guaranteed" in phrases and "risk-free" in phrases
    msgs = " ".join(c["message"] for c in rep["checks"])
    assert "no source" in msgs and "pressure language" in msgs
    assert any("not independently" in d or "cannot tell" in d for d in rep["disclaimers"])


def test_review_is_quiet_about_a_clean_campaign_and_does_not_change_it(founder):
    cid = mk(founder)
    before = founder.get(f"/api/campaigns/{cid}").json["campaign"]
    rep = review(founder, cid).json["report"]
    assert rep["compliance_flags"] == [] and rep["strengths"]
    assert founder.get(f"/api/campaigns/{cid}").json["campaign"] == before


def test_review_ownership_roles_and_usage_logging(founder, other_founder, supporter, client):
    cid = mk(founder)
    assert review(other_founder, cid).status_code == 404
    assert review(supporter, cid).status_code == 403
    assert review(client, cid).status_code == 401
    review(founder, cid)
    assert AiUsage.query.filter_by(feature="campaign_review").count() == 1


def test_external_provider_is_refused_without_consent_path(app, founder):
    class Ext(AiProvider):
        name, external = "ext", True

        def analyze_pitch_deck(self, text):
            return {}

    register_provider("ext", Ext)
    app.config["AI_PROVIDER"] = "ext"
    cid = mk(founder)
    assert review(founder, cid).json["error"] == "consent_required"


def test_provider_without_capability_gives_501(app, founder):
    class Bare(AiProvider):
        name = "bare"

        def analyze_pitch_deck(self, text):
            return {}

    register_provider("bare", Bare)
    app.config["AI_PROVIDER"] = "bare"
    assert review(founder, mk(founder)).status_code == 501


def publish(founder, admin, cid):
    founder.post(f"/api/campaigns/{cid}/submit")
    admin.post(f"/api/admin/campaigns/{cid}/decision", {"action": "approve", "reason": "ok"})
    assert founder.post(f"/api/campaigns/{cid}/publish").status_code == 200


def test_transparency_is_private_until_owner_approves_and_publicly_labelled(founder, admin, client):
    cid = mk(founder)
    d = founder.post(f"/api/campaigns/{cid}/transparency/draft",
                     {"owner_notes": {"risks": "Kiosks may be vandalised."}})
    assert d.status_code == 201 and d.json["transparency"]["status"] == "draft"
    body = " ".join(s["body"] for s in d.json["transparency"]["sections"])
    assert "R9 000.00" in body and "R1 000.00" in body and "not independently verified" in body
    publish(founder, admin, cid)
    slug = founder.get(f"/api/campaigns/{cid}").json["campaign"]["slug"]
    assert client.get(f"/api/public/campaigns/{slug}").json["campaign"]["transparency"] is None
    assert founder.post(f"/api/campaigns/{cid}/transparency/approve").status_code == 200
    t = client.get(f"/api/public/campaigns/{slug}").json["campaign"]["transparency"]
    keys = [s["key"] for s in t["sections"]]
    assert "verification" in keys and "risks" in keys and "not an audit" in t["note"]
    risks = next(s for s in t["sections"] if s["key"] == "risks")
    assert risks["source"] == "owner_written" and risks["body"] == "Kiosks may be vandalised."
    ver = next(s for s in t["sections"] if s["key"] == "verification")
    assert "not yet" in ver["body"] and "Financial figures independently verified: no" in ver["body"]


def test_editing_the_campaign_withdraws_approval_until_redone(founder, admin, client):
    cid = mk(founder)
    founder.post(f"/api/campaigns/{cid}/transparency/draft", {})
    founder.post(f"/api/campaigns/{cid}/transparency/approve")
    founder.post(f"/api/campaigns/{cid}/submit")
    admin.post(f"/api/admin/campaigns/{cid}/decision", {"action": "request_changes", "reason": "tweak"})
    founder.patch(f"/api/campaigns/{cid}", {"goal_cents": 2_000_000,
                  "use_of_funds": [{"item": "All", "amount_cents": 2_000_000}]})
    t = founder.get(f"/api/campaigns/{cid}/transparency").json["transparency"]
    assert t["stale"] is True
    assert founder.post(f"/api/campaigns/{cid}/transparency/approve").status_code == 409
    assert founder.get(f"/api/campaigns/{cid}").json["campaign"]["transparency"] is None


def test_new_draft_resets_approval_and_withdraw_removes(founder):
    cid = mk(founder)
    founder.post(f"/api/campaigns/{cid}/transparency/draft", {})
    assert founder.post(f"/api/campaigns/{cid}/transparency/approve").json["transparency"]["status"] == "approved"
    again = founder.post(f"/api/campaigns/{cid}/transparency/draft", {}).json["transparency"]
    assert again["status"] == "draft" and again["approved_at"] is None
    assert founder.delete(f"/api/campaigns/{cid}/transparency").status_code == 200
    assert founder.get(f"/api/campaigns/{cid}/transparency").json["transparency"] is None
    assert AuditLog.query.filter_by(action="transparency.withdraw").count() == 1


def test_transparency_validation_ownership_and_empty_campaign(founder, other_founder):
    cid = mk(founder)
    assert founder.post(f"/api/campaigns/{cid}/transparency/draft", {"owner_notes": {"hype": "x"}}).status_code == 400
    assert founder.post(f"/api/campaigns/{cid}/transparency/draft", {"owner_notes": {"risks": 5}}).status_code == 400
    assert other_founder.post(f"/api/campaigns/{cid}/transparency/draft", {}).status_code == 404
    assert other_founder.get(f"/api/campaigns/{cid}/transparency").status_code == 404
    assert other_founder.post(f"/api/campaigns/{cid}/transparency/approve").status_code == 404
    empty = founder.post("/api/campaigns", {"profile_id": make_profile(founder, "Other")["id"], "title": "Bare"}).json["campaign"]["id"]
    assert founder.post(f"/api/campaigns/{empty}/transparency/draft", {}).status_code == 409


def test_transparency_contains_no_invented_figures(founder):
    cid = mk(founder)
    secs = founder.post(f"/api/campaigns/{cid}/transparency/draft", {}).json["transparency"]["sections"]
    import re
    money = set(re.findall(r"R[\d ]+\.\d\d", " ".join(s["body"] for s in secs)))
    assert money <= {"R10 000.00", "R9 000.00", "R1 000.00"}


def test_public_statement_hidden_if_campaign_changes_after_approval(founder, admin, client, app):
    from app.extensions import db
    from app.models import Campaign
    cid = mk(founder)
    founder.post(f"/api/campaigns/{cid}/transparency/draft", {})
    founder.post(f"/api/campaigns/{cid}/transparency/approve")
    publish(founder, admin, cid)
    slug = founder.get(f"/api/campaigns/{cid}").json["campaign"]["slug"]
    assert client.get(f"/api/public/campaigns/{slug}").json["campaign"]["transparency"] is not None
    c = db.session.get(Campaign, cid)  # simulate a change that bypassed the API (e.g. a staff edit)
    c.use_of_funds = [{"item": "Something else", "amount_cents": c.goal_cents}]
    db.session.commit()
    assert client.get(f"/api/public/campaigns/{slug}").json["campaign"]["transparency"] is None


def test_approved_statement_not_shown_before_campaign_is_published(founder, admin):
    cid = mk(founder)
    founder.post(f"/api/campaigns/{cid}/transparency/draft", {})
    founder.post(f"/api/campaigns/{cid}/transparency/approve")
    founder.post(f"/api/campaigns/{cid}/submit")
    admin.post(f"/api/admin/campaigns/{cid}/decision", {"action": "approve", "reason": "ok"})
    assert founder.get(f"/api/campaigns/{cid}").json["campaign"]["status"] == "approved"
    assert founder.get(f"/api/campaigns/{cid}").json["campaign"]["transparency"] is None

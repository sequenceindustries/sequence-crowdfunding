import io

from app.ai import register_provider
from app.ai.base import AiProvider
from app.models import AiUsage, PitchDeck
from conftest import complete_campaign_payload, make_profile, minimal_pdf, text_pdf

GOOD_TEXT = (
    "Problem: township commuters struggle with dead phones. Our solution is a solar charging platform. "
    "Target customers are taxi commuters. Market demand is strong. Business model: we charge per charge. "
    "Competitor alternatives exist but our advantage is location. Marketing channel is taxi associations. "
    "Revenue and cost projections show break-even. We are seeking funding of R1000000. "
    "Use of funds: kiosks R900000. Team founder experience in energy. Traction: pilot with early customers."
)


def upload(c, data, name="deck.pdf", **extra):
    return c.post("/api/pitch-decks", data={"file": (io.BytesIO(data), name), **extra},
                  content_type="multipart/form-data")


def test_upload_extract_and_analyse(founder):
    r = upload(founder, text_pdf(GOOD_TEXT))
    assert r.status_code == 201 and r.json["pitch_deck"]["status"] == "ready"
    did = r.json["pitch_deck"]["id"]
    a = founder.post(f"/api/pitch-decks/{did}/analyse", {})
    assert a.status_code == 201
    rep = a.json["report"]
    assert rep["provider"] == "heuristic" and 0 <= rep["overall_completeness_score"] <= 100
    assert rep["overall_completeness_score"] > 60 and not rep["missing_sections"]
    assert any("not a prediction" in d for d in rep["disclaimers"])
    assert rep["methodology"]["weights"] and sum(rep["methodology"]["weights"].values()) == 100


def test_empty_deck_reports_missing_sections_not_fabrication(founder):
    r = upload(founder, text_pdf("Hello world"))
    did = r.json["pitch_deck"]["id"]
    rep = founder.post(f"/api/pitch-decks/{did}/analyse", {}).json["report"]
    assert rep["overall_completeness_score"] < 15 and "problem" in rep["missing_sections"]
    assert rep["strengths"] == []


def test_unsupported_claims_flagged(founder):
    r = upload(founder, text_pdf("We are the best and only guaranteed leading solution. " * 3))
    rep = founder.post(f"/api/pitch-decks/{r.json['pitch_deck']['id']}/analyse", {}).json["report"]
    assert rep["unclear_claims"]


def test_upload_validation(founder):
    assert upload(founder, b"MZ\x90 not a pdf", "evil.pdf").status_code == 400  # wrong magic
    assert upload(founder, b"%PDF-1.4 ok", "deck.exe").status_code == 400  # wrong extension
    assert upload(founder, b"", "deck.pdf").status_code == 400
    assert upload(founder, b"<html></html>", "deck.html").status_code == 400
    assert founder.post("/api/pitch-decks", data={}, content_type="multipart/form-data").status_code == 400


def test_oversize_upload_rejected(app, founder):
    app.config["MAX_UPLOAD_MB"] = 1
    assert upload(founder, b"%PDF-" + b"0" * (2 * 1024 * 1024)).status_code == 400


def test_malformed_pdf_is_handled_not_crashed(founder):
    r = upload(founder, b"%PDF-1.4 garbage that is not a real pdf")
    assert r.status_code == 201 and r.json["pitch_deck"]["status"] == "failed"
    did = r.json["pitch_deck"]["id"]
    assert founder.post(f"/api/pitch-decks/{did}/analyse", {}).status_code == 409


def test_scanned_pdf_without_text_flagged(founder):
    r = upload(founder, minimal_pdf())
    assert r.json["pitch_deck"]["status"] == "no_text"


def test_stored_privately_under_random_key(app, founder):
    upload(founder, text_pdf(GOOD_TEXT), "my-secret-business-plan.pdf")
    d = PitchDeck.query.first()
    assert "secret" not in d.storage_key and d.storage_key.endswith(".pdf")
    assert founder.get(f"/uploads/{d.storage_key}").status_code == 404  # no public route to files


def test_other_users_cannot_access_deck(founder, other_founder, admin):
    did = upload(founder, text_pdf(GOOD_TEXT)).json["pitch_deck"]["id"]
    assert other_founder.get(f"/api/pitch-decks/{did}").status_code == 404
    assert other_founder.post(f"/api/pitch-decks/{did}/analyse", {}).status_code == 404
    assert other_founder.post(f"/api/pitch-decks/{did}/download-link").status_code == 404
    # Admins cannot read a deck that is not attached to a campaign under review.
    assert admin.post(f"/api/pitch-decks/{did}/download-link").status_code == 404


def test_owner_download_link_is_user_bound_and_expires(app, make_client, founder, other_founder):
    original = text_pdf(GOOD_TEXT)
    did = upload(founder, original).json["pitch_deck"]["id"]
    url = founder.post(f"/api/pitch-decks/{did}/download-link").json["url"]
    got = founder.get(url)
    assert got.status_code == 200 and got.data == original
    assert got.headers["Cache-Control"] == "private, no-store"
    assert other_founder.get(url).status_code == 403  # leaked link is useless to someone else
    assert make_client().get(url).status_code == 401
    assert founder.get("/api/pitch-decks/download/garbage").status_code == 403
    from app.storage import private

    token = url.rsplit("/", 1)[1]
    assert private.read_download_token(token, max_age=-1) is None  # expired


def test_staff_can_open_deck_only_for_campaign_in_review(founder, reviewer):
    p = make_profile(founder)
    cid = founder.post("/api/campaigns", complete_campaign_payload(p["id"])).json["campaign"]["id"]
    did = upload(founder, text_pdf(GOOD_TEXT), campaign_id=str(cid)).json["pitch_deck"]["id"]
    assert reviewer.post(f"/api/pitch-decks/{did}/download-link").status_code == 404  # still a draft
    founder.post(f"/api/campaigns/{cid}/submit")
    assert reviewer.post(f"/api/pitch-decks/{did}/download-link").status_code == 200


def test_cannot_attach_deck_to_someone_elses_campaign(founder, other_founder):
    p = make_profile(founder)
    cid = founder.post("/api/campaigns", {"profile_id": p["id"], "title": "x"}).json["campaign"]["id"]
    assert upload(other_founder, text_pdf(GOOD_TEXT), campaign_id=str(cid)).status_code == 404


def test_external_provider_requires_consent(app, founder):
    class External(AiProvider):
        name, external = "fake-llm", True

        def analyze_pitch_deck(self, text):
            raise AssertionError("must not be called without consent")

    register_provider("fake-llm", External)
    app.config["AI_PROVIDER"] = "fake-llm"
    did = upload(founder, text_pdf(GOOD_TEXT)).json["pitch_deck"]["id"]
    r = founder.post(f"/api/pitch-decks/{did}/analyse", {})
    assert r.status_code == 409 and r.json["error"] == "consent_required"


def test_provider_failure_and_incomplete_output_handled(app, founder):
    class Broken(AiProvider):
        name = "broken"

        def analyze_pitch_deck(self, text):
            raise RuntimeError("boom with secrets")

    class Partial(AiProvider):
        name = "partial"

        def analyze_pitch_deck(self, text):
            return {"overall_completeness_score": 99}

    register_provider("broken", Broken)
    register_provider("partial", Partial)
    did = upload(founder, text_pdf(GOOD_TEXT)).json["pitch_deck"]["id"]
    for name in ("broken", "partial"):
        app.config["AI_PROVIDER"] = name
        r = founder.post(f"/api/pitch-decks/{did}/analyse", {})
        assert r.status_code == 502 and "secrets" not in r.get_data(as_text=True)
    assert AiUsage.query.filter_by(ok=False).count() == 2


def test_daily_ai_usage_limit(app, founder, monkeypatch):
    import app.ai as ai

    monkeypatch.setattr(ai, "DAILY_LIMIT_PER_USER", 2)
    did = upload(founder, text_pdf(GOOD_TEXT)).json["pitch_deck"]["id"]
    codes = [founder.post(f"/api/pitch-decks/{did}/analyse", {}).status_code for _ in range(3)]
    assert codes == [201, 201, 429]


def test_fee_is_configurable_and_not_charged(app, client):
    r = client.get("/api/config/pitch-deck-fee").json
    assert r["amount_cents"] == 50000 and r["currency"] == "ZAR"
    assert r["service"] == "package" and r["charging_enabled"] is False and r["provisional"] is True
    app.config["PITCH_DECK_FEE_ZAR_CENTS"] = 65000
    assert client.get("/api/config/pitch-deck-fee").json["amount_cents"] == 65000

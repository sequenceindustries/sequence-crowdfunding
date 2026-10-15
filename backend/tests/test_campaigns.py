from conftest import complete_campaign_payload, make_profile


def test_profile_isolation_and_history(founder, other_founder):
    p = make_profile(founder)
    assert other_founder.patch(f"/api/profiles/{p['id']}", {"name": "Hijack"}).status_code == 404
    assert founder.patch(f"/api/profiles/{p['id']}", {"description": "New text"}).status_code == 200
    hist = founder.get(f"/api/profiles/{p['id']}/history").json["history"]
    assert len(hist) == 1 and "description" in hist[0]["changed_fields"]
    assert other_founder.get(f"/api/profiles/{p['id']}/history").status_code == 404


def test_draft_save_and_resume(founder):
    p = make_profile(founder)
    cid = founder.post("/api/campaigns", {"profile_id": p["id"], "title": "Half done"}).json["campaign"]["id"]
    founder.patch(f"/api/campaigns/{cid}", {"summary": "Work in progress", "goal_cents": 500000})
    got = founder.get(f"/api/campaigns/{cid}").json["campaign"]
    assert got["status"] == "draft" and got["summary"] == "Work in progress" and got["goal_cents"] == 500000


def test_cannot_use_another_founders_profile_or_campaign(founder, other_founder):
    p = make_profile(founder)
    assert other_founder.post("/api/campaigns", {"profile_id": p["id"], "title": "x"}).status_code == 404
    cid = founder.post("/api/campaigns", {"profile_id": p["id"], "title": "Mine"}).json["campaign"]["id"]
    assert other_founder.get(f"/api/campaigns/{cid}").status_code == 404
    assert other_founder.patch(f"/api/campaigns/{cid}", {"title": "Stolen"}).status_code == 404
    assert other_founder.post(f"/api/campaigns/{cid}/submit").status_code == 404


def test_investment_model_is_disabled(founder):
    p = make_profile(founder)
    r = founder.post("/api/campaigns", {"profile_id": p["id"], "title": "x", "funding_model": "investment"})
    assert r.status_code == 400
    assert founder.post("/api/campaigns", {"profile_id": p["id"], "title": "x",
                                           "funding_model": "bogus"}).status_code == 400


def test_submit_blocked_until_complete_and_use_of_funds_matches_goal(founder):
    p = make_profile(founder)
    cid = founder.post("/api/campaigns", {"profile_id": p["id"], "title": "Incomplete"}).json["campaign"]["id"]
    r = founder.post(f"/api/campaigns/{cid}/submit")
    assert r.status_code == 422 and r.json["problems"]
    payload = complete_campaign_payload(p["id"])
    payload["use_of_funds"][0]["amount_cents"] -= 1  # no longer sums to the goal
    founder.patch(f"/api/campaigns/{cid}", payload)
    r = founder.post(f"/api/campaigns/{cid}/submit")
    assert r.status_code == 422 and any("total" in x for x in r.json["problems"])


def test_full_lifecycle_submit_approve_publish(founder, admin, submitted_campaign):
    cid = submitted_campaign
    assert founder.patch(f"/api/campaigns/{cid}", {"title": "Edit"}).status_code == 409  # locked in review
    assert founder.post(f"/api/campaigns/{cid}/publish").status_code == 409  # not approved yet
    assert admin.get("/api/admin/review-queue").json["campaigns"][0]["id"] == cid
    r = admin.post(f"/api/admin/campaigns/{cid}/decision", {"action": "approve", "reason": "Docs look fine"})
    assert r.status_code == 200 and r.json["campaign"]["status"] == "approved"
    assert founder.post(f"/api/campaigns/{cid}/publish").status_code == 200
    pub = founder.get("/api/public/campaigns").json
    assert pub["total"] == 1
    slug = pub["campaigns"][0]["slug"]
    page = founder.get(f"/api/public/campaigns/{slug}").json["campaign"]
    assert page["funding"]["confirmed_raised_cents"] == 0
    assert page["verification"]["financial_information_verified"] is False
    assert "owner_id" not in page and "review_note" not in page


def test_unapproved_campaigns_never_public(founder, submitted_campaign, client):
    assert client.get("/api/public/campaigns").json["total"] == 0


def test_moderation_requires_reason_and_valid_transition(admin, submitted_campaign):
    cid = submitted_campaign
    assert admin.post(f"/api/admin/campaigns/{cid}/decision", {"action": "approve"}).status_code == 400
    assert admin.post(f"/api/admin/campaigns/{cid}/decision",
                      {"action": "suspend", "reason": "x"}).status_code == 409  # cannot suspend a submitted one
    assert admin.post(f"/api/admin/campaigns/{cid}/decision",
                      {"action": "explode", "reason": "x"}).status_code == 400


def test_request_changes_then_resubmit(founder, admin, submitted_campaign):
    cid = submitted_campaign
    admin.post(f"/api/admin/campaigns/{cid}/decision", {"action": "request_changes", "reason": "Add milestones"})
    got = founder.get(f"/api/campaigns/{cid}").json["campaign"]
    assert got["status"] == "changes_requested" and got["review_note"] == "Add milestones"
    assert founder.patch(f"/api/campaigns/{cid}", {"summary": "Updated"}).status_code == 200
    assert founder.post(f"/api/campaigns/{cid}/submit").status_code == 200
    detail = admin.get(f"/api/admin/campaigns/{cid}").json
    assert [h["action"] for h in detail["moderation_history"]] == ["request_changes"]


def test_suspend_removes_from_public(founder, admin, client, submitted_campaign):
    cid = submitted_campaign
    admin.post(f"/api/admin/campaigns/{cid}/decision", {"action": "approve", "reason": "ok"})
    founder.post(f"/api/campaigns/{cid}/publish")
    assert client.get("/api/public/campaigns").json["total"] == 1
    admin.post(f"/api/admin/campaigns/{cid}/decision", {"action": "suspend", "reason": "Complaint received"})
    assert client.get("/api/public/campaigns").json["total"] == 0


def test_reviewer_can_review_but_not_see_admin_data(reviewer, submitted_campaign):
    assert reviewer.get("/api/admin/review-queue").status_code == 200
    assert reviewer.get("/api/admin/audit-log").status_code == 403
    assert reviewer.get("/api/admin/users").status_code == 403


def test_decisions_are_audited(admin, submitted_campaign):
    admin.post(f"/api/admin/campaigns/{submitted_campaign}/decision", {"action": "approve", "reason": "ok"})
    actions = [e["action"] for e in admin.get("/api/admin/audit-log").json["entries"]]
    assert "campaign.approve" in actions and "campaign.submit" in actions


def test_public_profile_hides_contact_unless_opted_in(founder, admin, client, submitted_campaign):
    cid = submitted_campaign
    pid = founder.get("/api/profiles/mine").json["profiles"][0]["id"]
    founder.patch(f"/api/profiles/{pid}", {"public_contact_email": "hello@sun.example"})
    admin.post(f"/api/admin/campaigns/{cid}/decision", {"action": "approve", "reason": "ok"})
    founder.post(f"/api/campaigns/{cid}/publish")
    slug = founder.get("/api/profiles/mine").json["profiles"][0]["slug"]
    assert "contact_email" not in client.get(f"/api/public/businesses/{slug}").json["profile"]
    founder.patch(f"/api/profiles/{pid}", {"contact_is_public": True})
    assert client.get(f"/api/public/businesses/{slug}").json["profile"]["contact_email"] == "hello@sun.example"


def test_search_filters_and_pagination_validate(founder, admin, client, submitted_campaign):
    cid = submitted_campaign
    admin.post(f"/api/admin/campaigns/{cid}/decision", {"action": "approve", "reason": "ok"})
    founder.post(f"/api/campaigns/{cid}/publish")
    assert client.get("/api/public/campaigns?q=solar").json["total"] == 1
    assert client.get("/api/public/campaigns?q=zzzz").json["total"] == 0
    assert client.get("/api/public/campaigns?funding_model=donation").json["total"] == 0
    assert client.get("/api/public/campaigns?q=s_lar").json["total"] == 0  # '_' is not a wildcard
    assert client.get("/api/public/campaigns?page=abc").status_code == 400

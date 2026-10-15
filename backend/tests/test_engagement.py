from app.models import CampaignUpdate, Follow


def post_update(c, cid, title="Kiosk 1 installed", body="First unit is live at the rank."):
    return c.post(f"/api/campaigns/{cid}/updates", {"title": title, "body": body})


def test_follow_unfollow_is_idempotent_and_listed(supporter, client, published_campaign):
    slug = published_campaign["slug"]
    assert supporter.post(f"/api/campaigns/{slug}/follow").status_code == 201
    assert supporter.post(f"/api/campaigns/{slug}/follow").status_code == 200
    assert Follow.query.count() == 1
    mine = supporter.get("/api/follows/mine").json["campaigns"]
    assert [c["slug"] for c in mine] == [slug] and "owner_id" not in mine[0]
    assert supporter.delete(f"/api/campaigns/{slug}/follow").json["following"] is False
    assert supporter.delete(f"/api/campaigns/{slug}/follow").status_code == 200
    assert supporter.get("/api/follows/mine").json["campaigns"] == []
    assert client.post(f"/api/campaigns/{slug}/follow").status_code == 401


def test_cannot_follow_unpublished_or_missing(supporter, founder, submitted_campaign):
    slug = founder.get(f"/api/campaigns/{submitted_campaign}").json["campaign"]["slug"] or "none"
    assert supporter.post(f"/api/campaigns/{slug}/follow").status_code == 404
    assert supporter.post("/api/campaigns/nope/follow").status_code == 404


def test_suspended_campaign_drops_out_of_follow_list(supporter, admin, published_campaign):
    supporter.post(f"/api/campaigns/{published_campaign['slug']}/follow")
    admin.post(f"/api/admin/campaigns/{published_campaign['id']}/decision", {"action": "suspend", "reason": "complaint"})
    assert supporter.get("/api/follows/mine").json["campaigns"] == []


def test_owner_posts_update_and_public_sees_it_labelled(founder, client, published_campaign):
    r = post_update(founder, published_campaign["id"])
    assert r.status_code == 201 and "Not independently verified" in r.json["update"]["label"]
    feed = client.get(f"/api/public/campaigns/{published_campaign['slug']}/updates").json["updates"]
    assert [u["title"] for u in feed] == ["Kiosk 1 installed"]
    post_update(founder, published_campaign["id"], title="Second")
    assert [u["title"] for u in client.get(f"/api/public/campaigns/{published_campaign['slug']}/updates").json["updates"]] == [
        "Second", "Kiosk 1 installed"]


def test_update_rules(founder, other_founder, supporter, client, submitted_campaign, published_campaign):
    cid = published_campaign["id"]
    assert post_update(other_founder, cid).status_code == 404  # not their campaign
    assert post_update(supporter, cid).status_code == 403
    assert client.post(f"/api/campaigns/{cid}/updates", {"title": "x", "body": "y"}).status_code == 401
    for bad in ({"title": "", "body": "b"}, {"title": "t", "body": "  "}, {"title": "t" * 201, "body": "b"},
                {"title": "t", "body": "b" * 5001}, {"title": 5, "body": "b"}, {}):
        assert founder.post(f"/api/campaigns/{cid}/updates", bad).status_code == 400
    assert CampaignUpdate.query.count() == 0


def test_updates_only_on_published_campaigns(founder, submitted_campaign):
    r = post_update(founder, submitted_campaign)
    assert r.status_code == 409 and r.json["error"] == "not_published"


def test_admin_can_hide_update_with_reason_and_it_leaves_the_feed(founder, admin, reviewer, supporter, client, published_campaign):
    uid = post_update(founder, published_campaign["id"]).json["update"]["id"]
    assert supporter.post(f"/api/admin/updates/{uid}/hide", {"reason": "x"}).status_code == 403
    assert admin.post(f"/api/admin/updates/{uid}/hide", {}).status_code == 400
    assert admin.post("/api/admin/updates/9999/hide", {"reason": "x"}).status_code == 404
    assert reviewer.post(f"/api/admin/updates/{uid}/hide", {"reason": "Misleading claim"}).status_code == 200
    assert client.get(f"/api/public/campaigns/{published_campaign['slug']}/updates").json["updates"] == []
    actions = [e["action"] for e in admin.get("/api/admin/audit-log").json["entries"]]
    assert "campaign.update_hidden" in actions


def test_suspended_campaign_hides_its_updates(founder, admin, client, published_campaign):
    post_update(founder, published_campaign["id"])
    admin.post(f"/api/admin/campaigns/{published_campaign['id']}/decision", {"action": "suspend", "reason": "complaint"})
    assert client.get(f"/api/public/campaigns/{published_campaign['slug']}/updates").status_code == 404

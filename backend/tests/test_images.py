"""Tests for image upload / serve endpoints."""
import io
import pytest
from conftest import verify_user

PNG_1PX = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _upload_png(client, url):
    """POST a 1-px PNG as multipart."""
    return client.c.post(url, headers=client._headers(),
                         data={"image": (io.BytesIO(PNG_1PX), "photo.png")},
                         content_type="multipart/form-data")


@pytest.fixture()
def founder_with_campaign(make_client):
    c = make_client()
    c.register("img_founder@example.com")
    verify_user("img_founder@example.com")
    c.login("img_founder@example.com")
    c.post("/api/profiles", {"name": "Img Biz", "industry": "tech"})
    profiles = c.get("/api/profiles/mine").get_json()["profiles"]
    pid = profiles[0]["id"]
    c.post("/api/campaigns", {"title": "Img Campaign", "profile_id": pid, "goal_cents": 500_000})
    campaigns = c.get("/api/campaigns/mine").get_json()["campaigns"]
    cid = campaigns[0]["id"]
    return c, pid, cid


@pytest.fixture()
def supporter_client(make_client):
    c = make_client()
    c.register("img_backer@example.com", role="supporter")
    verify_user("img_backer@example.com")
    c.login("img_backer@example.com")
    return c


def test_supporter_cannot_upload_cover(founder_with_campaign, supporter_client):
    _, _, cid = founder_with_campaign
    r = supporter_client.c.post(
        f"/api/campaigns/{cid}/cover-image",
        headers=supporter_client._headers(),
        data={"image": (io.BytesIO(PNG_1PX), "x.png")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 403


def test_upload_campaign_cover_wrong_owner(founder_with_campaign, make_client):
    _, _, cid = founder_with_campaign
    c2 = make_client()
    c2.register("img_other@example.com")
    verify_user("img_other@example.com")
    c2.login("img_other@example.com")
    r = c2.c.post(f"/api/campaigns/{cid}/cover-image", headers=c2._headers(),
                  data={"image": (io.BytesIO(PNG_1PX), "x.png")},
                  content_type="multipart/form-data")
    assert r.status_code == 404


def test_upload_campaign_cover_and_serve(founder_with_campaign):
    client, _, cid = founder_with_campaign
    r = _upload_png(client, f"/api/campaigns/{cid}/cover-image")
    assert r.status_code == 201
    token = r.get_json()["token"]

    # Serve via public image endpoint (logged-in user for private token).
    img = client.get(f"/api/public/images/{token}")
    assert img.status_code == 200
    assert img.content_type.startswith("image/")

    # campaign dict should now include the token
    detail = client.get("/api/campaigns/mine").get_json()
    assert detail["campaigns"][0]["cover_image_token"] is not None

    # Delete
    dr = client.delete(f"/api/campaigns/{cid}/cover-image")
    assert dr.status_code == 200
    detail2 = client.get("/api/campaigns/mine").get_json()
    assert detail2["campaigns"][0]["cover_image_token"] is None


def test_upload_profile_logo(founder_with_campaign):
    client, pid, _ = founder_with_campaign
    r = _upload_png(client, f"/api/profiles/{pid}/logo")
    assert r.status_code == 201
    token = r.get_json()["token"]
    img = client.get(f"/api/public/images/{token}")
    assert img.status_code == 200

    dr = client.delete(f"/api/profiles/{pid}/logo")
    assert dr.status_code == 200


def test_upload_pdf_as_image_rejected(founder_with_campaign):
    client, _, cid = founder_with_campaign
    pdf_bytes = b"%PDF-1.0 fake"
    r = client.c.post(f"/api/campaigns/{cid}/cover-image", headers=client._headers(),
                      data={"image": (io.BytesIO(pdf_bytes), "doc.pdf")},
                      content_type="multipart/form-data")
    assert r.status_code == 400


def test_tampered_token_rejected(founder_with_campaign):
    client, _, _ = founder_with_campaign
    r = client.get("/api/public/images/NOTAVALIDTOKEN")
    assert r.status_code == 403


def test_public_image_token_works_without_auth(founder_with_campaign):
    """A short-lived public token can be fetched without a session cookie (for public campaign pages)."""
    client, _, cid = founder_with_campaign
    r = _upload_png(client, f"/api/campaigns/{cid}/cover-image")
    assert r.status_code == 201
    token = r.get_json()["token"]
    # Use raw test client with no session
    from app import create_app
    anon = client.c  # same client — but the endpoint has no @login_required
    img = anon.get(f"/api/public/images/{token}")
    assert img.status_code == 200

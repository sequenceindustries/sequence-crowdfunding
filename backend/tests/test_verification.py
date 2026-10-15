import io

from app.models import AuditLog, EmailOutbox, VerificationDocument
from conftest import minimal_pdf

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
JPG = b"\xff\xd8\xff\xe0" + b"0" * 64


def up(c, kind="identity", data=None, name="id.pdf"):
    return c.post("/api/verification/documents",
                  data={"file": (io.BytesIO(data if data is not None else minimal_pdf()), name), "kind": kind},
                  content_type="multipart/form-data")


def decide(c, doc_id, action, reason="Checked against the register."):
    return c.post(f"/api/admin/verification/documents/{doc_id}/decision", {"action": action, "reason": reason})


def flags(client, cid):
    return client.get(f"/api/campaigns/{cid}") if False else None


def test_upload_accepts_pdf_png_jpg_and_rejects_others(founder):
    assert up(founder, data=minimal_pdf()).status_code == 201
    assert up(founder, "proof_of_address", PNG, "a.png").status_code == 201
    assert up(founder, "proof_of_address", JPG, "a.jpg").status_code == 201
    assert up(founder, "identity", b"MZ\x90" + b"0" * 50, "a.exe").status_code == 400
    assert up(founder, "identity", b"not a png", "a.png").status_code == 400  # content must match extension
    assert up(founder, "identity", b"", "a.pdf").status_code == 400
    assert up(founder, "selfie", minimal_pdf()).status_code == 400
    assert founder.post("/api/verification/documents", data={"kind": "identity"},
                        content_type="multipart/form-data").status_code == 400


def test_only_founders_upload_and_owners_see_only_their_own(founder, other_founder, supporter, client):
    assert up(supporter).status_code == 403
    assert up(client).status_code == 401
    did = up(founder).json["document"]["id"]
    assert [d["id"] for d in founder.get("/api/verification/documents").json["documents"]] == [did]
    assert other_founder.get("/api/verification/documents").json["documents"] == []
    assert other_founder.delete(f"/api/verification/documents/{did}").status_code == 404


def test_staff_endpoints_closed_to_founders_and_anonymous(founder, client):
    did = up(founder).json["document"]["id"]
    for c, code in ((founder, 403), (client, 401)):
        assert c.get("/api/admin/verification/queue").status_code == code
        assert c.post(f"/api/admin/verification/documents/{did}/download-link").status_code == code
        assert decide(c, did, "approve").status_code == code


def test_approval_sets_flags_and_audit_and_emails_owner(founder, reviewer, submitted_campaign):
    cid = submitted_campaign
    pub = lambda: founder.get(f"/api/campaigns/{cid}").json["campaign"]["verification"]
    before = pub()
    assert before["identity_checked"] is False and before["business_documents_reviewed"] is False
    did = up(founder).json["document"]["id"]
    assert pub()["identity_checked"] is False  # uploading alone proves nothing
    r = decide(reviewer, did, "approve")
    assert r.status_code == 200 and r.json["document"]["status"] == "approved"
    v = pub()
    assert v["identity_checked"] is True and v["business_documents_reviewed"] is False
    assert v["financial_information_verified"] is False
    assert AuditLog.query.filter_by(action="verification.approve", target_id=did).count() == 1
    assert EmailOutbox.query.filter(EmailOutbox.to_email == "founder@example.com",
                                    EmailOutbox.subject.contains("approved")).count() == 1
    assert founder.get("/api/verification/documents").json["documents"][0]["reviewer_note"]


def test_rejected_or_info_requested_never_set_flags(founder, reviewer, submitted_campaign):
    d1 = up(founder).json["document"]["id"]
    d2 = up(founder, "business_registration").json["document"]["id"]
    assert decide(reviewer, d1, "reject", "Photo unreadable").status_code == 200
    assert decide(reviewer, d2, "request_info", "Please add the full certificate").status_code == 200
    v = founder.get(f"/api/campaigns/{submitted_campaign}").json["campaign"]["verification"]
    assert v["identity_checked"] is False and v["business_documents_reviewed"] is False


def test_decisions_need_reason_valid_action_and_valid_state(founder, reviewer):
    did = up(founder).json["document"]["id"]
    assert decide(reviewer, did, "approve", "  ").status_code == 400
    assert decide(reviewer, did, "bless").status_code == 400
    assert decide(reviewer, 9999, "approve").status_code == 404
    assert decide(reviewer, did, "approve").status_code == 200
    assert decide(reviewer, did, "reject").status_code == 409  # already decided
    assert decide(reviewer, did, "approve").status_code == 409


def test_escalation_is_admin_only(founder, reviewer, admin):
    did = up(founder).json["document"]["id"]
    assert decide(reviewer, did, "escalate", "Possible forgery").json["document"]["status"] == "escalated"
    assert reviewer.get("/api/admin/verification/queue").json["documents"] == []
    assert decide(reviewer, did, "approve").status_code == 404
    assert reviewer.post(f"/api/admin/verification/documents/{did}/download-link").status_code == 404
    assert [d["id"] for d in admin.get("/api/admin/verification/queue").json["documents"]] == [did]
    assert decide(admin, did, "reject", "Confirmed forged").status_code == 200


def test_download_link_is_audited_user_bound_and_staff_only(founder, reviewer, admin):
    pdf = minimal_pdf()
    did = up(founder, data=pdf).json["document"]["id"]
    link = reviewer.post(f"/api/admin/verification/documents/{did}/download-link").json["url"]
    assert AuditLog.query.filter_by(action="verification.download_link").count() == 1
    assert admin.get(link).status_code == 403          # bound to the reviewer it was issued to
    assert founder.get(link).status_code == 403        # owner cannot use a staff link either
    r = reviewer.get(link)
    assert r.status_code == 200 and r.data == pdf and "no-store" in r.headers["Cache-Control"]
    assert AuditLog.query.filter_by(action="verification.download").count() == 1
    # a pitch-deck token can't open a verification document and vice versa
    from app.storage.private import make_download_token, read_verification_token
    assert read_verification_token(make_download_token(did, 1)) is None


def test_stored_file_is_not_web_reachable_and_owner_has_no_download(founder):
    did = up(founder).json["document"]["id"]
    assert founder.post(f"/api/admin/verification/documents/{did}/download-link").status_code == 403
    key = VerificationDocument.query.get(did).storage_key
    assert founder.get(f"/{key}").status_code == 404 and founder.get(f"/uploads/{key}").status_code == 404


def test_owner_can_delete_unapproved_but_not_approved(founder, reviewer, app):
    import os
    d1 = up(founder).json["document"]["id"]
    path = os.path.join(app.config["UPLOAD_DIR"], VerificationDocument.query.get(d1).storage_key)
    assert os.path.exists(path)
    assert founder.delete(f"/api/verification/documents/{d1}").status_code == 200
    assert not os.path.exists(path) and VerificationDocument.query.count() == 0
    d2 = up(founder).json["document"]["id"]
    decide(reviewer, d2, "approve")
    assert founder.delete(f"/api/verification/documents/{d2}").status_code == 409


def test_document_cap_per_user(founder):
    for _ in range(12):
        assert up(founder).status_code == 201
    assert up(founder).status_code == 409

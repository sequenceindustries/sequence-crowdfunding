import hashlib
import json

from ..models import Campaign, CampaignTransparency
from .verification import verification_flags

NOTE_FIELDS = {"risks": 2000, "update_plan": 2000}


def source_snapshot(c: Campaign) -> dict:
    """Only owner-entered fields. Verification status is rendered live, so it is not part of this."""
    return {
        "title": c.title, "summary": c.summary, "description": c.description, "funding_model": c.funding_model,
        "goal_cents": c.goal_cents, "use_of_funds": c.use_of_funds or [], "stage": c.stage,
        "location": c.location, "objectives": c.objectives, "funding_purpose": c.funding_purpose,
        "milestones": [{"title": m.title, "detail": m.detail,
                        "target_date": m.target_date.isoformat() if m.target_date else None} for m in c.milestones],
    }


def source_hash(c: Campaign, owner_notes: dict) -> str:
    blob = json.dumps({"s": source_snapshot(c), "n": owner_notes}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def clean_notes(body) -> tuple[dict, str | None]:
    out = {}
    if body is None:
        return out, None
    if not isinstance(body, dict):
        return {}, "owner_notes must be an object."
    for k, v in body.items():
        if k not in NOTE_FIELDS:
            return {}, f"Unknown note '{k}'."
        if not isinstance(v, str):
            return {}, f"{k} must be text."
        if v.strip():
            out[k] = v.strip()[:NOTE_FIELDS[k]]
    return out, None


def live_verification_section(c: Campaign) -> dict:
    f = verification_flags(c.owner_id)
    lines = [
        f"- Identity documents reviewed by the platform: {'yes' if f['identity_checked'] else 'not yet'}",
        f"- Business registration documents reviewed by the platform: {'yes' if f['business_documents_reviewed'] else 'not yet'}",
        "- Financial figures independently verified: no",
    ]
    return {"key": "verification", "heading": "What has and has not been checked", "source": "platform_status",
            "body": "\n".join(lines)}


def public_view(c: Campaign):
    """The approved statement, only while it still matches the campaign it was approved for."""
    if c.status != "published":
        return None
    t = CampaignTransparency.query.filter_by(campaign_id=c.id, status="approved").first()
    if t is None or t.source_hash != source_hash(c, t.owner_notes or {}):
        return None
    sections = list(t.sections)
    notes = t.owner_notes or {}
    if notes.get("risks"):
        sections.append({"key": "risks", "heading": "Risks, as described by the owner", "source": "owner_written", "body": notes["risks"]})
    if notes.get("update_plan"):
        sections.append({"key": "update_plan", "heading": "How the owner will share updates", "source": "owner_written", "body": notes["update_plan"]})
    sections.insert(1 if sections else 0, live_verification_section(c))
    return {"approved_at": t.approved_at.isoformat(), "sections": sections,
            "note": "Approved by the campaign owner. Built from the owner's own figures and fixed platform statements; not an audit."}

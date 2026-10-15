import io

from flask import Blueprint, jsonify, request, send_file

from ..extensions import db
from ..models import DeckDraft
from ..security import current_user, roles_required
from ..services.audit import audit
from ..services.deck_builder import (
    ORDER, THEMES, DeckInputError, build_section, build_slides, clean, validate_slides,
)
from ..services.deck_export import export_pptx

bp = Blueprint("deck_drafts", __name__, url_prefix="/api/deck-drafts")

MAX_DRAFTS_PER_USER = 50
ANSWER_TEXT_KEYS = ("business_name", "tagline", "idea", "problem", "solution", "product", "customers", "market",
                    "competition", "revenue_model", "marketing", "operations", "traction",
                    "financial_assumptions", "risks")


def _draft_dict(d: DeckDraft):
    return {"id": d.id, "title": d.title, "theme": d.theme, "answers": d.answers, "slides": d.slides,
            "incomplete_count": sum(1 for s in d.slides if s["incomplete"]),
            "themes": list(THEMES), "updated_at": d.updated_at.isoformat() if d.updated_at else None}


def _owned(draft_id):
    d = db.session.get(DeckDraft, draft_id)
    return d if d is not None and d.owner_id == current_user().id else None


def _clean_answers(raw):
    if not isinstance(raw, dict):
        raise DeckInputError("answers must be an object.")
    out = {}
    for k in ANSWER_TEXT_KEYS:
        if k in raw:
            if raw[k] is not None and not isinstance(raw[k], str):
                raise DeckInputError(f"{k} must be text.")
            out[k] = clean(raw[k])
    if "funding_request_cents" in raw:
        v = raw["funding_request_cents"]
        if v is not None and (not isinstance(v, int) or isinstance(v, bool) or v < 0 or v > 10**13):
            raise DeckInputError("funding_request_cents must be a non-negative whole number.")
        out["funding_request_cents"] = v
    for k, fields in (("use_of_funds", ("item", "amount_cents")), ("team", ("name", "role", "experience")),
                      ("milestones", ("title", "date"))):
        if k in raw:
            v = raw[k]
            if not isinstance(v, list) or len(v) > 30 or not all(isinstance(i, dict) for i in v):
                raise DeckInputError(f"{k} must be a list of at most 30 objects.")
            items = []
            for i in v:
                row = {}
                for f in fields:
                    val = i.get(f)
                    if f == "amount_cents":
                        if val is not None and (not isinstance(val, int) or isinstance(val, bool) or val < 0):
                            raise DeckInputError("amount_cents must be a non-negative whole number.")
                        row[f] = val
                    else:
                        row[f] = clean(val, 300)
                items.append(row)
            out[k] = items
    return out


@bp.post("")
@roles_required("founder")
def create():
    body = request.get_json(silent=True) or {}
    if DeckDraft.query.filter_by(owner_id=current_user().id).count() >= MAX_DRAFTS_PER_USER:
        return jsonify(error="draft_limit_reached"), 429
    try:
        answers = _clean_answers(body.get("answers", {}))
    except DeckInputError as exc:
        return jsonify(error="invalid", message=str(exc)), 400
    theme = body.get("theme", "classic")
    if theme not in THEMES:
        return jsonify(error="invalid", message="Unknown theme."), 400
    d = DeckDraft(owner_id=current_user().id, theme=theme, answers=answers, slides=build_slides(answers),
                  title=clean(body.get("title"), 200) or answers.get("business_name") or "Untitled deck")
    db.session.add(d)
    db.session.flush()
    audit(current_user().id, "deck_draft.create", "deck_draft", d.id)
    db.session.commit()
    return jsonify(draft=_draft_dict(d)), 201


@bp.get("")
@roles_required("founder")
def list_mine():
    rows = DeckDraft.query.filter_by(owner_id=current_user().id).order_by(DeckDraft.id.desc()).all()
    return jsonify(drafts=[{"id": d.id, "title": d.title, "theme": d.theme, "slide_count": len(d.slides),
                            "incomplete_count": sum(1 for s in d.slides if s["incomplete"])} for d in rows])


@bp.get("/<int:draft_id>")
@roles_required("founder")
def get_one(draft_id):
    d = _owned(draft_id)
    return (jsonify(draft=_draft_dict(d)), 200) if d else (jsonify(error="not_found"), 404)


@bp.patch("/<int:draft_id>")
@roles_required("founder")
def update(draft_id):
    d = _owned(draft_id)
    if d is None:
        return jsonify(error="not_found"), 404
    body = request.get_json(silent=True) or {}
    try:
        if "answers" in body:  # merges into existing answers; slides change only when regenerated
            d.answers = {**d.answers, **_clean_answers(body["answers"])}
        if "slides" in body:
            d.slides = validate_slides(body["slides"], existing=d.slides)
        if "theme" in body:
            if body["theme"] not in THEMES:
                raise DeckInputError("Unknown theme.")
            d.theme = body["theme"]
        if "title" in body:
            d.title = clean(body["title"], 200) or d.title
    except DeckInputError as exc:
        return jsonify(error="invalid", message=str(exc)), 400
    audit(current_user().id, "deck_draft.update", "deck_draft", d.id)
    db.session.commit()
    return jsonify(draft=_draft_dict(d))


@bp.post("/<int:draft_id>/regenerate")
@roles_required("founder")
def regenerate(draft_id):
    """Rebuild one section from the saved answers. This replaces any manual edits to that slide."""
    d = _owned(draft_id)
    if d is None:
        return jsonify(error="not_found"), 404
    key = (request.get_json(silent=True) or {}).get("key")
    if key not in ORDER:
        return jsonify(error="invalid", message="Unknown section."), 400
    fresh = build_section(key, d.answers)
    if fresh is None:
        return jsonify(error="no_content", message="There is nothing in your answers for this section yet."), 409
    slides = list(d.slides)
    for i, s in enumerate(slides):
        if s["key"] == key:
            fresh["id"] = s["id"]
            slides[i] = fresh
            break
    else:  # section had no slide yet: insert it in questionnaire order
        pos = len(slides)
        for i, s in enumerate(slides):
            if s["key"] in ORDER and ORDER.index(s["key"]) > ORDER.index(key):
                pos = i
                break
        slides.insert(pos, fresh)
    d.slides = slides
    audit(current_user().id, "deck_draft.regenerate", "deck_draft", d.id, {"section": key})
    db.session.commit()
    return jsonify(draft=_draft_dict(d))


@bp.delete("/<int:draft_id>")
@roles_required("founder")
def delete(draft_id):
    d = _owned(draft_id)
    if d is None:
        return jsonify(error="not_found"), 404
    audit(current_user().id, "deck_draft.delete", "deck_draft", d.id)
    db.session.delete(d)
    db.session.commit()
    return jsonify(ok=True)


@bp.get("/<int:draft_id>/export.pptx")
@roles_required("founder")
def export(draft_id):
    d = _owned(draft_id)
    if d is None:
        return jsonify(error="not_found"), 404
    incomplete = [s["title"] or "(untitled)" for s in d.slides if s["incomplete"]]
    # An unfinished deck must never be exported looking finished.
    if (incomplete or not d.slides) and request.args.get("allow_incomplete") != "true":
        return jsonify(error="incomplete", message="Some slides are incomplete.", incomplete_slides=incomplete), 409
    data = export_pptx(d.title, d.theme, d.slides)
    audit(current_user().id, "deck_draft.export", "deck_draft", d.id)
    db.session.commit()
    name = "".join(c if c.isalnum() else "-" for c in d.title)[:60].strip("-") or "pitch-deck"
    resp = send_file(io.BytesIO(data), as_attachment=True, download_name=f"{name}.pptx",
                     mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation")
    resp.headers["Cache-Control"] = "private, no-store"
    return resp

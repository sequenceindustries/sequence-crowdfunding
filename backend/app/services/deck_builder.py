"""Turn questionnaire answers into a slide draft.

The builder only rearranges text the founder wrote. It never adds facts, figures,
customers, partners or statistics. Missing essentials become slides marked
incomplete, with a prompt telling the founder what to supply."""
import re
import uuid

PLACEHOLDER = "[To be completed]"
THEMES = {
    "classic": {"bg": "FFFFFF", "title": "14231F", "body": "333333", "accent": "0F5C4A"},
    "midnight": {"bg": "14181F", "title": "FFFFFF", "body": "D8DEE9", "accent": "C8892B"},
    "forest": {"bg": "E5F1ED", "title": "0A4234", "body": "1F2D29", "accent": "0F5C4A"},
}
MAX_SLIDES = 40
MAX_TEXT = 5000
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class DeckInputError(ValueError):
    pass


def clean(text, limit=MAX_TEXT):
    """Strip control characters (they corrupt PPTX XML) and cap length."""
    if text is None:
        return ""
    return _CTRL.sub("", str(text)).strip()[:limit]


def _lines(text):
    return [clean(l, 500) for l in clean(text).splitlines() if l.strip()]


def _money(cents):
    return f"R{cents / 100:,.0f}".replace(",", " ")


def _slide(key, title, body="", bullets=None, incomplete=False, note=None, label=None):
    return {"id": uuid.uuid4().hex[:12], "key": key, "title": clean(title, 200), "body": clean(body),
            "bullets": [clean(b, 500) for b in (bullets or [])][:20],
            "incomplete": incomplete, "note": note, "label": label}


# Sections that always get a slide, even when empty (flagged incomplete).
REQUIRED = ("cover", "problem", "solution", "funding")
ORDER = ("cover", "problem", "solution", "product", "market", "business_model", "competition", "marketing",
         "traction", "team", "financials", "funding", "milestones", "risks")

PROMPTS = {
    "cover": "Add your business name.",
    "problem": "Describe the problem you solve and who has it.",
    "solution": "Describe what you offer and how it solves that problem.",
    "funding": "State how much you are asking for and break it into line items that add up to it.",
}


def build_section(key, a):
    """Return a slide for one section, or None when the founder gave no content for an optional section."""
    if key == "cover":
        name = clean(a.get("business_name"), 200)
        if not name:
            return _slide("cover", PLACEHOLDER, incomplete=True, note=PROMPTS["cover"])
        return _slide("cover", name, body=clean(a.get("tagline"), 300))

    if key == "problem":
        text = a.get("problem")
        if not clean(text):
            return _slide("problem", "The problem", incomplete=True, note=PROMPTS["problem"])
        return _slide("problem", "The problem", bullets=_lines(text))

    if key == "solution":
        parts = _lines(a.get("solution"))
        if not parts:
            return _slide("solution", "Our solution", incomplete=True, note=PROMPTS["solution"])
        return _slide("solution", "Our solution", bullets=parts)

    if key == "product":
        lines = _lines(a.get("product"))
        return _slide("product", "Product or service", bullets=lines) if lines else None

    if key == "market":
        lines = _lines(a.get("customers")) + _lines(a.get("market"))
        return _slide("market", "Customers and market", bullets=lines) if lines else None

    if key == "business_model":
        lines = _lines(a.get("revenue_model"))
        return _slide("business_model", "Business model", bullets=lines) if lines else None

    if key == "competition":
        lines = _lines(a.get("competition"))
        return _slide("competition", "Competitive landscape", bullets=lines) if lines else None

    if key == "marketing":
        lines = _lines(a.get("marketing")) + _lines(a.get("operations"))
        return _slide("marketing", "Marketing and operations", bullets=lines) if lines else None

    if key == "traction":
        lines = _lines(a.get("traction"))
        return _slide("traction", "Progress to date", bullets=lines,
                      label="Reported by the owner; not independently verified.") if lines else None

    if key == "team":
        members = a.get("team") or []
        lines = []
        for m in members[:15] if isinstance(members, list) else []:
            if isinstance(m, dict) and clean(m.get("name"), 100):
                role = clean(m.get("role"), 100)
                exp = clean(m.get("experience"), 300)
                lines.append(" — ".join(x for x in (clean(m["name"], 100), role, exp) if x))
        return _slide("team", "The team", bullets=lines) if lines else None

    if key == "financials":
        lines = _lines(a.get("financial_assumptions"))
        return _slide("financials", "Financial assumptions", bullets=lines,
                      label="Owner-provided assumptions and estimates. Not verified.") if lines else None

    if key == "funding":
        return _funding_slide(a)

    if key == "milestones":
        items = a.get("milestones") or []
        lines = []
        for m in items[:20] if isinstance(items, list) else []:
            if isinstance(m, dict) and clean(m.get("title"), 200):
                when = clean(m.get("date"), 40)
                lines.append(f"{clean(m['title'], 200)}" + (f" ({when})" if when else ""))
        return _slide("milestones", "Milestones", bullets=lines) if lines else None

    if key == "risks":
        lines = _lines(a.get("risks"))
        return _slide("risks", "Risks and next steps", bullets=lines) if lines else None
    raise DeckInputError(f"Unknown section '{key}'.")


def _funding_slide(a):
    request = a.get("funding_request_cents")
    uof = a.get("use_of_funds") or []
    valid_request = isinstance(request, int) and not isinstance(request, bool) and request > 0
    items = []
    if isinstance(uof, list):
        for u in uof[:30]:
            if isinstance(u, dict) and clean(u.get("item"), 200) and isinstance(u.get("amount_cents"), int) \
                    and not isinstance(u["amount_cents"], bool) and u["amount_cents"] >= 0:
                items.append((clean(u["item"], 200), u["amount_cents"]))
    if not valid_request and not items:
        return _slide("funding", "Funding request", incomplete=True, note=PROMPTS["funding"])
    bullets = []
    if valid_request:
        bullets.append(f"Funding requested: {_money(request)}")
    for name, cents in items:
        bullets.append(f"{name}: {_money(cents)}")
    total = sum(c for _, c in items)
    note = None
    if not valid_request:
        note = "Add the total amount you are requesting."
    elif not items:
        note = "Add a use-of-funds breakdown that adds up to the amount requested."
    elif total != request:
        note = (f"Your use of funds adds up to {_money(total)} but you are requesting {_money(request)}. "
                "Make them match before sharing.")
    else:
        bullets.append(f"Total: {_money(total)}")
    return _slide("funding", "Funding request and use of funds", bullets=bullets,
                  incomplete=note is not None, note=note, label="Planned by the owner; not independently verified.")


def build_slides(answers):
    slides = []
    for key in ORDER:
        s = build_section(key, answers)
        if s is not None:
            slides.append(s)
    return slides


def recompute_incomplete(slide):
    """A slide is incomplete when it is empty, has a placeholder, or its builder flagged a problem."""
    text = " ".join([slide["title"], slide["body"], *slide["bullets"]])
    if PLACEHOLDER in text or not slide["title"]:
        return True
    return not slide["body"] and not slide["bullets"]


def validate_slides(raw, existing=None):
    """Validate a client-supplied slide list (edit, reorder, add, remove all arrive this way).

    A slide whose content is unchanged keeps the incomplete flag the builder gave it (for example a
    funding total that does not match). A slide the founder edited is re-checked from its content."""
    stored = {s["id"]: s for s in (existing or [])}
    if not isinstance(raw, list) or len(raw) > MAX_SLIDES:
        raise DeckInputError(f"slides must be a list of at most {MAX_SLIDES}.")
    out, seen = [], set()
    for s in raw:
        if not isinstance(s, dict):
            raise DeckInputError("Each slide must be an object.")
        bullets = s.get("bullets", [])
        if not isinstance(bullets, list) or len(bullets) > 20 or not all(isinstance(b, str) for b in bullets):
            raise DeckInputError("bullets must be a list of at most 20 text items.")
        sid = clean(s.get("id"), 20) or uuid.uuid4().hex[:12]
        if sid in seen:
            raise DeckInputError("Slide ids must be unique.")
        seen.add(sid)
        slide = {"id": sid, "key": clean(s.get("key"), 30) or "custom", "title": clean(s.get("title"), 200),
                 "body": clean(s.get("body")), "bullets": [clean(b, 500) for b in bullets if clean(b, 500)],
                 "label": clean(s.get("label"), 200) or None, "note": None, "incomplete": False}
        prev = stored.get(sid)
        unchanged = prev is not None and all(prev[k] == slide[k] for k in ("title", "body", "bullets"))
        if unchanged:
            slide["incomplete"], slide["note"] = prev["incomplete"], prev["note"]
        else:
            slide["incomplete"] = recompute_incomplete(slide)
            if slide["incomplete"]:
                slide["note"] = clean(s.get("note"), 400) or "This slide still needs content."
        out.append(slide)
    return out

"""Deterministic campaign review and transparency drafting.

Nothing here invents facts: every statement is either a fixed platform statement about what the
funding model means, or the owner's own figures re-presented. Checks cite the field they refer to."""
import re

from .base import AiProvider  # noqa: F401  (kept for type context)

METHODOLOGY_VERSION = "campaign-checks-1.0"

# Language that implies investment returns or removes risk. Flagged for the owner to rewrite.
RETURN_CLAIMS = re.compile(
    r"\b(guarantee[sd]?|risk[- ]free|no risk|double your|triple your|get rich|passive income for (you|investors)|"
    r"returns? of \d|roi of|dividends?|profit[- ]shar\w+|equity|shares? in the (company|business)|"
    r"investors? will (earn|receive|get))\b", re.I)
PRESSURE = re.compile(r"\b(last chance|act now|hurry|don'?t miss out|only \d+ (hours|days) left)\b", re.I)
FIGURE = re.compile(r"(\d+(\.\d+)?\s?%|\b\d+(\.\d+)?\s?(million|billion)\b|\bR\s?\d[\d ,]{3,}\b)", re.I)
SOURCE_HINT = re.compile(r"\b(source|according to|per |report|survey|stats ?sa|study|data from)\b", re.I)


def _texts(c):
    return " ".join(str(c.get(k) or "") for k in ("title", "summary", "description", "objectives", "funding_purpose"))


def review_campaign(c: dict) -> dict:
    checks, strengths = [], []

    def add(field, severity, message):
        checks.append({"field": field, "severity": severity, "message": message})

    summary, desc = (c.get("summary") or "").strip(), (c.get("description") or "").strip()
    if len(summary) < 40:
        add("summary", "medium", "The summary is very short. One or two plain sentences on what you do and what the money is for help visitors decide whether to read on.")
    else:
        strengths.append("Summary present")
    if len(desc) < 300:
        add("description", "medium", "The description is under 300 characters. Explain the problem, who you serve, how the plan works and why you are the right people to do it.")
    else:
        strengths.append("Description has substance")
    for f, label in (("stage", "business stage"), ("location", "location"), ("objectives", "objectives"),
                     ("funding_purpose", "funding purpose")):
        if not (c.get(f) or "").strip():
            add(f, "low", f"No {label} given. Supporters cannot see it, and reviewers may ask.")
    ms = c.get("milestones") or []
    if not ms:
        add("milestones", "medium", "No milestones. Add the two or three things you will do with the money and roughly when, so supporters can follow progress.")
    else:
        strengths.append(f"{len(ms)} milestone(s) listed")
        if any(not m.get("target_date") for m in ms):
            add("milestones", "low", "Some milestones have no target date.")
    funds, goal = c.get("use_of_funds") or [], c.get("goal_cents") or 0
    total = sum(i["amount_cents"] for i in funds)
    if goal and funds and total != goal:
        add("use_of_funds", "high", "The use-of-funds items do not add up to the goal. Submission is blocked until they do.")
    elif goal and funds:
        strengths.append("Use of funds adds up to the goal")
        biggest = max(funds, key=lambda i: i["amount_cents"])
        if goal and biggest["amount_cents"] * 100 // goal >= 80 and len(funds) > 1:
            add("use_of_funds", "low", f"'{biggest['item']}' is {biggest['amount_cents'] * 100 // goal}% of the budget. Breaking it into parts shows supporters where the money goes.")
        elif len(funds) == 1:
            add("use_of_funds", "low", "A single budget line gives supporters little to check. Consider splitting it.")
    text = _texts(c)
    compliance = []
    for m in sorted({m.group(0).lower() for m in RETURN_CLAIMS.finditer(text)}):
        compliance.append({"phrase": m, "severity": "high",
                           "message": f"'{m}' promises or implies returns or removes risk. Contributions on this platform are not investments and outcomes cannot be guaranteed. Reword or remove it."})
    for m in sorted({m.group(0).lower() for m in PRESSURE.finditer(text)}):
        add("description", "low", f"'{m}' is pressure language. Reviewers may ask you to remove it.")
    if FIGURE.search(text) and not SOURCE_HINT.search(text):
        add("description", "medium", "You quote figures (percentages, amounts or market sizes) but name no source. Say where each came from, or mark it as your own estimate.")
    return {
        "provider": "heuristic", "methodology_version": METHODOLOGY_VERSION,
        "checks": checks, "compliance_flags": compliance, "strengths": strengths,
        "disclaimers": [
            "Rule-based check of completeness and wording. It cannot tell whether your claims are true.",
            "It does not rewrite your campaign. Nothing here changes it until you edit it yourself.",
        ],
    }


MODEL_STATEMENTS = {
    "donation": "Contributions are donations. Supporters receive nothing in return and have no ownership, profit share or repayment.",
    "reward": "Contributions are pre-purchases or support in exchange for the reward described by the owner. They are not investments and carry no ownership or profit share.",
    "business_support": "Contributions support the business. They are not investments and carry no ownership, profit share or repayment.",
}


def _rand(cents):
    return f"R{cents / 100:,.2f}".replace(",", " ")


def draft_transparency(c: dict) -> dict:
    """Sections built only from the owner's figures plus fixed platform statements."""
    sections = []
    goal, funds = c.get("goal_cents") or 0, c.get("use_of_funds") or []
    if goal:
        lines = [f"- {i['item']}: {_rand(i['amount_cents'])}" for i in funds]
        sections.append({"key": "use_of_funds", "heading": "Where the money would go", "source": "owner_entered",
                         "body": f"Goal: {_rand(goal)}. Breakdown as entered by the owner (not independently verified):\n" + "\n".join(lines)})
    model = c.get("funding_model")
    if model in MODEL_STATEMENTS:
        sections.append({"key": "what_this_is", "heading": "What a contribution is", "source": "platform_statement",
                         "body": MODEL_STATEMENTS[model] + " Delivery of the plan is not guaranteed."})
    ms = c.get("milestones") or []
    if ms:
        sections.append({"key": "milestones", "heading": "Planned milestones", "source": "owner_entered",
                         "body": "\n".join(f"- {m['title']}" + (f" (target {m['target_date']})" if m.get("target_date") else "")
                                           for m in ms)})
    return {"provider": "heuristic", "methodology_version": METHODOLOGY_VERSION, "sections": sections}

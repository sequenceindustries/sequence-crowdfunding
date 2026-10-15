"""Rule-based completeness analyser.

This is NOT a language model. It checks whether a deck's text covers each
expected topic and how much it says about it. It cannot judge whether claims are
true. It exists so the pipeline, report schema, scoring and tests work end to
end with no external credentials; a real LLM provider can replace it behind the
same interface."""
import re

from .base import AiProvider

METHODOLOGY_VERSION = "heuristic-1.0"

# category -> (weight, keywords). Weights sum to 100.
CATEGORIES = {
    "problem": (12, ["problem", "pain point", "challenge", "struggle", "gap"]),
    "solution": (12, ["solution", "we offer", "our product", "our service", "platform", "we provide"]),
    "market": (8, ["market", "tam", "sam", "customers", "industry size", "demand"]),
    "target_customer": (8, ["target", "customer segment", "persona", "who we serve", "users"]),
    "business_model": (10, ["business model", "pricing", "subscription", "commission", "we charge", "revenue per"]),
    "competition": (8, ["competitor", "competition", "alternative", "differentiat", "advantage"]),
    "marketing": (6, ["marketing", "acquisition", "go-to-market", "channel", "sales strategy"]),
    "financials": (8, ["revenue", "cost", "profit", "cash flow", "break-even", "projection", "margin"]),
    "funding_request": (8, ["funding", "raise", "seeking", "ask", "capital"]),
    "use_of_funds": (8, ["use of funds", "allocation", "we will spend", "budget", "proceeds"]),
    "team": (6, ["team", "founder", "experience", "ceo", "cto", "background"]),
    "traction": (6, ["traction", "pilot", "customers to date", "users to date", "growth", "validated", "milestone"]),
}

RECOMMENDATIONS = {
    "problem": "State the problem plainly, who has it, and how you know (interviews, data, first-hand experience).",
    "solution": "Describe what you offer and how it solves the stated problem, in one or two sentences.",
    "market": "Describe your market and cite a source for any size estimate you quote.",
    "target_customer": "Say exactly who your first customers are.",
    "business_model": "Explain how the business earns money: what is charged, to whom, and how often.",
    "competition": "Name real alternatives (including doing nothing) and say how you differ.",
    "marketing": "Explain how you will reach your first customers and what it will cost.",
    "financials": "Add your revenue and cost assumptions and mark which are estimates.",
    "funding_request": "State exactly how much you are asking for.",
    "use_of_funds": "Break the requested amount into line items that add up to the ask.",
    "team": "Show who is on the team and what relevant experience they have.",
    "traction": "Share evidence of progress you can prove, or say honestly that you are pre-launch.",
}

_CLAIM_PATTERNS = [
    r"\b(fastest|best|only|leading|number one|#1|revolutionary|guaranteed)\b",
    r"\b\d{2,3}\s?%\s+(growth|increase|market share)",
]


def _count_hits(text_lower: str, keywords):
    return sum(text_lower.count(k) for k in keywords)


def _category_score(hits: int) -> int:
    if hits == 0:
        return 0
    if hits == 1:
        return 40
    if hits <= 3:
        return 70
    return 100


class HeuristicProvider(AiProvider):
    name = "heuristic"
    external = False

    def review_campaign(self, campaign: dict) -> dict:
        from .campaign_checks import review_campaign

        return review_campaign(campaign)

    def draft_transparency(self, campaign: dict) -> dict:
        from .campaign_checks import draft_transparency

        return draft_transparency(campaign)

    def analyze_pitch_deck(self, text: str) -> dict:
        lower = (text or "").lower()
        words = len(re.findall(r"\w+", lower))
        scores, missing, weak, strong = {}, [], [], []
        total = 0.0
        for cat, (weight, kws) in CATEGORIES.items():
            score = _category_score(_count_hits(lower, kws))
            scores[cat] = score
            total += weight * score / 100
            if score == 0:
                missing.append(cat)
            elif score < 70:
                weak.append(cat)
            elif score == 100:
                strong.append(cat)

        unclear = []
        for pat in _CLAIM_PATTERNS:
            for m in re.finditer(pat, lower):
                unclear.append(f"Unsupported superlative or statistic: '{m.group(0)}' - add evidence or soften.")
        has_money = bool(re.search(r"\b(r|zar)\s?\d[\d\s,.]*", lower))
        fin_validate = []
        if scores["financials"] > 0:
            fin_validate.append("Revenue and cost figures in the deck are owner-supplied and have not been verified.")
        if scores["funding_request"] > 0 and not has_money:
            fin_validate.append("A funding request is mentioned but no rand amount was detected.")
        if scores["use_of_funds"] > 0 and not has_money:
            fin_validate.append("Use of funds is mentioned but no rand amounts were detected.")

        if words < 150:
            weak.append("length")

        return {
            "provider": self.name,
            "methodology_version": METHODOLOGY_VERSION,
            "overall_completeness_score": round(total),
            "category_scores": scores,
            "strengths": [f"Covers '{c}' in some depth." for c in strong],
            "weaknesses": [
                f"'{c}' is only briefly covered." if c != "length" else "The deck contains very little text."
                for c in weak
            ],
            "missing_sections": missing,
            "unclear_claims": unclear[:10],
            "financial_assumptions_to_validate": fin_validate,
            "recommendations": [RECOMMENDATIONS[c] for c in missing + [w for w in weak if w in RECOMMENDATIONS]],
            "next_steps": [
                "Address the missing sections first.",
                "Have someone unfamiliar with the business read the deck and say what is unclear.",
                "Gather documents that support your factual claims.",
            ],
            "methodology": {
                "type": "rule-based keyword coverage (not a language model)",
                "scoring": "Each of 12 topics scores 0 (no mention), 40 (1 mention), 70 (2-3) or 100 (4+) from keyword counts, "
                "then topics are weighted (weights sum to 100) into an overall completeness score.",
                "weights": {c: w for c, (w, _) in CATEGORIES.items()},
            },
            "disclaimers": [
                "This score measures how completely the deck covers expected topics. It is not a prediction of fundraising success.",
                "Professional wording does not make a claim true. Nothing here has been verified.",
            ],
        }

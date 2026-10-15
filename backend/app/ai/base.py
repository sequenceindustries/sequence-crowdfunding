"""Provider-independent AI layer. Feature code depends only on this interface."""
from abc import ABC, abstractmethod


class AiProviderError(Exception):
    pass


class AiProvider(ABC):
    name = "base"
    # True when document text leaves our infrastructure. External providers
    # require explicit user consent before any confidential text is sent.
    external = False

    @abstractmethod
    def analyze_pitch_deck(self, text: str) -> dict:
        """Return a structured report matching ai.report.REPORT_KEYS."""

    def review_campaign(self, campaign: dict) -> dict:
        """Return a campaign-quality review (checks, compliance flags). Optional capability."""
        raise AiProviderError("not_supported")

    def draft_transparency(self, campaign: dict) -> dict:
        """Return {'sections': [...]} built only from the supplied campaign data. Optional capability."""
        raise AiProviderError("not_supported")


REPORT_KEYS = (
    "provider", "methodology_version", "overall_completeness_score", "category_scores",
    "strengths", "weaknesses", "missing_sections", "unclear_claims",
    "financial_assumptions_to_validate", "recommendations", "next_steps",
    "methodology", "disclaimers",
)

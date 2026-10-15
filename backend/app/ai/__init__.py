from datetime import datetime, timedelta, timezone

from flask import current_app

from ..extensions import db
from ..models import AiUsage
from .base import AiProvider, AiProviderError, REPORT_KEYS
from .heuristic import HeuristicProvider

DAILY_LIMIT_PER_USER = 20

_PROVIDERS = {"mock": HeuristicProvider, "heuristic": HeuristicProvider}


def register_provider(name, cls):
    _PROVIDERS[name] = cls


def get_provider() -> AiProvider:
    name = current_app.config["AI_PROVIDER"]
    try:
        return _PROVIDERS[name]()
    except KeyError as exc:
        raise AiProviderError(f"Unknown AI provider '{name}'.") from exc


def usage_today(user_id: int) -> int:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    return AiUsage.query.filter(AiUsage.user_id == user_id, AiUsage.created_at >= since).count()


def run_pitch_deck_analysis(user_id: int, text: str, consent_external: bool = False):
    """Run an analysis with usage limits, consent checks and structured-output validation."""
    provider = get_provider()
    if provider.external and not consent_external:
        raise AiProviderError("consent_required")
    if usage_today(user_id) >= DAILY_LIMIT_PER_USER:
        raise AiProviderError("usage_limit_reached")
    ok = False
    try:
        report = provider.analyze_pitch_deck(text)
        missing = [k for k in REPORT_KEYS if k not in report]
        if missing:
            raise AiProviderError(f"Provider returned an incomplete report (missing {missing}).")
        ok = True
        return provider.name, report
    except AiProviderError:
        raise
    except Exception as exc:
        raise AiProviderError("provider_failed") from exc
    finally:
        db.session.add(
            AiUsage(
                user_id=user_id, feature="pitch_deck_analysis", provider=provider.name,
                input_chars=len(text or ""), ok=ok,
            )
        )
        db.session.commit()


def run_campaign_feature(user_id: int, feature: str, method: str, campaign: dict):
    """Run an optional provider capability on a campaign draft with the same guards as deck analysis.
    Drafts are not public yet, so an external provider needs explicit consent (not wired for any
    external provider today, so it is always refused)."""
    provider = get_provider()
    if provider.external:
        raise AiProviderError("consent_required")
    if usage_today(user_id) >= DAILY_LIMIT_PER_USER:
        raise AiProviderError("usage_limit_reached")
    ok = False
    try:
        result = getattr(provider, method)(campaign)
        ok = True
        return provider.name, result
    except AiProviderError:
        raise
    except Exception as exc:
        raise AiProviderError("provider_failed") from exc
    finally:
        db.session.add(AiUsage(user_id=user_id, feature=feature, provider=provider.name,
                               input_chars=len(str(campaign)), ok=ok))
        db.session.commit()

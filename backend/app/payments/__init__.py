from flask import current_app

from .base import PaymentProvider
from .mock import MockProvider

_PROVIDERS = {"mock": MockProvider}


def register_provider(name, cls):
    _PROVIDERS[name] = cls


def get_provider() -> PaymentProvider:
    name = current_app.config["PAYMENT_PROVIDER"]
    try:
        return _PROVIDERS[name]()
    except KeyError as exc:
        raise RuntimeError(f"Unknown payment provider '{name}'.") from exc


def active_mode() -> str:
    """'off', 'simulated' or 'live'. A mode that does not match the provider is treated as off,
    so a test provider can never take real money and a live provider is never called test mode."""
    mode = current_app.config["CONTRIBUTIONS_MODE"]
    if mode not in ("simulated", "live"):
        return "off"
    try:
        provider = get_provider()
    except RuntimeError:
        return "off"
    if mode == "simulated" and provider.simulated:
        return "simulated"
    if mode == "live" and not provider.simulated:
        return "live"
    return "off"

"""Payment provider interface.

No real provider is selected or approved. Providers declare whether they are
simulated; simulated money is never counted as raised or as revenue."""
import hashlib
import hmac
from abc import ABC, abstractmethod


class PaymentProvider(ABC):
    name = "base"
    simulated = True

    @abstractmethod
    def create_checkout(self, payment) -> dict:
        """Return {"provider_ref": str, "checkout_url": str | None, ...}."""

    @abstractmethod
    def request_refund(self, payment, amount_cents: int) -> dict:
        """Ask the provider to refund. The outcome arrives later by webhook."""


def sign_payload(secret: str, raw: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def signature_valid(secret: str, raw: bytes, header: str) -> bool:
    if not secret:  # never accept anything when no secret is configured
        return False
    return hmac.compare_digest(sign_payload(secret, raw).encode(), (header or "").encode("utf-8", "ignore"))

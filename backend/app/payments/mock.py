import secrets

from .base import PaymentProvider


class MockProvider(PaymentProvider):
    """Development provider. Nothing is charged. Outcomes are delivered by a signed webhook,
    which you can trigger with `flask mock-pay <provider_ref>`."""

    name = "mock"
    simulated = True

    def create_checkout(self, payment) -> dict:
        return {"provider_ref": "mock_" + secrets.token_hex(8), "checkout_url": None}

    def request_refund(self, payment, amount_cents: int) -> dict:
        return {"provider_refund_ref": "mockrf_" + secrets.token_hex(6)}

from __future__ import annotations
import uuid
from .base import PaymentProvider, PaymentIntent

class DummyProvider(PaymentProvider):
    name = "dummy"

    async def create_intent(self, amount_cents: int, currency: str, description: str) -> PaymentIntent:
        ext = str(uuid.uuid4())
        # заглушка, но архитектура настоящая
        url = f"https://example.com/pay?pid={ext}"
        return PaymentIntent(external_id=ext, pay_url=url)

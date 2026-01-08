from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class PaymentIntent:
    external_id: str
    pay_url: str

class PaymentProvider:
    name: str
    async def create_intent(self, amount_cents: int, currency: str, description: str) -> PaymentIntent:
        raise NotImplementedError

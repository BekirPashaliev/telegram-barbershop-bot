from __future__ import annotations

from app.payments.dummy import DummyProvider
from app.database.requests import create_payment

PROVIDERS = {
    "dummy": DummyProvider(),
}

async def create_payment_for_appointment(session, provider_name: str, amount_cents: int, currency: str, description: str):
    prov = PROVIDERS[provider_name]
    intent = await prov.create_intent(amount_cents, currency, description)
    p = await create_payment(session, provider=prov.name, amount_cents=amount_cents, currency=currency, external_id=intent.external_id, pay_url=intent.pay_url)
    return p

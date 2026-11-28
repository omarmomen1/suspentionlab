import os
import pytest
from httpx import AsyncClient
from unittest.mock import patch, MagicMock, AsyncMock
from sqlalchemy import select

from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.billing import StripeEvent
from suspensionlab.shared.models import PlanTier

@pytest.mark.asyncio
async def test_webhook_enterprise_e2e_upgrade_downgrade(client: AsyncClient, db_session, mock_redis):
    customer_id = "cus_ent_123"
    user = User(
        email="enterprise@test.com",
        password_hash="fake",
        plan=PlanTier.FREE,
        billing_customer_id=customer_id
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    from suspensionlab.backend.api.routes import billing_routes
    os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test"
    os.environ["STRIPE_ENTERPRISE_PRICE_ID"] = "price_ent_test"

    class MockStripeObject(dict):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.__dict__.update(kwargs)

    mock_event_upgrade = {
        "id": "evt_ent_upgrade_123",
        "type": "customer.subscription.updated",
        "data": {
            "object": MockStripeObject(
                customer=customer_id,
                items=MockStripeObject(data=[{"price": {"id": "price_ent_test"}}]),
                status="active",
                id="sub_ent_123"
            )
        }
    }

    with patch("stripe.Webhook.construct_event", return_value=mock_event_upgrade):
        response = await client.post(
            "/api/v1/billing/webhooks/stripe",
            json={"id": "evt_ent_upgrade_123"},
            headers={"stripe-signature": "test_sig"}
        )

    assert response.status_code == 200
    
    await db_session.refresh(user)
    assert user.plan == PlanTier.ENTERPRISE
    
    # Idempotency Test (Duplicate webhook ID)
    with patch("stripe.Webhook.construct_event", return_value=mock_event_upgrade):
        response2 = await client.post(
            "/api/v1/billing/webhooks/stripe",
            json={"id": "evt_ent_upgrade_123"},
            headers={"stripe-signature": "test_sig"}
        )

    assert response2.status_code == 200
    assert response2.json() == {"received": True, "message": "Duplicate event ignored"}

    # Downgrade Test
    mock_event_downgrade = {
        "id": "evt_ent_downgrade_456",
        "type": "customer.subscription.deleted",
        "data": {
            "object": MagicMock(
                customer=customer_id,
                __getitem__=lambda self, key: "sub_ent_123" if key == "id" else None
            )
        }
    }

    with patch("stripe.Webhook.construct_event", return_value=mock_event_downgrade):
        response3 = await client.post(
            "/api/v1/billing/webhooks/stripe",
            json={"id": "evt_ent_downgrade_456"},
            headers={"stripe-signature": "test_sig"}
        )

    assert response3.status_code == 200
    await db_session.refresh(user)
    assert user.plan == PlanTier.FREE

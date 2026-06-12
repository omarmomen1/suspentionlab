import pytest
from httpx import AsyncClient
from unittest.mock import patch, MagicMock, AsyncMock
from sqlalchemy import select

from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.billing import StripeEvent
from suspensionlab.shared.models import PlanTier

@pytest.mark.asyncio
async def test_webhook_enterprise_e2e_upgrade_downgrade(client: AsyncClient, db_session):
    customer_id = "cus_ent_123"
    user = User(
        email="enterprise@test.com",
        password_hash="fake",
        plan=PlanTier.FREE,
        stripe_customer_id=customer_id
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    from suspensionlab.backend.api.routes import billing_routes
    billing_routes.STRIPE_WEBHOOK_SECRET = "whsec_test"
    billing_routes.STRIPE_ENTERPRISE_PRICE_ID = "price_ent_test"

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
        with patch("suspensionlab.backend.api.routes.optimize.async_redis_conn", new_callable=MagicMock) as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)
            mock_redis.set = AsyncMock(return_value=True)
            mock_redis.setex = AsyncMock(return_value=True)
            
            response = await client.post(
                "/billing/webhooks/stripe",
                json={"id": "evt_ent_upgrade_123"},
                headers={"stripe-signature": "test_sig"}
            )

    assert response.status_code == 200
    
    await db_session.refresh(user)
    assert user.plan == PlanTier.ENTERPRISE
    
    # Idempotency Test (Duplicate webhook ID)
    with patch("stripe.Webhook.construct_event", return_value=mock_event_upgrade):
        with patch("suspensionlab.backend.api.routes.optimize.async_redis_conn", new_callable=MagicMock) as mock_redis:
            # Emulate redis cache miss, so it tries DB insert and hits IntegrityError
            mock_redis.get = AsyncMock(return_value=None)
            mock_redis.set = AsyncMock(return_value=True)
            mock_redis.setex = AsyncMock(return_value=True)
            
            response2 = await client.post(
                "/billing/webhooks/stripe",
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
        with patch("suspensionlab.backend.api.routes.optimize.async_redis_conn", new_callable=MagicMock) as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)
            mock_redis.set = AsyncMock(return_value=True)
            mock_redis.setex = AsyncMock(return_value=True)
            
            response3 = await client.post(
                "/billing/webhooks/stripe",
                json={"id": "evt_ent_downgrade_456"},
                headers={"stripe-signature": "test_sig"}
            )

    assert response3.status_code == 200
    await db_session.refresh(user)
    assert user.plan == PlanTier.FREE

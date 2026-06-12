import pytest
from httpx import AsyncClient
from unittest.mock import patch, MagicMock
from sqlalchemy import select

from suspensionlab.backend.database.models.user import User
from suspensionlab.shared.models import PlanTier

@pytest.mark.asyncio
async def test_stripe_webhook_updates_user_plan(client: AsyncClient, db_session):
    # 1. Create a user with a known stripe_customer_id
    customer_id = "cus_test_12345"
    user = User(
        email="webhook@test.com",
        password_hash="fake",
        plan=PlanTier.FREE,
        stripe_customer_id=customer_id
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    user_id = user.id

    assert user.plan == PlanTier.FREE

    # 2. Prepare mock event payload
    import os
    test_price_id = os.getenv("STRIPE_PRO_PRICE_ID", "price_pro_fake")
    
    from suspensionlab.backend.api.routes import billing_routes
    billing_routes.STRIPE_WEBHOOK_SECRET = "whsec_test"
    billing_routes.STRIPE_PRO_PRICE_ID = "price_pro_test"
    
    mock_event = {
        "id": "evt_test_123",
        "type": "customer.subscription.created",
        "data": {
            "object": MagicMock(
                customer=customer_id,
                items=MagicMock(data=[{"price": {"id": "price_pro_test"}}]),
                status="active",
                __getitem__=lambda self, key: "sub_123" if key == "id" else None
            )
        }
    }

    # 3. Mock the webhook constructor and hit the endpoint
    with patch("stripe.Webhook.construct_event", return_value=mock_event):
        with patch("suspensionlab.backend.api.routes.optimize.async_redis_conn", new_callable=MagicMock) as mock_redis:
            from unittest.mock import AsyncMock
            mock_redis.get = AsyncMock(return_value=None)
            mock_redis.set = AsyncMock(return_value=True)
            mock_redis.setex = AsyncMock(return_value=True)
            response = await client.post(
                "/billing/webhooks/stripe",
                json={"id": "evt_test_123"},
                headers={"stripe-signature": "test_sig"}
            )

    # 4. Assert response and database change
    assert response.status_code == 200
    assert response.json() == {"received": True}

    # Refresh user from DB
    result = await db_session.execute(select(User).where(User.id == user_id))
    updated_user = result.scalar_one()

    assert updated_user.plan == PlanTier.PRO
    assert updated_user.stripe_subscription_id == "sub_123"

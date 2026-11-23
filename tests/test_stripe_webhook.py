import pytest
from httpx import AsyncClient
from unittest.mock import patch, MagicMock
from sqlalchemy import select

from suspensionlab.backend.database.models.user import User
from suspensionlab.shared.models import PlanTier

@pytest.mark.asyncio
async def test_stripe_webhook_updates_user_plan(client: AsyncClient, db_session):
    # 1. Create a user with a known billing_customer_id
    customer_id = "cus_test_12345"
    user = User(
        email="webhook@test.com",
        password_hash="fake",
        plan=PlanTier.FREE,
        billing_customer_id=customer_id
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
    
    class FakeObject:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
        def get(self, key, default=None):
            return self.__dict__.get(key, default)

    mock_event = {
        "id": "evt_test_123",
        "type": "customer.subscription.created",
        "data": {
            "object": FakeObject(
                customer=customer_id,
                items=FakeObject(data=[{"price": {"id": "price_pro_test"}}]),
                status="active",
                id="sub_123"
            )
        }
    }

    # 3. Mock the webhook constructor and hit the endpoint
    with patch("stripe.Webhook.construct_event", return_value=mock_event):
        response = await client.post(
            "/api/v1/billing/webhooks/stripe",
            json={"id": "evt_test_123"},
            headers={"stripe-signature": "test_sig"}
        )

    # 4. Assert response and database change
    assert response.status_code == 200
    assert response.json() == {"received": True}

    # Refresh user from DB
    await db_session.refresh(user)
    updated_user = user

    assert updated_user.plan == PlanTier.PRO
    assert updated_user.billing_subscription_id == "sub_123"


@pytest.mark.asyncio
async def test_stripe_webhook_links_user_by_client_reference_id(client: AsyncClient, db_session):
    # 1. Create a user without a billing_customer_id
    user = User(
        email="new_sub@test.com",
        password_hash="fake",
        plan=PlanTier.FREE,
        billing_customer_id=None,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    user_id = str(user.id)
    new_customer_id = "cus_brand_new_999"

    from suspensionlab.backend.api.routes import billing_routes
    billing_routes.STRIPE_WEBHOOK_SECRET = "whsec_test"
    billing_routes.STRIPE_PRO_PRICE_ID = "price_pro_test"

    class FakeObject:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
        def get(self, key, default=None):
            return self.__dict__.get(key, default)

    mock_event = {
        "id": "evt_test_ref_456",
        "type": "customer.subscription.created",
        "data": {
            "object": FakeObject(
                customer=new_customer_id,
                client_reference_id=user_id,
                metadata={"user_id": user_id},
                items=FakeObject(data=[{"price": {"id": "price_pro_test"}}]),
                status="active",
                id="sub_ref_456"
            )
        }
    }

    with patch("stripe.Webhook.construct_event", return_value=mock_event):
        response = await client.post(
            "/api/v1/billing/webhooks/stripe",
            json={"id": "evt_test_ref_456"},
            headers={"stripe-signature": "test_sig"}
        )

    assert response.status_code == 200
    assert response.json() == {"received": True}

    await db_session.refresh(user)
    assert user.plan == PlanTier.PRO
    assert user.billing_customer_id == new_customer_id
    assert user.billing_subscription_id == "sub_ref_456"

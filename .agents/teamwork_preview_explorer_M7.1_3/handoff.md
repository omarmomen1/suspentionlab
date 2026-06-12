# Stripe Webhook E2E Smoke Test Strategy

## Summary
The codebase contains two separate Stripe webhook integrations. The relevant integration for "Enterprise" subscriptions resides in `src/suspensionlab/backend/api/routes/billing_routes.py`, which listens on `POST /billing/webhooks/stripe`. The strategy is to write tests simulating Stripe `customer.subscription.updated` and `customer.subscription.deleted` events to verify `PlanTier.ENTERPRISE` upgrades and downgrades.

## 1. Observation
- `src/suspensionlab/backend/api/routes/billing_routes.py` has a webhook endpoint (`/billing/webhooks/stripe`) that explicitly maps `STRIPE_ENTERPRISE_PRICE_ID` to `PlanTier.ENTERPRISE` and handles `customer.subscription.*` events.
- `src/suspensionlab/backend/billing/webhooks.py` has another webhook endpoint (`/billing/webhook`) that listens to `checkout.session.completed` events and does not enforce specific plan names, relying instead on session metadata. 
- `tests/test_stripe_webhook.py` only contains a single test (`test_stripe_webhook_updates_user_plan`) verifying a `PRO` plan upgrade using the `customer.subscription.created` event.
- `suspensionlab/shared/models.py` defines `PlanTier.ENTERPRISE`.

## 2. Logic Chain
1. **Target Identification:** Since the task specifies testing "Enterprise" upgrades/downgrades, the target must be `billing_routes.py`, which manages the `ENTERPRISE` tier explicitly.
2. **Missing Coverage:** The existing tests do not cover `customer.subscription.updated` (used for upgrades/downgrades from other tiers) nor `customer.subscription.deleted` (used for cancellations).
3. **Test Flow Strategy:** 
   - We need to create a new async test function in `tests/test_stripe_webhook.py` (e.g., `test_enterprise_subscription_lifecycle`).
   - Setup a dummy user with `PlanTier.FREE` and mock `STRIPE_ENTERPRISE_PRICE_ID` in `billing_routes`.
   - **Step 1 (Upgrade):** Patch `stripe.Webhook.construct_event` to return a `customer.subscription.updated` event containing the enterprise price ID and `status="active"`. Send a POST request to `/billing/webhooks/stripe`. Assert the user's tier in the DB updates to `ENTERPRISE`.
   - **Step 2 (Cancellation/Downgrade):** Patch the construct event again to return a `customer.subscription.deleted` event (or `updated` with `status="canceled"`) for the same customer. Send the POST request. Assert the user's tier reverts to `FREE`.

## 3. Caveats
- **Conflicting Webhooks:** The application currently registers two different webhook routers in `main.py` (`app.include_router(billing_router)` and `app.include_router(webhooks.router)`). The implementer should be aware of this duplication, although only `/billing/webhooks/stripe` needs to be tested for this specific requirement.
- **Mocking vs. True E2E:** We are patching `stripe.Webhook.construct_event` to bypass signature validation. While not a "true" E2E test hitting Stripe servers, this is the established pattern in the codebase for smoke testing webhooks without requiring external network dependencies or Stripe CLI in CI/CD.

## 4. Conclusion
To implement the End-to-End smoke test, expand `tests/test_stripe_webhook.py` to include a full lifecycle test for the Enterprise tier. This test will mock the Stripe signature verification, send JSON payloads for `customer.subscription.updated` (active) and `customer.subscription.deleted` events, and verify that the database correctly transitions the user's plan between `FREE` and `ENTERPRISE`.

## 5. Verification Method
1. Inspect the implementation in `tests/test_stripe_webhook.py` to ensure tests for Enterprise upgrades and downgrades are present.
2. Run `python -m pytest tests/test_stripe_webhook.py`.
3. The test suite should pass 100%, indicating that the mock payloads were successfully processed by the API and the database state was correctly updated.

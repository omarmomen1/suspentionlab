# Handoff Report: E2E Smoke Test for Stripe Webhook (M7.1)

## 1. Observation
- The application exposes **two** separate Stripe webhook endpoints via `src/suspensionlab/backend/api/main.py`:
  1. `app.include_router(billing_router)` includes `/billing/webhooks/stripe` (defined in `src/suspensionlab/backend/api/routes/billing_routes.py`). This endpoint explicitly handles `customer.subscription.created`, `.updated`, and `.deleted`. It queries the `User` and maps `STRIPE_ENTERPRISE_PRICE_ID` to `PlanTier.ENTERPRISE` or downgrades the user to `PlanTier.FREE` on deletion.
  2. `app.include_router(webhooks.router)` includes `/billing/webhook` (defined in `src/suspensionlab/backend/billing/webhooks.py`). This endpoint handles only `checkout.session.completed` and uses a `StripeEvent` database model to ensure idempotency.
- The existing test suite (`tests/test_stripe_webhook.py`) only tests the `PRO` plan for `/billing/webhooks/stripe`. It also circumvents the signature verification process by mocking the Stripe library (`with patch("stripe.Webhook.construct_event", ...)`).
- The M7.1 scope requires a "dedicated pytest script that successfully sends a mock payload to the Stripe webhook endpoint" to verify "enterprise subscription upgrades/downgrades are processed flawlessly" and verify "the user's tier is updated in the database."

## 2. Logic Chain
- Because M7.1 specifically requires checking the database update logic for Enterprise upgrades and downgrades, the test must hit the endpoint handling `customer.subscription.*` events (i.e., `/billing/webhooks/stripe`).
- To fulfill the "E2E smoke test" requirement without mocking internal validation libraries (like `stripe.Webhook.construct_event`), the dedicated test must manually compute a valid Stripe signature using the test payload and webhook secret. This guarantees the entire FastAPI routing, payload decoding, and Stripe signature verification stack is evaluated exactly as it would be in production.
- The dedicated test should first insert a `User` in `PlanTier.FREE` (with a known `stripe_customer_id`), send a validly signed `customer.subscription.updated` JSON payload referencing `STRIPE_ENTERPRISE_PRICE_ID`, and assert the database reflects `PlanTier.ENTERPRISE`.
- The test must then send a signed `customer.subscription.deleted` JSON payload for the same user and assert the database reflects `PlanTier.FREE` to cover the downgrade scenario.
- Given the architectural fragmentation of having duplicate webhook handlers, the strategy optionally recommends consolidating these endpoints into a single handler. However, for the immediate scope, testing `/billing/webhooks/stripe` is correct.

## 3. Caveats
- Since the codebase currently implements idempotency (`StripeEvent` table insertion) only in `webhooks.py` and not in `billing_routes.py`, the E2E test will not validate idempotency unless the handlers are consolidated and idempotency logic is ported over.
- The dynamic generation of Stripe signatures relies on internal methods (e.g., `stripe.WebhookSignature._compute_signature`) in the `stripe` python library.

## 4. Conclusion
The implementation strategy is as follows:
1. **Target**: Create a new file `tests/test_webhook_enterprise_e2e.py` (or rename the existing file to `tests/test_webhook_e2e.py` and expand it).
2. **Setup**: Use `AsyncClient` and the `db_session` fixture to seed a User with a `stripe_customer_id` and `PlanTier.FREE`. Set `STRIPE_WEBHOOK_SECRET` and `STRIPE_ENTERPRISE_PRICE_ID` in the environment configuration via fixtures.
3. **E2E Signature Validation**: Write a helper to compute the `Stripe-Signature` dynamically (`t=<timestamp>,v1=<sig>`) using the secret, avoiding `patch` decorators and testing the real FastAPI payload parsing.
4. **Upgrade Test Case**: Issue a `POST /billing/webhooks/stripe` with a `customer.subscription.updated` payload containing the mocked Enterprise price ID. Assert response is `200 OK` and the user plan in DB is updated to `PlanTier.ENTERPRISE`.
5. **Downgrade Test Case**: Issue a `POST /billing/webhooks/stripe` with a `customer.subscription.deleted` payload for the same user. Assert response is `200 OK` and the user plan in DB reverts to `PlanTier.FREE`.
6. **Refactor Recommendation**: Consolidate `webhooks.py` and `billing_routes.py` into a single endpoint to avoid duplicate logic.

## 5. Verification Method
- **Run the tests**: Execute `pytest tests/test_webhook_enterprise_e2e.py -v`.
- **Invalidation Condition**: The strategy fails if the webhook signature cannot be computed locally resulting in a `400 Invalid signature`, or if the test fails to trigger the `customer.subscription.*` logic in `billing_routes.py`.

# Handoff Report: E2E Smoke Test Strategy for Stripe Webhooks

## Observation
- **Observation 1:** There are two overlapping Stripe webhook endpoints in the codebase:
  - `src/suspensionlab/backend/billing/webhooks.py` defines `POST /billing/webhook`, which handles `checkout.session.completed` for upgrades. It stores events in the `StripeEvent` table.
  - `src/suspensionlab/backend/api/routes/billing_routes.py` defines `POST /billing/webhooks/stripe`, which handles `customer.subscription.created`, `customer.subscription.updated`, and `customer.subscription.deleted`. It supports both `PRO` and `ENTERPRISE` tiers using `STRIPE_PRO_PRICE_ID` and `STRIPE_ENTERPRISE_PRICE_ID`.
- **Observation 2:** Both routers are registered simultaneously in `src/suspensionlab/backend/api/main.py`.
- **Observation 3:** The idempotency middleware (`src/suspensionlab/backend/security/idempotency.py`) explicitly matches `^/billing/webhook$` and hardcodes `path == "/billing/webhook"`. It extracts the Stripe event ID to prevent duplicate processing.
- **Observation 4:** The `/billing/webhooks/stripe` endpoint lacks idempotency protection (both middleware and DB-level `StripeEvent` logging), making it vulnerable to duplicate webhook deliveries from Stripe.
- **Observation 5:** `tests/test_stripe_webhook.py` only tests the `PRO` plan upgrade against `/billing/webhooks/stripe`. No tests exist for enterprise upgrades or downgrades.

## Logic Chain
1. To fulfill the milestone of testing enterprise subscription upgrades and downgrades, the test must utilize the logic in `/billing/webhooks/stripe`, as it is the only endpoint that handles downgrades (`customer.subscription.deleted`) and explicitly references the enterprise price ID.
2. However, `/billing/webhooks/stripe` is currently bypassing the system's idempotency safeguards.
3. Therefore, the fix strategy must first unify the webhook logic:
   - Deprecate/remove `/billing/webhook` (`webhooks.py`) or merge its `StripeEvent` DB insertion logic into `/billing/webhooks/stripe` (`billing_routes.py`).
   - Update `IdempotencyMiddleware` in `idempotency.py` to match `^/billing/webhooks/stripe$`.
4. Once unified and secured, the E2E smoke test strategy requires a new pytest script (e.g., `tests/test_webhook_enterprise_e2e.py`) that uses `TestClient` or `AsyncClient` to:
   - Create a test `User` in the DB with a known `stripe_customer_id`.
   - Mock `stripe.Webhook.construct_event` to bypass Stripe's signature verification during the test.
   - Send a `POST` request with a `customer.subscription.created` or `updated` payload containing the `STRIPE_ENTERPRISE_PRICE_ID` and assert the user tier is updated to `PlanTier.ENTERPRISE` in the DB.
   - Send a `POST` request with a `customer.subscription.deleted` payload and assert the user tier is updated to `PlanTier.FREE`.

## Caveats
- I am assuming that `checkout.session.completed` (currently in `webhooks.py`) is redundant for tier management if `customer.subscription.created` is handled properly, or that both should be supported in the unified endpoint.
- Since the environment operates in CODE_ONLY mode without actual Stripe API access, the "E2E smoke test" relies on mocked webhook payloads injected into the FastAPI test client, satisfying the constraint: *"Must provide a dedicated pytest script that successfully sends a mock payload"*.

## Conclusion
The codebase suffers from split-brain webhook processing. To successfully implement the E2E smoke test for enterprise upgrades and downgrades, you must:
1. **Unify Webhooks**: Move the `StripeEvent` DB tracking into `/billing/webhooks/stripe` and update the `IdempotencyMiddleware` to protect this route. Remove the redundant `/billing/webhook`.
2. **Implement the Test**: Create a dedicated pytest script (`test_webhook_enterprise_e2e.py`) that sends mock `customer.subscription.created` (with enterprise price ID) and `customer.subscription.deleted` payloads to `/billing/webhooks/stripe`, verifying the user's `plan` tier reflects `ENTERPRISE` and `FREE` respectively.

## Verification Method
1. Run `pytest tests/test_stripe_webhook.py` to ensure existing PRO tests still pass.
2. Verify the new E2E test runs successfully and catches plan changes: `pytest tests/test_webhook_enterprise_e2e.py`.
3. Verify idempotency protection: Send the exact same mock payload twice in the new test and assert that a duplicate `StripeEvent` is not processed and a `X-Idempotent-Replay: true` header is returned.

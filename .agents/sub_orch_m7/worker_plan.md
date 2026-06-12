# Worker Task: Stripe Webhook Enterprise E2E Test

## Context
The codebase suffers from a split-brain webhook processing issue. There are two overlapping webhook endpoints:
- `src/suspensionlab/backend/billing/webhooks.py`: `POST /billing/webhook` (Handles `checkout.session.completed`, has idempotency and `StripeEvent` DB tracking).
- `src/suspensionlab/backend/api/routes/billing_routes.py`: `POST /billing/webhooks/stripe` (Handles `customer.subscription.created`, `updated`, `deleted` for both PRO and ENTERPRISE tiers, but lacks idempotency protection).

## Instructions
1. **Unify Webhooks & Add Idempotency**: 
   - Move the `StripeEvent` DB tracking into the `/billing/webhooks/stripe` endpoint (or unify them so all events go through one endpoint). 
   - Update `IdempotencyMiddleware` (`src/suspensionlab/backend/security/idempotency.py`) to protect the unified endpoint. It currently hardcodes `path == "/billing/webhook"`. Make sure the endpoint that handles enterprise upgrades/downgrades is protected by idempotency.
   - Clean up any redundant router definitions in `main.py`.

2. **Implement Enterprise Smoke Test**:
   - Create a dedicated pytest script (e.g. `tests/test_webhook_enterprise_e2e.py` or add to `tests/test_stripe_webhook.py`).
   - Mock `stripe.Webhook.construct_event` to bypass Stripe signature verification.
   - Test **Upgrade**: Send a `POST` request with a `customer.subscription.updated` or `created` payload containing the enterprise price ID (`STRIPE_ENTERPRISE_PRICE_ID`). Assert the user's tier is updated to `PlanTier.ENTERPRISE`.
   - Test **Downgrade**: Send a `POST` request with a `customer.subscription.deleted` payload for the enterprise customer. Assert the user's tier is updated to `PlanTier.FREE`.
   - Test **Idempotency**: Send the exact same mock payload twice and assert that a duplicate `StripeEvent` is not processed and a `X-Idempotent-Replay: true` header is returned (or however idempotency handles duplicates).

3. **Verify**:
   - Run existing PRO tests: `pytest tests/test_stripe_webhook.py`
   - Run your new tests and verify they pass.
   - DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

4. **Output**:
   - Write your handoff report to `handoff.md` in your working directory and report back via send_message.

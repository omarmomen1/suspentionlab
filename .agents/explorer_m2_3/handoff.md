# Frontend Error Boundary & Edge Case Analysis

## Observation

1. **Missing Next.js Boundaries:** The `frontend/app` directory lacks `error.tsx`, `global-error.tsx`, and `loading.tsx` files entirely at the root and route levels (`auth`, `docs`, `garage`, `onboarding`, `pricing`, `settings`). 
2. **Unhandled Promise Rejections in `settings/page.tsx`:** 
   - `useEffect` data fetching (lines 56-59): `fetch` chain lacks a `.catch()` block.
   - `createKey` (lines 62-80): Uses `try...finally` with no `catch`.
   - `revokeKey` (lines 82-85): Lacks `try...catch` completely.
   - `openBillingPortal` (lines 93-102): Uses `try...finally` with no `catch`.
3. **Unsafe Array Manipulations in `garage/page.tsx`:**
   - `fetchProfiles` sets `profiles` to `await res.json()` directly if `res.ok` (line 59).
   - In `filtered` (line 91) and `typeCounts` (line 100), it loops over `profiles` assuming it is an array.
4. **Missing Fallbacks in `settings/page.tsx`:**
   - `badge` is accessed via `PLAN_BADGES[plan]` (line 49). If `user.plan` is an unexpected value, `badge` is undefined.

## Logic Chain

1. Without `error.tsx` at the root (`app/error.tsx`) or layout level, any unhandled JavaScript error during React rendering (in a client component or server component) will bubble up and crash the entire application, showing a stark Next.js default error overlay rather than a graceful fallback UI.
2. In `settings/page.tsx`, if the API server is unreachable, the network request in `useEffect`, `createKey`, or `revokeKey` will fail. Without a `.catch()` block, this results in an unhandled promise rejection. The user receives no visual feedback (toast/alert) that the operation failed.
3. In `garage/page.tsx`, if the API succeeds (`res.ok` is true) but returns a non-array response (e.g., an empty object `{}` due to a backend bug), `await res.json()` sets `profiles` to an object. Subsequent `useMemo` hooks calling `profiles.filter` or `profiles.forEach` will throw a `TypeError` and crash the application.
4. In `settings/page.tsx`, if `user.plan` returns a value not listed in `PLAN_BADGES` (e.g. `"pro"` instead of `"PRO"` or a new plan type), `badge` becomes `undefined`. Line 163 (`{badge.label}`) and line 162 (`${badge.color}`) will throw a `TypeError: Cannot read properties of undefined`, crashing the Settings page.

## Caveats

- I did not test the actual backend responses; the edge cases identified assume potential malformed API responses (e.g., non-arrays, unknown plan strings) or network failures.
- Only the specified routes were analyzed. Other modules (e.g., simulation routes like `quarter-car`) might have similar issues.
- It is assumed `authHeader()` does not throw an error synchronously.

## Conclusion

The application is highly vulnerable to rendering crashes and silent failures. To fix this:
1. **Implement Error Boundaries:** Create `app/error.tsx` (and potentially route-specific `error.tsx` files for `garage` and `settings`) to catch rendering exceptions gracefully.
2. **Fix `settings/page.tsx` API calls:** Add `.catch()` blocks or `catch` clauses in `try/catch` statements to all `fetch` calls, and display error messages to the user (e.g., via a toast or inline error state).
3. **Safeguard `garage/page.tsx`:** Validate `Array.isArray(data)` before setting `profiles` or use `Array.isArray(profiles) ? profiles.filter(...) : []`.
4. **Safeguard `settings/page.tsx` plan badge:** Add a fallback badge for unknown plans: `const badge = PLAN_BADGES[plan] ?? { label: "Unknown", color: "text-gray-500" };`.

## Verification Method

1. Run the frontend (`npm run dev`).
2. Simulate a network failure on the `Settings` page by taking the backend offline, and observe that errors are silently unhandled (check browser console).
3. Hardcode `plan = "UNKNOWN"` in `settings/page.tsx` and observe the page crash.
4. Inject a deliberate throw in a React component's render function to verify that the app crashes entirely (due to missing `error.tsx`).

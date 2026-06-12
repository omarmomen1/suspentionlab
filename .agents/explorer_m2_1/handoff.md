# Handoff Report: Frontend Route Analysis for Edge-Cases and Error Boundaries

## Observation
During my investigation of the Next.js routes (`active`, `digital-twin`, `full-car`, `half-car`, `handling`) inside `c:\Users\omaar\Downloads\project\frontend\app`, I observed the following:
1.  **Missing Route Boundaries**: A listing of the directory contents for all five routes revealed only `page.tsx` files. There are no `error.tsx` or `loading.tsx` files in any of these route directories.
2.  **Unsafe WebSocket Data Parsing**: In `digital-twin/page.tsx`, lines 35-36 use `const data = JSON.parse(event.data);` directly inside the `ws.onmessage` event listener without a surrounding `try...catch` block. 
3.  **Missing WebSocket Error Handling**: In `digital-twin/page.tsx`, there is no `ws.onerror` handler implemented to gracefully manage connection failures or provide informative user feedback.
4.  **Unsafe Data Mapping**: In `full-car/page.tsx`, `half-car/page.tsx`, and `handling/page.tsx`, the visualization components map over result arrays aggressively (e.g., `r.z_s.map`, `r.theta.map`, `r.a_y.map`). They do not use optional chaining (e.g., `r.z_s?.map`). 
5.  **Unsafe Mathematical Operations**: In `active/page.tsx`, `comfort_improvement` is calculated as `((results.passive_rms_accel - results.active_rms_accel) / Math.max(results.passive_rms_accel, 1e-6)) * 100`. There is no validation to ensure `passive_rms_accel` or `active_rms_accel` actually exist in the response payload before performing the math.

## Logic Chain
1.  **React Suspense and Error Boundaries**: In the Next.js App Router, `error.tsx` and `loading.tsx` are standard mechanisms. Without `error.tsx`, any unexpected runtime error (such as a mapping error or a third-party library crash like `react-plotly.js`) will bubble up and crash the entire React application tree, resulting in a blank white screen rather than a localized error message. The lack of `loading.tsx` prevents Next.js from rendering standard, route-level fallback skeletons during server navigation or async operations.
2.  **WebSocket Resilience**: If the DAQ WebSocket server (`ws://localhost:8000/telemetry/live`) returns malformed JSON or plain text errors, the unprotected `JSON.parse` will throw a `SyntaxError`, crashing the client side of the `digital-twin` route.
3.  **Missing Keys in Payload**: If the backend successfully returns a response but drops a specific key (e.g., omitting `z_s` from a half-car response due to optimization or a partial backend error), `r.z_s.map` will evaluate `undefined.map(...)`, which throws a `TypeError` and crashes the UI. Optional chaining (`r.z_s?.map(v => ...) ?? []`) is essential here.
4.  **Math on Undefined**: Passing `undefined` to `Math.max` evaluates to `NaN`. The result is then passed to `KPICard`, resulting in rendering text like `"NaN%"` on the screen instead of a graceful fallback.

## Caveats
- I did not inspect the backend logic or API schemas; it is possible the backend guarantees all response keys are consistently present, making the map errors theoretically unreachable under normal operation. However, edge-case UI programming dictates that the client must defensively handle missing payload keys regardless.
- I focused only on the explicitly requested directories. Other routes may have similar structural omissions.
- No modifications were made; this is purely a read-only analysis.

## Conclusion
The application is vulnerable to full-page crashes due to missing Next.js error boundaries (`error.tsx`), unhandled WebSocket JSON parsing, and unprotected array mapping.

**Implementation Recommendations:**
1.  **Add `error.tsx`**: Create an `error.tsx` file for each of the five routes (or a single generic one at the `app/` layout level) to catch React rendering failures gracefully.
2.  **Add `loading.tsx`**: Add `loading.tsx` to handle page transitions properly in the App Router.
3.  **Defensive JSON Parsing**: Wrap `JSON.parse(event.data)` in `digital-twin/page.tsx` with a `try...catch` block. Implement a `ws.onerror` event listener.
4.  **Optional Chaining**: Perform a regex replace in `active`, `full-car`, `half-car`, and `handling` `page.tsx` files to replace `.map(` with `?.map(` on all data payload references, and provide a fallback `?? []`.
5.  **Data Validation**: Validate numerical fields before calculating derived metrics like `comfort_improvement`.

## Verification Method
1. **Verify missing route files**: Run `ls c:\Users\omaar\Downloads\project\frontend\app\active` (etc.) and verify that `error.tsx` and `loading.tsx` do not exist.
2. **Verify JSON vulnerability**: Check `c:\Users\omaar\Downloads\project\frontend\app\digital-twin\page.tsx` at line 36.
3. **Verify mapping vulnerability**: Run `Select-String -Pattern "\.map" c:\Users\omaar\Downloads\project\frontend\app\full-car\page.tsx` and observe the lack of optional chaining (`?`) before `.map`.

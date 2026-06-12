# Frontend Edge-Cases and Error Boundaries Implementation Handoff

## Observation
- `error.tsx` and `loading.tsx` were missing across the Next.js `app` directory. 
- `digital-twin/page.tsx` directly used `JSON.parse` on WebSocket messages without `try...catch`, and lacked an `onerror` handler.
- Several pages (`full-car/page.tsx`, `half-car/page.tsx`, `handling/page.tsx`) were using `.map()` on potentially undefined backend result arrays without optional chaining.
- `active/page.tsx` was performing an unprotected `comfort_improvement` calculation (dividing and mapping on properties that might not exist or might be `undefined`).
- `quarter-car/page.tsx` was extracting variables dynamically in `useMemo` hooks (`forces`, `psdData`) and performing calculations on arrays without verifying their existence. KPI rendering was missing nullish fallbacks.
- `sensitivity/page.tsx` was rendering the `Plot` component even when the `X`, `Y`, and `Z` array matrices from results were malformed or non-existent.
- `settings/page.tsx` had multiple `fetch` calls leading to Unhandled Promise Rejections (e.g. `openBillingPortal`, `createKey`, `revokeKey`, `api-keys` fetching) and an unsafe badge access `PLAN_BADGES[plan]`.
- `garage/page.tsx` assumed `await res.json()` returned an array without validation, leading to `TypeError` during filtering.

## Logic Chain
- Adding `app/error.tsx` ensures unhandled React crashes bubble up to a global error boundary fallback instead of giving a white screen. `app/loading.tsx` provides a suspense boundary.
- Wrapping JSON parsing in `try...catch` and registering `ws.onerror` prevents silent or unhandled client-side crashes from WebSocket disconnects or bad payloads.
- Implementing optional chaining (`?.map()`) and `?? []` fallbacks on visualization loops ensures `react-plotly.js` correctly handles partial simulation data without unmounting the app.
- Checking types (`typeof === 'number'`) and conditionally executing math in `active/page.tsx` prevents `NaN` propagations.
- Enforcing `!zs || !zu` style checks before iterating in `useMemo` hooks (e.g., `quarter-car/page.tsx`) shields the frontend from evaluating maps over undefined state.
- Fallback badges (`PLAN_BADGES[plan] ?? {...}`) and `try...catch` fetch wrappers inside `settings/page.tsx` prevent crashes on unexpected plan strings and handle network failures natively.
- Using `Array.isArray(data)` before setting the profile states in `garage/page.tsx` avoids `TypeError: filter is not a function`.

## Caveats
- Global `app/error.tsx` handles broad boundary errors; specific route `error.tsx` instances can be added later if custom per-page fallback logic is required.
- The `digital-twin` websocket fix correctly suppresses console crashes but relies on prior states if the `JSON.parse` fails.
- The `.map()` regex replacements and array validations safely avoid `TypeError`s, though Plotly might render blank spaces or flat lines depending on the extent of missing payload variables.

## Conclusion
Edge-case protections and error boundaries have been integrated across all affected Next.js routes. Null safety and unhandled promise protections secure the core simulation loop components. The application is now significantly more resilient against backend anomalies, unexpected payload structures, and network timeouts.

## Verification Method
Run `npm run build` from the `frontend/` directory to ensure type safety and the correct implementation of the Next.js `error.tsx` boundary directive (`"use client"`). The app will compile successfully with no TypeScript errors (verified). Start the UI and purposefully trigger API failures (e.g., disable the backend) to confirm local fallbacks render without crashing the entire App tree.

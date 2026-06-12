# Handoff Report: Missing Error Boundaries & Edge-Case Protections

## 1. Observation
- **Missing File-based Boundaries**: A search (`grep_search` and directory listing via `list_dir`) across `frontend/app` and specifically the routes `kinematics`, `nvh`, `quarter-car`, and `sensitivity` revealed that no `error.tsx` or `loading.tsx` files exist.
- **Incomplete Next.js Suspense**: While `page.tsx` files (e.g., `kinematics/page.tsx:206`) wrap their dashboards in `<Suspense>`, this only handles the asynchronous loading of the dynamically imported component.
- **Data Edge-Case Protections in `quarter-car`**: 
  - In `quarter-car/page.tsx:299-313`, the `forces` `useMemo` destructures state variables (`zs`, `zu`, `vs`, `vu`) from `results` and maps over them directly (`zs.map(...)`).
  - In `quarter-car/page.tsx:268-283`, the `psdData` `useMemo` accesses `t[1] - t[0]` based purely on assuming `t` (from `results.time`) exists.
  - KPI rendering (e.g. `r.omega_n_s.toFixed(2)`) assumes all nested scalar properties are defined if `results.error` is false.
- **Data Edge-Case Protections in `sensitivity`**: 
  - `sensitivity/page.tsx:172` maps 3D coordinate matrices (`r.Z`, `r.X`, `r.Y`) into the `Plot` component directly, which requires complete datasets to render.
- **Network Errors**: Network errors are caught via standard `try/catch` wrapping `fetch()`, which sets `results.error = true` to display an inline error component (e.g. `quarter-car/page.tsx:495`). However, API JSON errors that still yield `HTTP 200` but omit critical data structure will bypass this protection.

## 2. Logic Chain
- The Next.js App Router relies on `error.tsx` to establish React Error Boundaries for routes. If a runtime exception occurs (such as a `TypeError` from an undefined property), the lack of `error.tsx` will cause the entire application to crash and unmount, leading to a blank screen instead of a graceful fallback UI.
- The `quarter-car` dashboard manually manages `isRunning` and sets a localized loading state. If the API returns a response that successfully parses (`HTTP 200`) but is structurally incomplete (e.g. missing `ddz_s` array or `omega_n_s` number), the condition `results.error` evaluates to `false`.
- Consequently, JS array operations (`map`, indexing) and number formatting (`toFixed`) will be called on `undefined`, triggering a `TypeError` during the React render cycle or within `useMemo`.
- Because there is no `error.tsx` boundary, this `TypeError` will crash the whole app. 

## 3. Caveats
- The `kinematics` and `nvh` dashboards perform their math synchronously without calling any backend endpoint. Consequently, they are immune to partial network response payloads. They only strictly require an `error.tsx` to handle any deeply unanticipated JS errors (like unexpected input types or math functions throwing).
- We have not inspected the backend codebase, so it may currently be fully type-safe and never return incomplete payloads. However, robust frontend design mandates defensive programming against malformed API responses.

## 4. Conclusion
1. **Add `error.tsx` and `loading.tsx`**: Implement route-level (or at minimum, a global `app/error.tsx`) error boundaries to capture unhandled React rendering crashes and provide graceful loading transitions.
2. **Defensive Checks in `quarter-car`**: 
   - Add nullish/optional checks in `forces` `useMemo`: `if (!zs || !zu || !vs || !vu) return null;`.
   - Add nullish checks in `psdData` `useMemo`: `if (!t || t.length < 2) return null;`.
   - Update JSX interpolations to use optional chaining: `r.omega_n_s?.toFixed(2) ?? 'N/A'`.
3. **Defensive Checks in `sensitivity`**:
   - Ensure the Plot component is conditionally rendered only if `r.X`, `r.Y`, and `r.Z` are truthy and correctly populated arrays.

## 5. Verification Method
- **To test the error boundary missing**: In `quarter-car/page.tsx`, temporarily inject `throw new Error("Test Crash")` inside the component render. The application will white-screen and crash. After adding `error.tsx`, the application will display the fallback UI.
- **To test data protections**: Modify the backend (`simulate` route) to return `{"status": "success"}` without any nested data arrays. Or manually stub `results` to be `{}`. Attempt to run the simulation. The application should gracefully display "no data" or fallback strings without throwing a `TypeError`.

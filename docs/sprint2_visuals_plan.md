# Sprint 2 visuals plan (prep, written against f53b5d0)

Line numbers are from `f53b5d0` (master after Wave 6 + UI v2 Phases 1-4). Sprint 1 edits `app/page.tsx`, `app/kinematics/page.tsx` and others, so numbers WILL shift. Re-find each anchor by the quoted text, not the number.

Rules that stay true: frontend only, at most one WebGL canvas per route, `next/dynamic(..., { ssr: false })`, replaced by 2D below `lg` (1024 px), missing data renders `EmptyState`, no invented numbers. Single lime accent `#C8F04B`, carbon `#0C0F12`, panel `#13181D`, 1 px hairlines.

## 0. What is already on this branch
`frontend/components/v2/LandingHero3D.tsx` (new, self-contained) and `frontend/tests/landingHero3D.test.ts` (3 tests on the linkage solve: rest pose, constant rigid lengths through bump and droop, bump lifts the wheel).
It is a schematic front-view (Y-Z) double wishbone using the default formula-car hardpoints from `app/kinematics/page.tsx` `DEFAULT_HP`. The motion is solved in this file. It is NOT the backend solver and prints no KPIs. Its caption says so.

## 1. Mount LandingHero3D on `/`  (`app/page.tsx`)
- Anchor: `<aside aria-label="What runs today" ...>` (line 95, `lg:col-span-5`) holding the "What runs today" card (line 96).
- Add near line 9: `import dynamic from "next/dynamic";` and
  `const LandingHero3D = dynamic(() => import("../components/v2/LandingHero3D"), { ssr: false, loading: () => <div className="h-[360px] border border-hairline bg-panel" /> });`
- Replace the card body with `<LandingHero3D className="lg:col-span-5" />`.
- Do NOT delete the evidence pointers (they are the honesty content). Move them into a `<details>` or a row under the hero.
- Below `lg`: render the existing card only (`hidden lg:block` on the hero, `lg:hidden` on the card). The landing has no other canvas, so the one-canvas rule holds.
- `CommandCenterWorkspace` (line 201) must be checked for a canvas before this ships (not inspected).

## 2. Lap-Sim: 3D Spa elevation ON by default, larger viewport  (`app/lap-sim/page.tsx`)
- Default: line 1191 `useState<boolean>(false)` -> `useState<boolean>(true)`. The payload still only sends `with_elevation` when the circuit is `spa` (line 1484), so non-Spa runs are unchanged.
- Cost: the elevation run was measured slower on the backend (Why Chain is about 10.6 s on Spa; elevation run time was not measured by this prep). Time a default Spa run before and after and say so in the UI.
- Viewport: `components/v2/instruments/TerrainElevation3D.tsx` line 96 `h-[240px]` -> `h-[360px] lg:h-[420px]`. Raise contrast: ribbon stroke is already lime; set the grid to `#2a3036`/`#1a2026` (already), add a 1 px lime baseline for z = min.
- Section wrapper `terrain-section` is at line 2632, rendered only after a result exists. To make it a primary view, lift it above `EnvelopePlot` (line 2625) so it is the first visual after the verdict.
- Copy fix needed regardless: line 2636 still says "Other circuits stay flat (z = 0)". The panel itself now shows EmptyState for non-Spa, so reword to "Only Spa has elevation data."
- Below `lg` the component already swaps the canvas for `ElevationProfile2D`.

## 3. Full-Car: surface "Footprints & Attitude"  (`app/full-car/page.tsx`)
- It is tab index 4 (label at line 58, body at line 712, `data-testid="footprints-attitude-tab"`), the last tab. `activeTab` default is 0 (line 207).
- Option A (small): after a successful run, `setActiveTab(4)`; keep tab order.
- Option B (primary view): move the tab to index 0 in the tab array (line 58) and renumber the `activeTab === n` blocks (lines 590 to 712), or render the scrubber plus footprints above the tab strip.
- The attitude canvas is already `next/dynamic` ssr:false and the `lg` fallback is FourFootprintsSVG, so only one canvas is ever mounted.

## 4. Kinematics: surface the Motion Ratio heatmap  (`app/kinematics/page.tsx`)
- Tab id `"mr"` is at line 1433. Two blocks use it: the Plotly MR curve (line 1740) and the field card `data-testid="mr-field-card"` (line 1787, `<MotionRatioField data={mrField} />` at 1799).
- Make the field card the first block in the MR tab, and keep the Plotly curve below it.
- To surface it in the primary (workspace) view: reuse `MotionRatioField` with the same `mrField` state in the `workspace` tab (line 1463). It needs a data call: either auto-run `computeMrField` after the first solve, or keep the button. Auto-run adds a backend call per solve; decide explicitly.
- The optional wheelbase input already gates Ackermann. Keep it.
- No new canvas on this route beyond the existing `SuspensionKinematics3D`. Do not mount `LandingHero3D` here.

## 5. Single lime accent
Out of scope for this branch (Sprint 1 owns it). After Sprint 1, grep for `#f2a900`, `#D97706`, `amber-`, `orange-` in `app/` and `components/v2/` and keep amber only for WARN status chips.

## 6. Verification checklist after merge
type-check; `npm test`; `npm run build`; open `/`, `/lap-sim`, `/full-car`, `/kinematics` at 1440 px and 390 px; confirm exactly one `<canvas>` per route in DevTools; confirm reduced-motion stops the hero animation.

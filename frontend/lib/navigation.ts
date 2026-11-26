/**
 * Navigation configuration and Studio Mode feature flag helpers
 * shared across desktop (Navbar) and mobile (MobileNav) navigation.
 */

export interface NavDropdownItem {
  href: string;
  label: string;
  desc?: string;
  aliases?: string[];
  badge?: string;
}

export type StudioIconKey =
  | "kinematics"
  | "quarter_car"
  | "full_car"
  | "correlation"
  | "optimizer"
  | "memory"
  | "ai"
  | "overview"
  | "studios"
  | "apexsim"
  | "telemetry"
  | "optimize"
  | "reports";

export interface StudioToolGroup {
  id: string;
  label: string;
  href: string;
  icon: StudioIconKey;
  dropdownAlign?: "left" | "right";
  routes: NavDropdownItem[];
}

export interface MobileNavSection {
  title: string;
  links: Array<{ href: string; label: string; aliases?: string[] }>;
}

/**
 * Feature flag controlling focused Studio Mode navigation.
 * Uses direct property access so Next.js statically inlines NEXT_PUBLIC_STUDIO_MODE.
 */
export function isStudioModeEnabled(): boolean {
  return process.env.NEXT_PUBLIC_STUDIO_MODE === "true";
}

export const STUDIO_PRICING_CTA = {
  href: "/pricing",
  label: "Pricing",
  mobileLabel: "Upgrade / Pricing",
  subtitle: "Unlock PRO & Enterprise capabilities",
} as const;

export function matchesRoute(
  pathname: string,
  href: string,
  aliases?: string[]
): boolean {
  const targets = [href, ...(aliases ?? [])];
  return targets.some(
    (target) => pathname === target || pathname.startsWith(target + "/")
  );
}

export function isToolGroupActive(
  pathname: string,
  routes: NavDropdownItem[]
): boolean {
  return routes.some((route) =>
    matchesRoute(pathname, route.href, route.aliases)
  );
}

/**
 * The 6 highest-impact visual engineering tools shown when NEXT_PUBLIC_STUDIO_MODE=true.
 */
export const STUDIO_TOOLS: StudioToolGroup[] = [
  {
    id: "kinematics",
    label: "3D Kinematics & Hardpoints",
    href: "/kinematics",
    icon: "kinematics",
    routes: [
      {
        href: "/kinematics",
        label: "3D Kinematics & Hardpoints",
        desc: "Roll centers, camber gain, bump steer & hardpoints",
      },
    ],
  },
  {
    id: "quarter-car",
    label: "Quarter-Car & Damper Studio",
    href: "/quarter-car",
    icon: "quarter_car",
    routes: [
      {
        href: "/quarter-car",
        label: "Quarter-Car & Damper Studio",
        desc: "2-DOF bounce, non-linear damper LUT & ISO 2631 comfort",
      },
    ],
  },
  {
    id: "full-car-handling",
    label: "Full-Car & Handling",
    href: "/full-car",
    icon: "full_car",
    dropdownAlign: "left",
    routes: [
      {
        href: "/full-car",
        label: "Full-Car (7-DOF)",
        desc: "4-corner multi-body heave, pitch & roll chassis solver",
      },
      {
        href: "/handling",
        label: "Handling Dynamics",
        desc: "Bicycle model, slip angles & transient yaw response",
      },
      {
        href: "/lap-sim",
        label: "Lap Simulator",
        desc: "Quasi-static track solver, bottleneck mapping & delta analysis",
        badge: "PRO",
      },
    ],
  },
  {
    id: "correlation-compare",
    label: "Telemetry & Setup Correlation",
    href: "/correlation",
    icon: "correlation",
    dropdownAlign: "left",
    routes: [
      {
        href: "/correlation",
        label: "Telemetry Correlation",
        desc: "Measured telemetry vs simulated physical correlation",
      },
      {
        href: "/compare",
        label: "Setup Compare (A vs B)",
        desc: "Side-by-side setup delta & physical tradeoff verification",
      },
      {
        href: "/investigate",
        label: "Investigation Room",
        desc: "Guided stage-by-stage telemetry investigation workflow",
      },
    ],
  },
  {
    id: "sensitivity-optimizer",
    label: "Setup Sensitivity & Optimizer",
    href: "/setup-sensitivity",
    icon: "optimizer",
    dropdownAlign: "right",
    routes: [
      {
        href: "/setup-sensitivity",
        label: "Setup Sensitivity",
        desc: "ARB balance, ride height & aero sensitivity sweeps",
      },
      {
        href: "/optimize",
        label: "Pareto Optimizer",
        desc: "Multi-objective comfort & tire-load frontier optimization",
      },
    ],
  },
  {
    id: "memory-reports",
    label: "Engineering Memory & Reports",
    href: "/engineering-memory",
    icon: "memory",
    dropdownAlign: "right",
    routes: [
      {
        href: "/engineering-memory",
        label: "Engineering Memory",
        desc: "Vehicle development timeline, diffs & signed decisions",
        aliases: ["/timeline"],
      },
      {
        href: "/report",
        label: "Engineering Reports",
        desc: "Executive simulation & compliance report export",
      },
      {
        href: "/cae",
        label: "CAE Interop (Adams / MATLAB)",
        desc: "MSC Adams, MATLAB & CarMaker import/export decks",
      },
    ],
  },
  {
    id: "ai-engineer",
    label: "AI Race Engineer",
    href: "/ai-engineer",
    icon: "ai",
    dropdownAlign: "right",
    routes: [
      {
        href: "/ai-engineer",
        label: "AI Race Engineer",
        desc: "Physics-grounded setup diagnosis, Copilot reasoning & sign-off",
      },
    ],
  },
  {
    id: "lap-sim",
    label: "Lap Time & Track Sim",
    href: "/lap-sim",
    icon: "full_car",
    dropdownAlign: "right",
    routes: [
      {
        href: "/lap-sim",
        label: "Lap Time & Track Sim",
        desc: "Quasi-static track solver, bottleneck mapping & delta analysis",
      },
    ],
  },
];

/**
 * Contextual "Next Step" workflow chain across the core studio pages:
 * 3D Kinematics -> Quarter-Car -> Full-Car / Lap Sim -> Investigate -> Memory & PDF.
 * Consumed by components/NextStepLink.tsx on each core studio page.
 */
export const STUDIO_WORKFLOW_CHAIN: { href: string; label: string; next?: { href: string; label: string } }[] = [
  { href: "/kinematics", label: "3D Kinematics", next: { href: "/quarter-car", label: "Quarter-Car & Damper Studio" } },
  { href: "/quarter-car", label: "Quarter-Car", next: { href: "/full-car", label: "Full-Car / Lap Sim" } },
  { href: "/full-car", label: "Full-Car", next: { href: "/lap-sim", label: "Lap Simulator" } },
  { href: "/lap-sim", label: "Lap Sim", next: { href: "/investigate", label: "Investigation Room" } },
  { href: "/investigate", label: "Investigate", next: { href: "/engineering-memory", label: "Memory & PDF" } },
];

export function nextStepFor(pathname: string): { href: string; label: string } | null {
  const entry = STUDIO_WORKFLOW_CHAIN.find((e) => e.href === pathname);
  return entry?.next ?? null;
}

export const ALL_SOLVER_ITEMS: NavDropdownItem[] = [
  { href: "/quarter-car", label: "Quarter Car (2-DOF)", desc: "Corner bounce, damping & ISO 2631 ride comfort" },
  { href: "/half-car",    label: "Half Car (4-DOF)",    desc: "Pitch & bounce pitch-center coupling solver" },
  { href: "/full-car",    label: "Full Car (7-DOF)",    desc: "4-corner multi-body dynamic chassis simulation" },
  { href: "/active",      label: "Active Suspension",   desc: "Skyhook / groundhook & LQR control systems" },
  { href: "/handling",    label: "Handling Dynamics",   desc: "Bicycle model, slip angles & transient yaw response" },
  { href: "/kinematics",  label: "Kinematics & Geometry", desc: "Roll centers, camber gain & bump steer curves" },
  { href: "/lap-sim",     label: "Lap Time Simulation", desc: "Quasi-static track solver & GG friction limits" },
  { href: "/yaw-dynamics",label: "Yaw Dynamics & MMM",  desc: "Milliken Moment Diagram & aerodynamic balance" },
  { href: "/nvh",         label: "NVH & Acoustics",     desc: "FFT frequency spectrum & cabin resonance isolation" },
];

export const VALIDATION_ITEMS: NavDropdownItem[] = [
  { href: "/correlation", label: "Correlation Cockpit", desc: "Measured telemetry vs simulated physical correlation" },
  { href: "/digital-twin",label: "Digital Twin",        desc: "Virtual vehicle state observer & continuous calibration" },
  { href: "/timeline",    label: "Timeline & Decisions", desc: "Vehicle development history, diffs & cryptographic sign-off" },
  { href: "/vnv",         label: "V&V Evidence Suite",  desc: "Numerical solver validation & test benchmarks" },
  { href: "/cae",         label: "CAE Interoperability", desc: "MSC Adams, MATLAB & CarMaker import/export decks" },
  { href: "/audit",       label: "Audit & Governance",  desc: "Tamper-evident cryptographic ledger" },
];

export const FULL_MOBILE_SECTIONS: MobileNavSection[] = [
  {
    title: "Hypothesis & Decisions",
    links: [
      { href: "/experiment", label: "⚗ 1-Click Experiment" },
      { href: "/compare", label: "⇄ Deep Compare (A vs B)" },
      { href: "/optimize", label: "✦ Pareto Optimizer" },
      { href: "/correlation", label: "⚡ Correlation Cockpit" },
      { href: "/timeline", label: "⏱ Timeline & Decisions" },
      { href: "/cae", label: "⛭ CAE Interoperability Hub" },
    ],
  },
  {
    title: "Simulation",
    links: [
      { href: "/quarter-car", label: "Quarter Car" },
      { href: "/half-car", label: "Half Car" },
      { href: "/full-car", label: "Full Car" },
      { href: "/active", label: "Active" },
      { href: "/handling", label: "Handling" },
    ],
  },
  {
    title: "Analysis",
    links: [
      { href: "/kinematics", label: "Kinematics" },
      { href: "/lap-sim", label: "Lap Sim" },
      { href: "/setup-sensitivity", label: "Setup Sensitivity" },
      { href: "/yaw-dynamics", label: "Yaw / MMM" },
      { href: "/digital-twin", label: "Digital Twin" },
      { href: "/sensitivity", label: "Sensitivity" },
      { href: "/nvh", label: "NVH" },
      { href: "/durability", label: "Durability" },
    ],
  },
  {
    title: "Workspace",
    links: [
      { href: "/ai-engineer", label: "✦ AI Engineer" },
      { href: "/garage", label: "Garage" },
      { href: "/pricing", label: "Pricing" },
      { href: "/docs", label: "Docs" },
    ],
  },
  {
    title: "Account",
    links: [
      { href: "/auth/login", label: "Sign In" },
      { href: "/auth/register", label: "Create Account" },
      { href: "/settings", label: "Settings" },
    ],
  },
];


/**
 * V2 workspace navigation (Phase 1): 7 groups, same data feeds desktop and mobile.
 * Every route from the previous Studio, Standard and mobile menus is still
 * reachable. /investigate lives under Telemetry, /cae under Reports.
 */
export const NAV_V2: StudioToolGroup[] = [
  {
    id: "overview",
    label: "Overview",
    href: "/garage",
    icon: "overview",
    dropdownAlign: "left",
    routes: [
      { href: "/garage", label: "Garage & Setup", desc: "Vehicle profiles and saved configurations" },
      { href: "/docs", label: "Docs", desc: "Guides, model assumptions and API reference" },
      { href: "/pricing", label: "Pricing", desc: "Free, Pro and Team plans" },
    ],
  },
  {
    id: "studios",
    label: "Studios",
    href: "/kinematics",
    icon: "studios",
    dropdownAlign: "left",
    routes: [
      { href: "/kinematics", label: "3D Kinematics & Hardpoints", desc: "Roll centers, camber gain, bump steer" },
      { href: "/quarter-car", label: "Quarter-Car & Damper Studio", desc: "2-DOF bounce, damper LUT, ISO 2631 comfort" },
      { href: "/half-car", label: "Half-Car (4-DOF)", desc: "Pitch and bounce coupling" },
      { href: "/full-car", label: "Full-Car (7-DOF)", desc: "4-corner heave, pitch and roll" },
      { href: "/handling", label: "Handling Dynamics", desc: "Bicycle model, slip angles, yaw response" },
      { href: "/yaw-dynamics", label: "Yaw Dynamics & MMM", desc: "Milliken Moment Diagram and aero balance" },
      { href: "/active", label: "Active Suspension", desc: "Skyhook, groundhook and LQR control" },
      { href: "/nvh", label: "NVH & Acoustics", desc: "FFT spectrum and resonance isolation" },
      { href: "/durability", label: "Durability", desc: "Load-cycle and fatigue estimates" },
    ],
  },
  {
    id: "apexsim",
    label: "ApexSim",
    href: "/lap-sim",
    icon: "apexsim",
    dropdownAlign: "left",
    routes: [
      { href: "/lap-sim", label: "ApexSim Lap Studio", desc: "Quasi-static track solver, bottleneck map, delta analysis", badge: "PRO" },
    ],
  },
  {
    id: "telemetry",
    label: "Telemetry",
    href: "/correlation",
    icon: "telemetry",
    dropdownAlign: "left",
    routes: [
      { href: "/correlation", label: "Correlation Cockpit", desc: "Measured telemetry vs simulation" },
      { href: "/investigate", label: "Investigation Room", desc: "Guided stage-by-stage telemetry investigation" },
      { href: "/digital-twin", label: "Digital Twin", desc: "State observer and continuous calibration" },
    ],
  },
  {
    id: "optimize",
    label: "Optimize",
    href: "/optimize",
    icon: "optimize",
    dropdownAlign: "right",
    routes: [
      { href: "/experiment", label: "1-Click Experiment", desc: "Hypothesis, candidate setups and constraint checks" },
      { href: "/optimize", label: "Pareto Optimizer", desc: "Comfort and tire-load frontier" },
      { href: "/compare", label: "Setup Compare (A vs B)", desc: "Side-by-side setup delta" },
      { href: "/setup-sensitivity", label: "Setup Sensitivity", desc: "ARB, ride height and aero sweeps" },
      { href: "/sensitivity", label: "Parameter Sensitivity", desc: "One-at-a-time parameter sweeps" },
    ],
  },
  {
    id: "reports",
    label: "Reports",
    href: "/report",
    icon: "reports",
    dropdownAlign: "right",
    routes: [
      { href: "/report", label: "Engineering Reports", desc: "Simulation and compliance report export" },
      { href: "/cae", label: "CAE Interop (Adams / MATLAB)", desc: "MSC Adams, MATLAB and CarMaker decks" },
      { href: "/engineering-memory", label: "Engineering Memory", desc: "Development timeline and signed decisions", aliases: ["/timeline"] },
      { href: "/vnv", label: "V&V Evidence", desc: "Solver validation and benchmarks" },
      { href: "/audit", label: "Audit & Governance", desc: "Tamper-evident ledger" },
    ],
  },
  {
    id: "ai-engineer",
    label: "AI Engineer",
    href: "/ai-engineer",
    icon: "ai",
    dropdownAlign: "right",
    routes: [
      { href: "/ai-engineer", label: "AI Race Engineer", desc: "Physics-grounded diagnosis and sign-off" },
    ],
  },
];

/** The navigation groups rendered by Navbar and MobileNav. */
export function getNavGroups(): StudioToolGroup[] {
  return NAV_V2;
}

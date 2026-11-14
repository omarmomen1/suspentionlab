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
  | "ai";

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

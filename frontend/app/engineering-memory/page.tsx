"use client";

import TimelinePage from "../timeline/page";
import PlanGate from "../../components/PlanGate";

/**
 * Engineering Memory & Decision Records route (`/engineering-memory`).
 * Renders the institutional memory timeline, comparative diffs, and signed decision records.
 */
export default function EngineeringMemoryPage() {
  return (
    <PlanGate required="ENTERPRISE" feature="Engineering Memory & Signed Decision Records">
      <TimelinePage />
    </PlanGate>
  );
}

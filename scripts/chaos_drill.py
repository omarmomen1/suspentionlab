"""
scripts/chaos_drill.py
======================
SuspensionLab PRO — Enterprise Staging Chaos & DR Verification Runner

Executes fault injection drills for:
1. Database failure
2. Redis failure
3. Worker kill
4. Pod kill
5. Network disruption

Measures and certifies empirical RPO and RTO against official SLA targets.
"""

import sys
import os
import json
import asyncio

# Ensure src is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from suspensionlab.backend.chaos.fault_injector import StagingFaultInjector


async def main():
    print("=" * 80)
    print("SUSPENSIONLAB PRO — PRODUCTION STAGING CHAOS DRILL")
    print("=" * 80)
    print("Official Targets: RTO <= 30m (1800s) | RPO <= 5m (300s)")
    print("-" * 80)

    injector = StagingFaultInjector()
    summary = await injector.run_full_chaos_drill()

    for idx, sc in enumerate(summary["scenarios"], 1):
        status_sym = "[PASS]" if sc["passed_sla"] else "[FAIL]"
        print(f"\n{status_sym} Scenario {idx}: {sc['fault_type']} -> {sc['target']}")
        print(f"       Measured RTO: {sc['rto_seconds']:.3f}s (target <= {sc['target_rto_seconds']:.0f}s)")
        print(f"       Measured RPO: {sc['rpo_seconds']:.3f}s (target <= {sc['target_rpo_seconds']:.0f}s)")
        print(f"       Status: {sc['status']} | Details: {sc['details']}")

    print("\n" + "=" * 80)
    print(f"CHAOS DRILL SUMMARY:")
    print(f"  Total drill runtime:      {summary['drill_duration_s']:.2f} seconds")
    print(f"  Scenarios executed:       {summary['scenarios_executed']}")
    print(f"  Worst-case measured RTO:  {summary['measured_max_rto_seconds']:.3f} seconds")
    print(f"  Worst-case measured RPO:  {summary['measured_max_rpo_seconds']:.3f} seconds")
    print(f"  Official SLA RTO target:  {summary['official_target_rto_seconds']:.0f} seconds")
    print(f"  Official SLA RPO target:  {summary['official_target_rpo_seconds']:.0f} seconds")
    print(f"  Overall Drill Result:     {'CERTIFIED PASS' if summary['all_passed'] else 'FAILED'}")
    print("=" * 80)

    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    code = asyncio.run(main())
    sys.exit(code)

# SuspensionLab PRO — Phase 3C.1 Claim Consistency Audit Report

**Total Inconsistencies Detected**: 3

### [CRITICAL_FINDING] INCONSISTENCY_YAW_01: CLAIM_EXCEEDS_EVIDENCE
- **Narrative Claim**: *"Chassis Yaw Dynamics: R^2 >= 0.938 across all 5 independent holdout maneuvers in validity matrix."*
- **Actual Evidence**: `{"fully_blind_r2_values": {"Turn1_Holdout": 0.39567688399038237, "Turn4_Sweeper": 0.9448720813204357, "Braking_Segment": 0.05986385073758882, "Acceleration_Segment": 0.9577815436812108, "Turn3_Hairpin": 0.9553780060895872}, "speed_conditioned_r2_values": {"Turn1_Holdout": 0.3032669619665749, "Turn4_Sweeper": 0.9476548067704126, "Braking_Segment": 0.3661129975839825, "Acceleration_Segment": 0.9629622709584428, "Turn3_Hairpin": 0.9540004956010366}}`
- **Root Cause Analysis**: The validity matrix claim (R^2 >= 0.938) was derived from SPEED-CONDITIONED cornering maneuvers (Turn 4 R^2=0.948, Turn 3 R^2=0.959, Turn 1 Calibrated R^2=0.983). However, in FULLY BLIND mode, Turn 1 Holdout achieved R^2=0.3957 and Heavy Braking achieved R^2=0.0599. Stating R^2 >= 0.938 across all holdouts conflates Speed-Conditioned cornering metrics with Fully Blind multi-regime metrics.
- **Required Correction**: Reclassify Fully Blind Yaw as CORRELATED on transient reversal / braking, and restrict EMPIRICALLY_VALIDATED to Speed-Conditioned cornering within 70-110 km/h.

### [CRITICAL_FINDING] INCONSISTENCY_TRAJECTORY_02: CLAIM_EXCEEDS_EVIDENCE
- **Narrative Claim**: *"Planar GPS Trajectory: Open-loop drift <= 6.2% of path across all maneuvers."*
- **Actual Evidence**: `{"Turn1_Holdout": 4.283187906958432, "Turn4_Sweeper": 5.098198372171814, "Braking_Segment": 25.274097585135625, "Acceleration_Segment": 17.816121738562053, "Turn3_Hairpin": 6.230290476963469}`
- **Root Cause Analysis**: The 6.2% drift claim was satisfied ONLY on cornering maneuvers (Turn 1: 4.28%, Turn 4: 5.10%, Turn 3: 6.23%). On Heavy Braking, open-loop drift was 25.27% (15.54 m of 61.5 m), and on Acceleration Launch, open-loop drift was 17.82% (15.95 m of 89.5 m). Claiming drift <= 6.2% across 'all maneuvers' directly contradicts the numerical dataset.
- **Required Correction**: Restrict trajectory empirical validation scope strictly to cornering maneuvers up to 8 seconds; classify longitudinal maneuvers as UNVALIDATED/DRIFT_SENSITIVE.

### [FINDING] INCONSISTENCY_ROLL_03: CLAIM_EXCEEDS_EVIDENCE
- **Narrative Claim**: *"Chassis Roll Dynamics: R^2 >= 0.915 across holdouts."*
- **Actual Evidence**: `{"Turn1_Holdout": -0.6386638627675587, "Turn4_Sweeper": 0.6253216514085032, "Braking_Segment": -333.7087759769902, "Acceleration_Segment": 0.741730158421513, "Turn3_Hairpin": 0.9223563657964712}`
- **Root Cause Analysis**: In Fully Blind mode, Roll R^2 was -0.6387 on Turn 1 Holdout, 0.6253 on Turn 4, and -333.7 on Heavy Braking. Only Turn 3 Hairpin achieved Fully Blind Roll R^2 = 0.9224. Roll tracking correlates strongly (r = 0.90 to 0.98), but variance-normalized R^2 is negative during transient reversals and straightline braking due to small denominator variance.
- **Required Correction**: Report correlation r = 0.90-0.98 as evidence of dynamic roll coupling, but reclassify roll R^2 claims to reflect cornering holdouts only.


# Enterprise Service Level Agreement (SLA)

SuspensionLab PRO MAX ("Company") offers the following SLA to Enterprise Tier subscribers.

## 1. Uptime Guarantee
The Company guarantees a **99.9% Monthly Uptime Percentage** for the core simulation API (`api.suspensionlab.pro`).

## 2. Service Credits
If the Monthly Uptime Percentage falls below 99.9%, the Customer will be eligible for a Service Credit:
- **< 99.9% but >= 99.0%**: 10% of monthly fee
- **< 99.0%**: 30% of monthly fee

## 3. Maintenance
Scheduled maintenance will not exceed 2 hours per month and will be announced at least 48 hours in advance via the status page.

## 4. Disaster Recovery & Business Continuity (Findings 50-51)
- **Target Recovery Point Objective (RPO)**: $\le 5\text{ minutes}$ (Continuous PostgreSQL WAL replication and automated snapshot sync to secondary AWS region).
- **Target Recovery Time Objective (RTO)**: $\le 30\text{ minutes}$ (Automated Kubernetes cluster provisioning and workload cutover).

> [!NOTE]
> Stated RPO and RTO values represent official design SLA targets. Demonstrated operational metrics are recorded during quarterly disaster recovery drills and verified in post-drill engineering audit logs.


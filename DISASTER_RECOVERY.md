# Disaster Recovery & Business Continuity Runbook
**SuspensionLab Platform | Enterprise Edition**

---

## 1. Objectives

This document defines the disaster recovery (DR) procedures for the SuspensionLab Platform to ensure business continuity in the event of a catastrophic failure (e.g., total AWS region loss, severe data corruption, or ransomware).

### 1.1 Official Enterprise DR Targets (Reconciled with SLA)
* **Recovery Point Objective (RPO):** $\le 5\text{ minutes}$ (Maximum acceptable data/transaction loss; backed by AWS RDS PostgreSQL continuous cross-region WAL stream and ElastiCache Global Datastore).
* **Recovery Time Objective (RTO):** $\le 30\text{ minutes}$ (Maximum acceptable downtime from disaster declaration to 100% active traffic serving in standby AWS region us-west-2).

---

## 2. Architecture: Active/Passive (Pilot Light)

SuspensionLab utilizes an **Active/Passive Multi-Region** architecture.
* **Primary Region:** `us-east-1` (Active, serving 100% of traffic)
* **Secondary Region:** `us-west-2` (Standby)

### 2.1 Replicated State
The following stateful resources are continuously replicated to the secondary region:
1. **PostgreSQL Database:** AWS RDS Cross-Region Read Replica.
2. **Redis Datastore:** ElastiCache Global Datastore.
3. **Container Images:** ECR cross-region replication.

### 2.2 Cold Compute
To save costs, the compute layer (EKS Cluster, ALB, WAF) in `us-west-2` is provisioned via Terraform but scaled to zero (or minimal replicas). During a disaster, these are scaled up.

---

## 3. Disaster Declaration

A disaster can be declared by the **Platform Lead** or **CTO** when:
* AWS Status Page confirms a multi-AZ outage in `us-east-1` lasting > 30 minutes.
* Critical infrastructure components in `us-east-1` are irrecoverably corrupted.

**Emergency Contact Bridge:** `slack://#incidents-critical`

---

## 4. Failover Procedure (us-east-1 -> us-west-2)

When a disaster is declared, execute the following steps to fail over traffic to the secondary region.

### Step 1: Promote RDS Read Replica
The `us-west-2` RDS instance is currently a read replica. It must be promoted to a standalone primary cluster.
```bash
aws rds promote-read-replica \
    --db-instance-identifier suspensionlab-db-prod-secondary \
    --region us-west-2
```
*Wait for the status to change from `modifying` to `available`.*

### Step 2: Promote ElastiCache Global Datastore
Failover the Redis Global Datastore to make `us-west-2` the primary.
```bash
aws elasticache failover-global-replication-group \
    --global-replication-group-id suspensionlab-global \
    --primary-region us-west-2 \
    --primary-replication-group-id suspensionlab-redis-prod-sec \
    --region us-west-2
```

### Step 3: Scale Up Secondary Compute
Deploy the application to the `us-west-2` EKS cluster using Helm. 
Update your kubeconfig to target the secondary cluster:
```bash
aws eks update-kubeconfig --name suspensionlab-prod-secondary --region us-west-2
```
Deploy the Helm chart, overriding the database endpoints to point to the newly promoted instances:
```bash
helm upgrade --install suspensionlab ./k8s/suspensionlab-chart \
  -n suspensionlab-prod \
  -f k8s/suspensionlab-chart/values-prod.yaml \
  --set api.replicaCount=3 \
  --set ui.replicaCount=3
```

### Step 4: Route53 DNS Failover
AWS Route53 is configured with a Failover Routing Policy.
If the `us-east-1` ALB fails health checks, Route53 will automatically route traffic to the `us-west-2` ALB. 
To force a manual failover immediately, disable the primary health check:
```bash
aws route53 update-health-check \
    --health-check-id <PRIMARY_HEALTH_CHECK_ID> \
    --disabled
```

---

## 5. Failback Procedure

Once `us-east-1` is restored and stable, the system must be failed back to its original state.
*Do NOT failback during peak business hours.*

1. **Re-establish Replication:** Create a new RDS read replica in `us-east-1` sourced from the `us-west-2` primary.
2. **Promote Primary:** Once replication lag is zero, stop all writes in `us-west-2`, promote the `us-east-1` replica to primary.
3. **Restore DNS:** Re-enable the primary Route53 health check to route traffic back to `us-east-1`.
4. **Scale Down Standby:** Scale down the `us-west-2` EKS workloads to return to Pilot Light mode.

---

## 6. Point-in-Time Recovery (Ransomware/Data Corruption)

If data is corrupted or encrypted by ransomware, we must restore from an automated backup (PITR).
* RDS maintains 7-14 days of automated backups.
* Redis maintains daily snapshots.

**Restore Command (RDS):**
```bash
aws rds restore-db-instance-to-point-in-time \
    --source-db-instance-identifier suspensionlab-db-prod \
    --target-db-instance-identifier suspensionlab-db-prod-restored \
    --restore-time "2026-07-12T10:00:00Z" \
    --region us-east-1
```
*Note: This creates a NEW database instance. You must update Terraform and Helm values to point to the new endpoint.*

---

## 7. Quarterly Disaster Drills & Measurable Certification (Finding 55)

To guarantee that disaster recovery is an operational capability rather than an unproven hypothesis:

### 7.1 Target Metrics
* **RTO (Recovery Time Objective):** $\le 30\text{ minutes}$ from disaster declaration to 100% traffic serving in Region B.
* **RPO (Recovery Point Objective):** $\le 5\text{ minutes}$ of transactional telemetry/simulation state loss.
* **Service Health Baseline:** Zero 5xx errors on core simulation routes after DNS migration.

### 7.2 Drill Execution Checklist
1. **Trigger Drill:** Initiate simulated failure of `us-east-1` in staging/canary environment.
2. **Promote Standby Database:** Measure seconds elapsed until read replica is promoted to primary (`db.is_available == true`).
3. **Failover Redis Global Datastore:** Measure latency for cluster state synchronization.
4. **Deploy Compute & Scale Workers:** Scale `us-west-2` worker deployment to target replica counts via KEDA.
5. **Execute Automated Verification Suite:**
   ```bash
   python -m pytest tests/test_integration_e2e.py -v
   python -m pytest tests/test_webhook_enterprise_e2e.py -v
   ```
6. **Log Drill Metrics:** Record drill duration, RTO, RPO, and any manual interventions in the enterprise compliance audit log.


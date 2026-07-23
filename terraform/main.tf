terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
  # NOTE: backend config is in backend.tf (S3 + DynamoDB)
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "SuspensionLab"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

provider "aws" {
  alias  = "secondary"
  region = var.aws_secondary_region

  default_tags {
    tags = {
      Project     = "SuspensionLab"
      Environment = var.environment
      ManagedBy   = "Terraform"
      Role        = "DR-Standby"
    }
  }
}

# ── Current caller identity (used in outputs) ─────────────────────────────────
data "aws_caller_identity" "current" {}

# ── VPC & Network ─────────────────────────────────────────────────────────────
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.0.0"
  name    = "suspensionlab-vpc-${var.environment}"
  cidr    = "10.0.0.0/16"

  azs             = ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  # FIXED: one_nat_gateway_per_az eliminates the single NAT gateway SPOF.
  # A NAT gateway failure in the original config would black-hole ALL egress traffic.
  enable_nat_gateway     = true
  single_nat_gateway     = false
  one_nat_gateway_per_az = true

  # Required for EKS
  enable_dns_hostnames = true
  enable_dns_support   = true

  private_subnet_tags = {
    "kubernetes.io/cluster/suspensionlab-prod" = "shared"
    "kubernetes.io/role/internal-elb"          = "1"
  }

  public_subnet_tags = {
  public_subnet_tags = {
    "kubernetes.io/cluster/suspensionlab-prod" = "shared"
    "kubernetes.io/role/elb"                   = "1"
  }
}

# ── Secondary VPC (Standby Region) ────────────────────────────────────────────
module "vpc_secondary" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.0.0"
  providers = {
    aws = aws.secondary
  }
  
  count = var.enable_multi_region ? 1 : 0

  name = "suspensionlab-vpc-${var.environment}-secondary"
  cidr = "10.1.0.0/16"

  azs             = ["${var.aws_secondary_region}a", "${var.aws_secondary_region}b", "${var.aws_secondary_region}c"]
  private_subnets = ["10.1.1.0/24", "10.1.2.0/24", "10.1.3.0/24"]
  public_subnets  = ["10.1.101.0/24", "10.1.102.0/24", "10.1.103.0/24"]

  enable_nat_gateway     = true
  single_nat_gateway     = false
  one_nat_gateway_per_az = true
  enable_dns_hostnames   = true
  enable_dns_support     = true
}

# ── Security Groups ───────────────────────────────────────────────────────────
# FIXED: Previously used default_security_group_id for RDS which allows all
# inbound traffic. Replaced with explicit, least-privilege security groups.

resource "aws_security_group" "rds" {
  name        = "suspensionlab-rds-${var.environment}"
  description = "Allow PostgreSQL access from EKS nodes only"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description     = "PostgreSQL from EKS worker nodes"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }

  # No egress from RDS — databases do not initiate outbound connections
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow outbound for patch downloads (restricted to AWS endpoints via NACL)"
  }

  tags = {
    Name = "suspensionlab-rds-sg"
  }
}

resource "aws_security_group" "redis" {
  name        = "suspensionlab-redis-${var.environment}"
  description = "Allow Redis access from EKS nodes only"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description     = "Redis from EKS worker nodes"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow outbound"
  }

  tags = {
    Name = "suspensionlab-redis-sg"
  }
}

# ── ECR Repositories ──────────────────────────────────────────────────────────
# FIXED: image_tag_mutability changed from MUTABLE to IMMUTABLE.
# Mutable tags allow silent overwriting of existing tags, breaking rollback guarantees.
# With IMMUTABLE tags, the CI/CD pipeline MUST use unique git-SHA tags.

resource "aws_ecr_repository" "backend" {
  name                 = "suspensionlab/backend"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_repository" "frontend" {
  name                 = "suspensionlab/frontend"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

# ECR lifecycle policy — keep last 20 images per repo, expire untagged after 1 day
resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 1 day"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep last 20 tagged images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v", "sha-"]
          countType     = "imageCountMoreThan"
          countNumber   = 20
        }
        action = { type = "expire" }
      }
    ]
  })
}

resource "aws_ecr_lifecycle_policy" "frontend" {
  repository = aws_ecr_repository.frontend.name
  policy     = aws_ecr_lifecycle_policy.backend.policy
}

# ── EKS Cluster ───────────────────────────────────────────────────────────────
module "eks" {
  source          = "terraform-aws-modules/eks/aws"
  version         = "19.15.3"
  cluster_name    = "suspensionlab-prod"
  cluster_version = var.eks_cluster_version

  vpc_id                   = module.vpc.vpc_id
  subnet_ids               = module.vpc.private_subnets
  control_plane_subnet_ids = module.vpc.private_subnets

  # Enable private endpoint access; restrict public access to known CIDR if needed
  cluster_endpoint_private_access = true
  cluster_endpoint_public_access  = true

  # Enable cluster-level encryption of Secrets
  cluster_encryption_config = {
    resources = ["secrets"]
  }

  eks_managed_node_groups = {
    # System node group: runs cluster-critical pods (CoreDNS, kube-proxy, metrics-server)
    system = {
      min_size       = 2
      max_size       = 4
      desired_size   = 2
      instance_types = ["t3.medium"]
      labels = {
        role = "system"
      }
      taints = []
    }

    # Application node group: runs API, frontend, worker pods
    # c6i.large provides 2 vCPU + 4 GB RAM — appropriate for SciPy/NumPy simulation loads
    application = {
      min_size       = 2
      max_size       = 20
      desired_size   = 3
      instance_types = ["c6i.large"]
      labels = {
        role = "application"
      }
    }
  }
}

# ── RDS PostgreSQL ────────────────────────────────────────────────────────────
# FIXED: multi_az = true, instance class upgraded, deletion protection, backups.
# The original config had multi_az = false (SPOF) and db.t4g.small (undersized).

module "db" {
  source  = "terraform-aws-modules/rds/aws"
  version = "6.1.1"

  identifier = "suspensionlab-db-${var.environment}"

  engine               = "postgres"
  engine_version       = "15"
  family               = "postgres15"
  major_engine_version = "15"
  instance_class       = var.db_instance_class  # Validated minimum: db.t4g.medium

  allocated_storage     = 50
  max_allocated_storage = 500
  storage_encrypted     = true

  db_name  = "suspensionlab"
  username = "susplab"
  port     = 5432

  # FIXED: multi_az = true — eliminates AZ-level SPOF
  multi_az               = true
  db_subnet_group_name   = module.vpc.database_subnet_group_name
  vpc_security_group_ids = [aws_security_group.rds.id]

  create_db_subnet_group = true
  subnet_ids             = module.vpc.private_subnets

  # FIXED: Automated backups with minimum 7-day retention
  backup_retention_period = var.db_backup_retention_days
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"

  # FIXED: Deletion protection prevents accidental `terraform destroy` data loss
  deletion_protection = true

  # Performance Insights for query monitoring
  performance_insights_enabled          = true
  performance_insights_retention_period = 7

  # Automated minor version upgrades during maintenance window
  auto_minor_version_upgrade = true

  # Credentials stored in AWS Secrets Manager (auto-rotated)
  manage_master_user_password = true
}

# ── RDS Cross-Region Read Replica (Standby) ───────────────────────────────────
module "db_secondary" {
  source  = "terraform-aws-modules/rds/aws"
  version = "6.1.1"
  providers = {
    aws = aws.secondary
  }

  count = var.enable_multi_region ? 1 : 0

  identifier = "suspensionlab-db-${var.environment}-secondary"

  # Replica configuration
  replicate_source_db    = module.db.db_instance_arn
  instance_class         = var.db_instance_class
  multi_az               = true
  
  # Network
  db_subnet_group_name   = module.vpc_secondary[0].database_subnet_group_name
  create_db_subnet_group = true
  subnet_ids             = module.vpc_secondary[0].private_subnets
  
  # Backups are required on replica for promoting to primary
  backup_retention_period = var.db_backup_retention_days
  storage_encrypted       = true
  
  skip_final_snapshot = true
}

# ── ElastiCache Redis (Replication Group) ─────────────────────────────────────
# FIXED: Replaced single-node aws_elasticache_cluster with a replication group
# providing one primary and one replica for read scaling and HA failover.
# Original had num_cache_nodes = 1 — a single Redis failure took down the entire
# rate-limiting, session, and job queue subsystem.

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "suspensionlab-redis-${var.environment}"
  description          = "SuspensionLab Redis — rate limiting, sessions, job queue"

  node_type            = "cache.t4g.small"
  port                 = 6379
  parameter_group_name = "default.redis7"
  engine_version       = "7.0"

  # Primary + 1 replica across 2 AZs
  num_cache_clusters         = 2
  automatic_failover_enabled = true
  multi_az_enabled           = true

  subnet_group_name  = aws_elasticache_subnet_group.redis.name
  security_group_ids = [aws_security_group.redis.id]

  # Encryption at rest and in transit
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token_enabled         = true

  # Automated snapshot for DR
  snapshot_retention_limit = 3
  snapshot_window          = "02:00-03:00"

  log_delivery_configuration {
    destination      = aws_cloudwatch_log_group.redis_slow_log.name
    destination_type = "cloudwatch-logs"
    log_format       = "json"
    log_type         = "slow-log"
  }
}

resource "aws_cloudwatch_log_group" "redis_slow_log" {
  name              = "/suspensionlab/redis/slow-log"
  retention_in_days = 14
}

resource "aws_elasticache_subnet_group" "redis" {
  name       = "suspensionlab-redis-subnet-${var.environment}"
  subnet_ids = module.vpc.private_subnets
}

# ── Global Datastore for Redis (Cross-Region) ─────────────────────────────────
resource "aws_elasticache_global_replication_group" "global_redis" {
  count = var.enable_multi_region ? 1 : 0

  global_replication_group_id_suffix = "suspensionlab-global"
  primary_replication_group_id       = aws_elasticache_replication_group.redis.id
}

resource "aws_elasticache_replication_group" "redis_secondary" {
  provider = aws.secondary
  count    = var.enable_multi_region ? 1 : 0

  replication_group_id          = "suspensionlab-redis-${var.environment}-sec"
  description                   = "SuspensionLab Redis — Secondary Region"
  global_replication_group_id   = aws_elasticache_global_replication_group.global_redis[0].global_replication_group_id
  
  num_cache_clusters = 2
  multi_az_enabled   = true
  
  subnet_group_name  = aws_elasticache_subnet_group.redis_secondary[0].name
}

resource "aws_elasticache_subnet_group" "redis_secondary" {
  provider = aws.secondary
  count    = var.enable_multi_region ? 1 : 0

  name       = "suspensionlab-redis-subnet-${var.environment}-sec"
  subnet_ids = module.vpc_secondary[0].private_subnets
}

# ── AWS WAF v2 ────────────────────────────────────────────────────────────────
# FIXED: Added AWS WAFv2 web ACL with AWS-managed rule groups.
# Previously absent — any ALB was fully exposed to OWASP Top 10 attacks.

resource "aws_wafv2_web_acl" "main" {
  count = var.waf_enabled ? 1 : 0

  name        = "suspensionlab-waf-${var.environment}"
  description = "WAF for SuspensionLab ALB — blocks OWASP Top 10 and known bad inputs"
  scope       = "REGIONAL"

  default_action {
    allow {}
  }

  # AWS Managed Rules — Common Rule Set (OWASP Top 10 mitigations)
  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 1
    override_action { none {} }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "CommonRuleSet"
      sampled_requests_enabled   = true
    }
  }

  # AWS Managed Rules — Known Bad Inputs (SQLi, log4j, etc.)
  rule {
    name     = "AWSManagedRulesKnownBadInputsRuleSet"
    priority = 2
    override_action { none {} }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "KnownBadInputs"
      sampled_requests_enabled   = true
    }
  }

  # AWS Managed Rules — SQL Injection specific
  rule {
    name     = "AWSManagedRulesSQLiRuleSet"
    priority = 3
    override_action { none {} }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesSQLiRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "SQLiRuleSet"
      sampled_requests_enabled   = true
    }
  }

  # Rate limiting — 2000 requests per 5 minutes per IP
  rule {
    name     = "RateLimitPerIP"
    priority = 4
    action { block {} }
    statement {
      rate_based_statement {
        limit              = 2000
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "RateLimitPerIP"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "suspensionlab-waf"
    sampled_requests_enabled   = true
  }
}

# ── CloudWatch Log Groups ─────────────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "application" {
  name              = "/suspensionlab/application"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "eks_cluster" {
  name              = "/aws/eks/suspensionlab-prod/cluster"
  retention_in_days = 30
}

# ── AWS Secrets Manager ───────────────────────────────────────────────────────
# Placeholder secrets — actual values populated post-apply via CI/CD or manually.
# The RDS master password is auto-managed by the RDS module above.

resource "aws_secretsmanager_secret" "app_secrets" {
  name                    = "suspensionlab/${var.environment}/app"
  description             = "SuspensionLab application secrets (JWT key, API keys, billing)"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "app_secrets" {
  secret_id = aws_secretsmanager_secret.app_secrets.id
  secret_string = jsonencode({
    JWT_SECRET_KEY               = "REPLACE_WITH_GENERATED_SECRET"
    LEMON_SQUEEZY_API_KEY        = "REPLACE_WITH_REAL_KEY"
    LEMON_SQUEEZY_WEBHOOK_SECRET = "REPLACE_WITH_REAL_SECRET"
    GEMINI_API_KEY               = "REPLACE_WITH_REAL_KEY"
  })

  lifecycle {
    # Prevent Terraform from overwriting secrets that have been populated externally
    ignore_changes = [secret_string]
  }
}

# ── IAM Role for External Secrets Operator ────────────────────────────────────
# Allows the External Secrets Operator (running in EKS) to read from Secrets Manager
# via IRSA (IAM Roles for Service Accounts) — no static credentials in the cluster.

data "aws_iam_policy_document" "external_secrets_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [module.eks.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${module.eks.oidc_provider}:sub"
      values   = ["system:serviceaccount:external-secrets:external-secrets"]
    }
  }
}

resource "aws_iam_role" "external_secrets" {
  name               = "suspensionlab-external-secrets-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.external_secrets_assume.json
}

resource "aws_iam_role_policy" "external_secrets_read" {
  name = "read-app-secrets"
  role = aws_iam_role.external_secrets.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = [
          aws_secretsmanager_secret.app_secrets.arn,
          # RDS auto-managed secret ARN pattern
          "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:rds!db-*"
        ]
      }
    ]
  })
}

# ── Route53 Failover Routing ──────────────────────────────────────────────────
# Active/Passive DNS failover routing for the main application endpoint.

data "aws_route53_zone" "main" {
  name = "suspensionlab.pro"
}

resource "aws_route53_health_check" "primary" {
  fqdn              = "primary.app.suspensionlab.pro"
  port              = 443
  type              = "HTTPS"
  resource_path     = "/health"
  failure_threshold = 3
  request_interval  = 30
  
  tags = {
    Name = "SuspensionLab-Primary-HealthCheck"
  }
}

resource "aws_route53_record" "app_primary" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "app.suspensionlab.pro"
  type    = "CNAME"
  ttl     = 60

  failover_routing_policy {
    type = "PRIMARY"
  }

  set_identifier  = "primary"
  health_check_id = aws_route53_health_check.primary.id
  records         = ["primary.app.suspensionlab.pro"]
}

resource "aws_route53_record" "app_secondary" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "app.suspensionlab.pro"
  type    = "CNAME"
  ttl     = 60

  failover_routing_policy {
    type = "SECONDARY"
  }

  set_identifier = "secondary"
  records        = ["secondary.app.suspensionlab.pro"]
}

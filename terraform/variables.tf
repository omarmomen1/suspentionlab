variable "aws_region" {
  description = "Primary AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "aws_secondary_region" {
  description = "Secondary AWS region for disaster recovery (Active/Passive)"
  type        = string
  default     = "us-west-2"
}

variable "enable_multi_region" {
  description = "Enable cross-region replication and secondary resources"
  type        = bool
  default     = true
}

variable "environment" {
  description = "Deployment environment name (prod, staging, dev)."
  type        = string
  default     = "prod"
  validation {
    condition     = contains(["prod", "staging", "dev"], var.environment)
    error_message = "Environment must be one of: prod, staging, dev."
  }
}

variable "db_instance_class" {
  description = "RDS instance class. Minimum db.t4g.medium for production simulation workloads."
  type        = string
  default     = "db.t4g.medium"
  validation {
    condition     = !contains(["db.t4g.micro", "db.t4g.small", "db.t2.micro", "db.t3.micro"], var.db_instance_class)
    error_message = "db.t4g.micro, db.t4g.small, db.t2.micro, and db.t3.micro are prohibited in this configuration — they are insufficient for SciPy/NumPy simulation workloads."
  }
}

variable "db_backup_retention_days" {
  description = "Number of days to retain RDS automated backups. Minimum 7 for production."
  type        = number
  default     = 7
  validation {
    condition     = var.db_backup_retention_days >= 7
    error_message = "Backup retention must be at least 7 days for production environments."
  }
}

variable "eks_cluster_version" {
  description = "Kubernetes version for the EKS cluster."
  type        = string
  default     = "1.29"
}

variable "eks_cluster_endpoint_public_access" {
  description = "Whether the Amazon EKS public API server endpoint is enabled."
  type        = bool
  default     = true
}

variable "eks_public_access_cidrs" {
  description = "List of CIDR blocks that can access the Amazon EKS public API server endpoint. Must not be open to 0.0.0.0/0 in production."
  type        = list(string)
  default     = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
  validation {
    condition     = var.environment != "prod" || !contains(var.eks_public_access_cidrs, "0.0.0.0/0")
    error_message = "Public control-plane access cannot be open to 0.0.0.0/0 in production. Restrict CIDRs to trusted corporate or bastion networks."
  }
}

variable "waf_enabled" {
  description = "Whether to provision and attach AWS WAFv2 to the application load balancer."
  type        = bool
  default     = true
}

variable "app_secrets" {
  description = "Map of application secrets. Rejects placeholder strings in production."
  type        = map(string)
  default     = {}
  sensitive   = true
  validation {
    condition = var.environment != "prod" || alltrue([
      for k, v in var.app_secrets : !can(regex("(?i)(REPLACE_WITH_|changeme|default|example)", v))
    ])
    error_message = "Production secrets must not contain placeholder values (REPLACE_WITH_, changeme, default, example)."
  }
}

variable "s3_artifacts_bucket_prefix" {
  description = "Prefix for the S3 simulation artifacts and telemetry storage buckets."
  type        = string
  default     = "suspensionlab-artifacts"
}

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

variable "waf_enabled" {
  description = "Whether to provision and attach AWS WAFv2 to the application load balancer."
  type        = bool
  default     = true
}

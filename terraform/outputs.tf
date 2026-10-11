# ── Infrastructure Outputs ────────────────────────────────────────────────────
# These outputs are consumed by the CI/CD pipeline (GitHub Actions) and the
# Helm deployment step to avoid hardcoding values.

output "aws_account_id" {
  description = "AWS Account ID — used to construct ECR repository URLs in CI/CD."
  value       = data.aws_caller_identity.current.account_id
}

output "eks_cluster_name" {
  description = "EKS cluster name — used by CI/CD for kubectl/helm deployment context."
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "EKS cluster API server endpoint."
  value       = module.eks.cluster_endpoint
  sensitive   = true
}

output "ecr_backend_url" {
  description = "Full ECR URL for the backend image — used in Helm --set flags by CI/CD."
  value       = aws_ecr_repository.backend.repository_url
}

output "ecr_frontend_url" {
  description = "Full ECR URL for the frontend image."
  value       = aws_ecr_repository.frontend.repository_url
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint — used to populate AWS Secrets Manager."
  value       = module.db.db_instance_endpoint
  sensitive   = true
}

output "redis_primary_endpoint" {
  description = "ElastiCache Redis primary endpoint."
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
  sensitive   = true
}

output "waf_web_acl_arn" {
  description = "WAFv2 Web ACL ARN — attached to the ALB by the EKS ingress controller annotation."
  value       = var.waf_enabled ? aws_wafv2_web_acl.main[0].arn : null
}

output "eks_secondary_cluster_name" {
  description = "Secondary Standby EKS cluster name for DR failover."
  value       = var.enable_multi_region ? module.eks_secondary[0].cluster_name : null
}

output "rds_secondary_endpoint" {
  description = "RDS PostgreSQL secondary replica endpoint for DR failover."
  value       = var.enable_multi_region ? module.db_secondary[0].db_instance_endpoint : null
  sensitive   = true
}

output "redis_secondary_endpoint" {
  description = "ElastiCache Redis secondary endpoint for DR failover."
  value       = var.enable_multi_region ? aws_elasticache_replication_group.redis_secondary[0].primary_endpoint_address : null
  sensitive   = true
}

output "s3_artifacts_bucket_arn" {
  description = "Primary S3 artifacts bucket ARN."
  value       = aws_s3_bucket.artifacts.arn
}

output "s3_artifacts_secondary_bucket_arn" {
  description = "Secondary DR S3 artifacts bucket ARN."
  value       = var.enable_multi_region ? aws_s3_bucket.artifacts_secondary[0].arn : null
}

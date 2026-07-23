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

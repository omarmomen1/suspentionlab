terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# --- VPC & Network ---
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.0.0"
  name    = "suspensionlab-vpc"
  cidr    = "10.0.0.0/16"

  azs             = ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = true
}

# --- ECR ---
resource "aws_ecr_repository" "backend" {
  name                 = "suspensionlab/backend"
  image_tag_mutability = "MUTABLE"
}

resource "aws_ecr_repository" "frontend" {
  name                 = "suspensionlab/frontend"
  image_tag_mutability = "MUTABLE"
}

# --- EKS Cluster ---
module "eks" {
  source          = "terraform-aws-modules/eks/aws"
  version         = "19.15.3"
  cluster_name    = "suspensionlab-prod"
  cluster_version = "1.28"

  vpc_id                   = module.vpc.vpc_id
  subnet_ids               = module.vpc.private_subnets
  control_plane_subnet_ids = module.vpc.public_subnets

  eks_managed_node_groups = {
    default = {
      min_size       = 2
      max_size       = 5
      desired_size   = 2
      instance_types = ["t3.medium"]
    }
    workers = {
      min_size       = 1
      max_size       = 10
      desired_size   = 2
      instance_types = ["c6i.large"]
    }
  }
}

# --- RDS PostgreSQL ---
module "db" {
  source  = "terraform-aws-modules/rds/aws"
  version = "6.1.1"

  identifier = "suspensionlab-db"

  engine               = "postgres"
  engine_version       = "15"
  family               = "postgres15"
  major_engine_version = "15"
  instance_class       = "db.t4g.small"

  allocated_storage     = 20
  max_allocated_storage = 100

  db_name  = "suspensionlab"
  username = "postgres"
  port     = 5432

  multi_az               = false
  db_subnet_group_name   = module.vpc.database_subnet_group_name
  vpc_security_group_ids = [module.vpc.default_security_group_id]

  create_db_subnet_group = true
  subnet_ids             = module.vpc.private_subnets
}

# --- ElastiCache Redis ---
resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "suspensionlab-redis"
  engine               = "redis"
  node_type            = "cache.t4g.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  engine_version       = "7.0"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.redis_subnet_group.name
}

resource "aws_elasticache_subnet_group" "redis_subnet_group" {
  name       = "suspensionlab-redis-subnet"
  subnet_ids = module.vpc.private_subnets
}

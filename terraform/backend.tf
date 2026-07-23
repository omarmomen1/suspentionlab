terraform {
  # ── Remote State Backend ───────────────────────────────────────────────────
  # State is stored in S3 with DynamoDB-based distributed locking.
  # This prevents concurrent `terraform apply` runs from corrupting state.
  #
  # Bootstrap (one-time, before first apply):
  #   aws s3api create-bucket --bucket suspensionlab-terraform-state \
  #     --region us-east-1 --create-bucket-configuration \
  #     LocationConstraint=us-east-1
  #   aws s3api put-bucket-versioning --bucket suspensionlab-terraform-state \
  #     --versioning-configuration Status=Enabled
  #   aws s3api put-bucket-encryption --bucket suspensionlab-terraform-state \
  #     --server-side-encryption-configuration \
  #     '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
  #   aws dynamodb create-table --table-name suspensionlab-tf-lock \
  #     --attribute-definitions AttributeName=LockID,AttributeType=S \
  #     --key-schema AttributeName=LockID,KeyType=HASH \
  #     --billing-mode PAY_PER_REQUEST --region us-east-1
  backend "s3" {
    bucket         = "suspensionlab-terraform-state"
    key            = "prod/suspensionlab.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "suspensionlab-tf-lock"
  }
}

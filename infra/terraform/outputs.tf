output "vpc_id" {
  description = "VPC of the private subnets."
  value       = aws_vpc.main.id
}

output "db_cluster_endpoint" {
  description = "Aurora writer endpoint."
  value       = aws_rds_cluster.main.endpoint
}

output "db_cluster_arn" {
  description = "Aurora cluster ARN (used with the RDS Data API for bootstrap)."
  value       = aws_rds_cluster.main.arn
}

output "db_master_secret_arn" {
  description = "Secrets Manager secret with the master credentials (managed by RDS)."
  value       = aws_rds_cluster.main.master_user_secret[0].secret_arn
}

output "raw_bucket" {
  description = "Raw data lake bucket (landing/ and rejected/)."
  value       = aws_s3_bucket.raw.bucket
}

output "loader_queue_url" {
  description = "SQS queue fed by S3 notifications."
  value       = aws_sqs_queue.loader.url
}

output "loader_dlq_url" {
  description = "Dead-letter queue of the loader."
  value       = aws_sqs_queue.loader_dlq.url
}

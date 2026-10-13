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

output "api_url" {
  description = "Base URL of the HTTP API."
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "ecr_repository_url" {
  description = "ECR repository for the application image."
  value       = aws_ecr_repository.api.repository_url
}

output "cognito_user_pool_id" {
  description = "Cognito user pool issuing the API tokens."
  value       = aws_cognito_user_pool.main.id
}

output "cognito_client_id" {
  description = "App client used to obtain tokens (audience of the JWT authorizer)."
  value       = aws_cognito_user_pool_client.api.id
}

output "api_function_name" {
  description = "API Lambda function."
  value       = aws_lambda_function.api.function_name
}

output "loader_function_name" {
  description = "Loader Lambda function (also invoked with {\"action\": \"migrate\"})."
  value       = aws_lambda_function.loader.function_name
}

output "alarms_topic_arn" {
  description = "SNS topic receiving the CloudWatch alarms."
  value       = aws_sns_topic.alarms.arn
}

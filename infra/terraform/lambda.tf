# Two functions from the same image (ADR-009):
# - api: HTTP requests from API Gateway, served by FastAPI through the Lambda Web Adapter.
# - loader: SQS batches and migration invocations, forwarded to POST /internal/events.

locals {
  image_uri = "${aws_ecr_repository.api.repository_url}:${var.image_tag}"

  # AWS_REGION is set by Lambda itself (reserved variable) and read by the application.
  lambda_environment = {
    APP_ENV      = var.environment
    LOG_LEVEL    = "INFO"
    DB_HOST      = aws_rds_cluster.main.endpoint
    DB_PORT      = "5432"
    DB_NAME      = var.db_name
    DB_USER      = var.db_iam_user
    DB_IAM_AUTH  = "true"
    DB_POOL_SIZE = "1" # one request at a time per Lambda instance
    RAW_BUCKET   = aws_s3_bucket.raw.bucket
  }
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.name}-api"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "loader" {
  name              = "/aws/lambda/${local.name}-loader"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "api" {
  function_name = "${local.name}-api"
  description   = "FastAPI REST API (CSV migration, batch inserts, metrics)"
  role          = aws_iam_role.api.arn
  package_type  = "Image"
  image_uri     = local.image_uri
  architectures = ["arm64"]
  memory_size   = var.api_memory_mb
  timeout       = 29 # API Gateway HTTP API integrations time out at 30 seconds

  reserved_concurrent_executions = var.api_reserved_concurrency

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = local.lambda_environment
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.api.name
  }

  depends_on = [aws_iam_role_policy_attachment.api_vpc, aws_ecr_repository_policy.api]
}

resource "aws_lambda_function" "loader" {
  function_name = "${local.name}-loader"
  description   = "Event-driven CSV loader (S3 -> SQS) and database migrations"
  role          = aws_iam_role.loader.arn
  package_type  = "Image"
  image_uri     = local.image_uri
  architectures = ["arm64"]
  memory_size   = var.loader_memory_mb
  timeout       = var.loader_timeout_seconds

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = merge(local.lambda_environment, {
      ENABLE_EVENT_HANDLERS     = "true"
      AWS_LWA_PASS_THROUGH_PATH = "/internal/events"
    })
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.loader.name
  }

  depends_on = [aws_iam_role_policy_attachment.loader_vpc, aws_ecr_repository_policy.api]
}

resource "aws_lambda_event_source_mapping" "loader" {
  event_source_arn        = aws_sqs_queue.loader.arn
  function_name           = aws_lambda_function.loader.arn
  batch_size              = 1
  function_response_types = ["ReportBatchItemFailures"]

  scaling_config {
    maximum_concurrency = var.loader_max_concurrency
  }
}

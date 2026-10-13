# Plan-time tests of the architecture decisions. The AWS provider is mocked, so these tests run
# without an AWS account or credentials: `make tf-test`.

mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
    }
  }

  mock_data "aws_availability_zones" {
    defaults = {
      names = ["us-east-1a", "us-east-1b", "us-east-1c"]
    }
  }

  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
}

variables {
  image_tag = "abc1234"
}

run "network_is_private_and_multi_az" {
  command = plan

  assert {
    condition     = length(aws_subnet.private) == 2
    error_message = "Expected two private subnets."
  }

  assert {
    condition     = length(distinct([for s in aws_subnet.private : s.availability_zone])) == 2
    error_message = "Private subnets must be in different availability zones."
  }

  assert {
    condition     = alltrue([for s in aws_subnet.private : s.map_public_ip_on_launch != true])
    error_message = "Subnets must not assign public IPs."
  }

  assert {
    condition     = aws_vpc_endpoint.s3.vpc_endpoint_type == "Gateway"
    error_message = "S3 must be reached through the free gateway endpoint."
  }

  assert {
    condition = (
      aws_vpc_security_group_ingress_rule.database_from_lambda.from_port == 5432 &&
      aws_vpc_security_group_ingress_rule.database_from_lambda.to_port == 5432 &&
      aws_vpc_security_group_ingress_rule.database_from_lambda.cidr_ipv4 == null
    )
    error_message = "Aurora must only accept PostgreSQL from the Lambda security group, never a CIDR."
  }
}

run "database_dev_defaults_scale_to_zero" {
  command = plan

  assert {
    condition     = aws_rds_cluster.main.iam_database_authentication_enabled
    error_message = "IAM database authentication must be enabled."
  }

  assert {
    condition     = aws_rds_cluster.main.storage_encrypted && aws_rds_cluster.main.manage_master_user_password
    error_message = "Storage must be encrypted and the master password managed by RDS."
  }

  assert {
    condition = (
      aws_rds_cluster.main.serverlessv2_scaling_configuration[0].min_capacity == 0 &&
      aws_rds_cluster.main.serverlessv2_scaling_configuration[0].seconds_until_auto_pause == 900
    )
    error_message = "Dev defaults must scale to 0 ACU and pause after 15 idle minutes."
  }

  assert {
    condition     = aws_rds_cluster.main.skip_final_snapshot && !aws_rds_cluster.main.deletion_protection
    error_message = "Dev defaults must be disposable."
  }

  assert {
    condition     = length(aws_rds_cluster_instance.main) == 1
    error_message = "Dev defaults use a single serverless instance."
  }
}

run "database_production_settings" {
  command = plan

  variables {
    db_min_capacity     = 0.5
    db_instance_count   = 2
    deletion_protection = true
  }

  assert {
    condition     = aws_rds_cluster.main.serverlessv2_scaling_configuration[0].min_capacity == 0.5
    error_message = "Production settings keep a warm minimum capacity (no auto-pause, no resume latency)."
  }

  assert {
    condition = (
      aws_rds_cluster.main.deletion_protection &&
      !aws_rds_cluster.main.skip_final_snapshot &&
      aws_rds_cluster.main.final_snapshot_identifier == "globant-challenge-dev-final"
    )
    error_message = "Production settings must protect the database and keep a final snapshot."
  }

  assert {
    condition     = length(aws_rds_cluster_instance.main) == 2
    error_message = "Production settings add a second instance for failover."
  }

  assert {
    condition     = aws_cognito_user_pool.main.deletion_protection == "ACTIVE"
    error_message = "Deletion protection must also cover the user pool."
  }
}

run "raw_bucket_is_locked_down" {
  command = plan

  assert {
    condition = (
      aws_s3_bucket_public_access_block.raw.block_public_acls &&
      aws_s3_bucket_public_access_block.raw.block_public_policy &&
      aws_s3_bucket_public_access_block.raw.ignore_public_acls &&
      aws_s3_bucket_public_access_block.raw.restrict_public_buckets
    )
    error_message = "All public access must be blocked."
  }

  assert {
    condition     = aws_s3_bucket.raw.bucket == "globant-challenge-dev-raw-123456789012"
    error_message = "The bucket name must be unique per account."
  }

  assert {
    condition = (
      aws_s3_bucket_notification.raw.queue[0].filter_prefix == "landing/" &&
      aws_s3_bucket_notification.raw.queue[0].filter_suffix == ".csv"
    )
    error_message = "Only CSV files in landing/ must trigger the loader."
  }
}

run "loader_queue_and_event_source" {
  command = plan

  assert {
    condition     = aws_sqs_queue.loader.visibility_timeout_seconds == 6 * var.loader_timeout_seconds
    error_message = "The visibility timeout must be 6x the loader timeout."
  }

  assert {
    condition = (
      aws_lambda_event_source_mapping.loader.batch_size == 1 &&
      aws_lambda_event_source_mapping.loader.scaling_config[0].maximum_concurrency == 5 &&
      contains(aws_lambda_event_source_mapping.loader.function_response_types, "ReportBatchItemFailures")
    )
    error_message = "The loader must use partial batch responses and capped concurrency."
  }
}

run "lambdas_share_one_arm64_image" {
  command = plan

  assert {
    condition     = aws_lambda_function.api.architectures == tolist(["arm64"]) && aws_lambda_function.loader.architectures == tolist(["arm64"])
    error_message = "Both Lambdas must run on arm64 (Graviton)."
  }

  assert {
    condition     = aws_lambda_function.api.package_type == "Image" && aws_lambda_function.loader.package_type == "Image"
    error_message = "Both Lambdas must run the container image."
  }

  assert {
    condition = (
      aws_lambda_function.loader.environment[0].variables["ENABLE_EVENT_HANDLERS"] == "true" &&
      !contains(keys(aws_lambda_function.api.environment[0].variables), "ENABLE_EVENT_HANDLERS")
    )
    error_message = "Only the loader may expose the internal events route."
  }

  assert {
    condition = alltrue([
      for fn in [aws_lambda_function.api, aws_lambda_function.loader] :
      fn.environment[0].variables["DB_IAM_AUTH"] == "true" && fn.environment[0].variables["DB_POOL_SIZE"] == "1"
    ])
    error_message = "Lambdas must use IAM database auth and a single pooled connection."
  }

  assert {
    condition     = aws_lambda_function.api.timeout < 30
    error_message = "The API timeout must stay below the 30 s API Gateway limit."
  }
}

run "only_health_and_docs_are_public" {
  command = plan

  assert {
    condition     = aws_apigatewayv2_route.protected.route_key == "ANY /{proxy+}" && aws_apigatewayv2_route.protected.authorization_type == "JWT"
    error_message = "Every route must require a Cognito JWT by default."
  }

  assert {
    condition     = toset(keys(aws_apigatewayv2_route.public)) == toset(["GET /health", "GET /docs", "GET /openapi.json"])
    error_message = "Only the health check and the documentation may be public."
  }

  assert {
    condition     = aws_cognito_user_pool.main.admin_create_user_config[0].allow_admin_create_user_only
    error_message = "Self sign-up must be disabled."
  }
}

run "alarm_email_is_optional" {
  command = plan

  variables {
    alarm_email = "oncall@example.com"
  }

  assert {
    condition     = length(aws_sns_topic_subscription.alarms_email) == 1
    error_message = "An alarm email must create one subscription."
  }
}

run "a_single_availability_zone_is_rejected" {
  command = plan

  variables {
    availability_zone_count = 1
  }

  expect_failures = [var.availability_zone_count]
}

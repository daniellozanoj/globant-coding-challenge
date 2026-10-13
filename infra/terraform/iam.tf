# One least-privilege role per Lambda.

locals {
  # rds-db:connect is granted for a single database user of this cluster.
  db_user_arn = "arn:aws:rds-db:${var.aws_region}:${local.account_id}:dbuser:${aws_rds_cluster.main.cluster_resource_id}/${var.db_iam_user}"
}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# --- API ---

resource "aws_iam_role" "api" {
  name               = "${local.name}-api"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "api_vpc" {
  role       = aws_iam_role.api.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

data "aws_iam_policy_document" "api" {
  statement {
    sid       = "ConnectToDatabase"
    actions   = ["rds-db:connect"]
    resources = [local.db_user_arn]
  }

  statement {
    # Presigned URLs are signed with this role: it must be allowed to put landing files.
    sid       = "SignLandingUploads"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.raw.arn}/landing/*"]
  }
}

resource "aws_iam_role_policy" "api" {
  name   = "api"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api.json
}

# --- Loader ---

resource "aws_iam_role" "loader" {
  name               = "${local.name}-loader"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "loader_vpc" {
  role       = aws_iam_role.loader.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

data "aws_iam_policy_document" "loader" {
  statement {
    sid       = "ConnectToDatabase"
    actions   = ["rds-db:connect"]
    resources = [local.db_user_arn]
  }

  statement {
    sid       = "ReadLandingFiles"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.raw.arn}/landing/*"]
  }

  statement {
    sid       = "WriteRejectedRows"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.raw.arn}/rejected/*"]
  }

  statement {
    sid = "ConsumeLoaderQueue"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:ChangeMessageVisibility",
      "sqs:GetQueueAttributes",
    ]
    resources = [aws_sqs_queue.loader.arn]
  }
}

resource "aws_iam_role_policy" "loader" {
  name   = "loader"
  role   = aws_iam_role.loader.id
  policy = data.aws_iam_policy_document.loader.json
}

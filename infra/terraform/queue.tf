# Buffer between S3 notifications and the loader Lambda: absorbs bursts, retries failures and
# isolates poison messages in a DLQ.

resource "aws_sqs_queue" "loader_dlq" {
  name                      = "${local.name}-loader-dlq"
  message_retention_seconds = 1209600 # 14 days to inspect and redrive
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "loader" {
  name                    = "${local.name}-loader"
  sqs_managed_sse_enabled = true
  # AWS recommends at least 6x the function timeout for Lambda event sources.
  visibility_timeout_seconds = var.loader_timeout_seconds * 6
  message_retention_seconds  = 345600 # 4 days

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.loader_dlq.arn
    maxReceiveCount     = var.loader_max_receive_count
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "loader_dlq" {
  queue_url = aws_sqs_queue.loader_dlq.id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.loader.arn]
  })
}

data "aws_iam_policy_document" "loader_queue" {
  statement {
    sid       = "AllowRawBucketNotifications"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.loader.arn]

    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_s3_bucket.raw.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_sqs_queue_policy" "loader" {
  queue_url = aws_sqs_queue.loader.id
  policy    = data.aws_iam_policy_document.loader_queue.json
}

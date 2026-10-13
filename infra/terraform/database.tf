# Aurora PostgreSQL Serverless v2: scales from 0 ACU (auto-pause, storage-only cost when idle)
# up to db_max_capacity. Lambdas authenticate with IAM tokens; the master password is generated
# and rotated by RDS in Secrets Manager and only used for bootstrap.

resource "aws_db_subnet_group" "main" {
  name       = local.name
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_rds_cluster" "main" {
  cluster_identifier = local.name
  engine             = "aurora-postgresql"
  engine_mode        = "provisioned"
  engine_version     = var.db_engine_version
  database_name      = var.db_name

  master_username             = var.db_master_username
  manage_master_user_password = true

  iam_database_authentication_enabled = true
  # RDS Data API: lets the deployment bootstrap the IAM database user over HTTPS, without
  # network access to the private VPC.
  enable_http_endpoint = true

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.database.id]

  storage_encrypted       = true
  backup_retention_period = var.db_backup_retention_days
  copy_tags_to_snapshot   = true

  deletion_protection       = var.deletion_protection
  skip_final_snapshot       = !var.deletion_protection
  final_snapshot_identifier = var.deletion_protection ? "${local.name}-final" : null

  serverlessv2_scaling_configuration {
    min_capacity             = var.db_min_capacity
    max_capacity             = var.db_max_capacity
    seconds_until_auto_pause = var.db_min_capacity == 0 ? var.db_seconds_until_auto_pause : null
  }
}

resource "aws_rds_cluster_instance" "main" {
  count = var.db_instance_count

  identifier           = "${local.name}-${count.index + 1}"
  cluster_identifier   = aws_rds_cluster.main.id
  instance_class       = "db.serverless"
  engine               = aws_rds_cluster.main.engine
  engine_version       = aws_rds_cluster.main.engine_version
  db_subnet_group_name = aws_db_subnet_group.main.name

  performance_insights_enabled = false
}

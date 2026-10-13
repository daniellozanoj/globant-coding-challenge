#!/usr/bin/env bash
# Create the IAM-authenticated database user the Lambdas connect as.
#
# Runs once after `terraform apply`, through the RDS Data API (HTTPS): no network access to the
# private VPC is needed. Uses the master credentials stored by RDS in Secrets Manager.
#
# Usage: scripts/bootstrap-db-user.sh   (from the repository root, after terraform apply)
set -euo pipefail

TF_DIR="${TF_DIR:-infra/terraform}"
DB_NAME="${DB_NAME:-globant}"
DB_USER="${DB_USER:-app_iam}"

cluster_arn="$(terraform -chdir="$TF_DIR" output -raw db_cluster_arn)"
secret_arn="$(terraform -chdir="$TF_DIR" output -raw db_master_secret_arn)"

run_sql() {
  # A paused Aurora Serverless v2 cluster resumes on the first call; retry while it wakes up.
  for attempt in 1 2 3 4 5 6; do
    if aws rds-data execute-statement \
      --resource-arn "$cluster_arn" \
      --secret-arn "$secret_arn" \
      --database "$DB_NAME" \
      --sql "$1" >/dev/null; then
      return 0
    fi
    echo "Database not ready (attempt $attempt), retrying in 10 seconds..." >&2
    sleep 10
  done
  return 1
}

echo "Creating database user ${DB_USER} with IAM authentication..."
run_sql "DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} WITH LOGIN;
  END IF;
END \$\$"
run_sql "GRANT rds_iam TO ${DB_USER}"
# The migrations run as this user, so it owns the application schema objects.
run_sql "GRANT ALL ON SCHEMA public TO ${DB_USER}"
echo "Done."

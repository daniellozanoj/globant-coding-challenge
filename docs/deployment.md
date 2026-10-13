# Deploying to AWS

Step-by-step guide to deploy the architecture described in [architecture.md](architecture.md)
with the Terraform code in [`infra/terraform/`](../infra/terraform/), test it end to end and tear
it down.

> **Cost:** with the default (dev) settings the stack idles at roughly 1–3 USD/month, mostly
> Aurora storage, one secret and logs. Aurora is billed per ACU-hour while it is running; it
> pauses after 15 idle minutes. Always run [teardown](#9-teardown) when you are done.
> Validate prices for your region with the [AWS Pricing Calculator](https://calculator.aws/).

- [Prerequisites](#prerequisites)
- [1. Configure Terraform](#1-configure-terraform)
- [2. Create the container registry](#2-create-the-container-registry)
- [3. Build and push the image](#3-build-and-push-the-image)
- [4. Deploy the stack](#4-deploy-the-stack)
- [5. Bootstrap the database user](#5-bootstrap-the-database-user)
- [6. Run the migrations](#6-run-the-migrations)
- [7. Create a user and get a token](#7-create-a-user-and-get-a-token)
- [8. Test end to end](#8-test-end-to-end)
- [9. Teardown](#9-teardown)
- [Troubleshooting](#troubleshooting)
- [Continuous delivery (next step)](#continuous-delivery-next-step)

## Prerequisites

- An AWS account and credentials with administrator access for the first deployment
  (`aws sts get-caller-identity` must work).
- [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html).
- [Terraform](https://developer.hashicorp.com/terraform/install) 1.10 or later.
- Docker able to build `linux/arm64` images (native on Apple silicon; elsewhere use
  `docker buildx` with QEMU).

```bash
export AWS_REGION=us-east-1
export TF_DIR=infra/terraform
export IMAGE_TAG=$(git rev-parse --short HEAD)   # immutable tag: the commit SHA
```

## 1. Configure Terraform

Optional but recommended: keep the state in S3 with native locking.

```bash
cp $TF_DIR/backend.tf.example $TF_DIR/backend.tf   # then set your state bucket
cp $TF_DIR/terraform.tfvars.example $TF_DIR/terraform.tfvars
terraform -chdir=$TF_DIR init
```

Without `backend.tf` the state is stored locally in `infra/terraform/terraform.tfstate`
(ignored by Git).

## 2. Create the container registry

The Lambdas need an image in ECR before they can be created, so the repository goes first:

```bash
terraform -chdir=$TF_DIR apply -target=aws_ecr_repository.api -var image_tag=$IMAGE_TAG
export ECR_URL=$(terraform -chdir=$TF_DIR output -raw ecr_repository_url)
```

## 3. Build and push the image

```bash
aws ecr get-login-password --region $AWS_REGION \
  | docker login --username AWS --password-stdin ${ECR_URL%%/*}

# Apple silicon (native arm64):
docker build -t $ECR_URL:$IMAGE_TAG .
# Elsewhere: Lambda rejects images with provenance attestations, hence --provenance=false
# docker buildx build --platform linux/arm64 --provenance=false -t $ECR_URL:$IMAGE_TAG .

docker push $ECR_URL:$IMAGE_TAG
```

## 4. Deploy the stack

```bash
terraform -chdir=$TF_DIR plan -var image_tag=$IMAGE_TAG -out=tfplan
terraform -chdir=$TF_DIR apply tfplan
```

Aurora takes several minutes to create. Then export the outputs used below:

```bash
export API_URL=$(terraform -chdir=$TF_DIR output -raw api_url)
export POOL_ID=$(terraform -chdir=$TF_DIR output -raw cognito_user_pool_id)
export CLIENT_ID=$(terraform -chdir=$TF_DIR output -raw cognito_client_id)
export LOADER_FN=$(terraform -chdir=$TF_DIR output -raw loader_function_name)

curl $API_URL/health   # {"status":"ok"}: public route, no token needed
```

## 5. Bootstrap the database user

The Lambdas connect as `app_iam` with IAM authentication. Create that user once, through the RDS
Data API (no access to the private VPC needed), with the master credentials that RDS stores in
Secrets Manager:

```bash
scripts/bootstrap-db-user.sh
```

It runs `CREATE ROLE app_iam WITH LOGIN`, `GRANT rds_iam TO app_iam` and grants the `public`
schema to the user, retrying while a paused cluster resumes.

## 6. Run the migrations

Migrations run inside the VPC, invoking the loader Lambda with a migration event:

```bash
aws lambda invoke --function-name $LOADER_FN \
  --cli-binary-format raw-in-base64-out \
  --payload '{"action": "migrate"}' migrate.json && cat migrate.json
# {"status": "migrated", "revision": "0001"}
```

Run this step on every deployment that adds a migration.

## 7. Create a user and get a token

Users are created by an administrator only:

```bash
export API_USER=demo@example.com
export API_PASSWORD='Choose-A-Strong-Passw0rd!'

aws cognito-idp admin-create-user --user-pool-id $POOL_ID --username $API_USER \
  --message-action SUPPRESS
aws cognito-idp admin-set-user-password --user-pool-id $POOL_ID --username $API_USER \
  --password "$API_PASSWORD" --permanent

export TOKEN=$(aws cognito-idp initiate-auth --client-id $CLIENT_ID \
  --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters USERNAME=$API_USER,PASSWORD="$API_PASSWORD" \
  --query AuthenticationResult.AccessToken --output text)
```

Tokens last 60 minutes. Requests without a valid token get `401` from API Gateway.

## 8. Test end to end

```bash
AUTH="Authorization: Bearer $TOKEN"

# Asynchronous migration: presigned URL -> direct upload to S3 -> SQS -> loader Lambda
for table in departments jobs hired_employees; do
  ticket=$(curl -s -X POST $API_URL/api/v1/uploads -H "$AUTH" \
    -H "Content-Type: application/json" -d "{\"table\": \"$table\"}")
  curl -s -X PUT "$(echo $ticket | jq -r .upload_url)" -H "Content-Type: text/csv" \
    --data-binary @data/$table.csv
  status_url=$(echo $ticket | jq -r .status_url)
  until curl -s $status_url -H "$AUTH" | jq -e '.status == "SUCCEEDED" or .status == "FAILED"' >/dev/null; do
    sleep 3
  done
  curl -s $status_url -H "$AUTH" | jq '{table_name, status, rows_loaded, rows_rejected}'
done
```

Load the catalogs before `hired_employees`, as above: employees referencing unknown departments
or jobs are rejected. The 70 invalid employees are also written to
`s3://<raw bucket>/rejected/hired_employees/<job_id>.csv`.

```bash
# Batch insert and Section 2 metrics
curl -s -X POST $API_URL/api/v1/jobs/batch -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"rows": [{"id": 184, "job": "Data Engineer"}]}'
curl -s "$API_URL/api/v1/metrics/departments-above-mean?year=2021" -H "$AUTH" | jq
curl -s "$API_URL/api/v1/metrics/hires-by-quarter?year=2021&format=csv" -H "$AUTH" | head

# Without a token
curl -s -o /dev/null -w "%{http_code}\n" $API_URL/api/v1/metrics/hires-by-quarter   # 401
```

The interactive documentation is public at `$API_URL/docs`.

## 9. Teardown

```bash
terraform -chdir=$TF_DIR destroy -var image_tag=$IMAGE_TAG
```

With the dev defaults (`force_destroy_bucket`, `ecr_force_delete`, no `deletion_protection`) this
removes everything, including the bucket contents, the images and the database (no final
snapshot). In production set `deletion_protection = true`.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| First request after a while takes ~15 s or times out | Aurora was paused (min 0 ACU) and is resuming. Retry, or set `db_min_capacity = 0.5` |
| Lambda creation fails: image manifest not supported | The image was built with provenance attestations; rebuild with `--provenance=false` |
| Lambda creation fails: reserved concurrency | New accounts have a low concurrency quota; keep `api_reserved_concurrency = -1` |
| `PAM authentication failed` in the logs | The `app_iam` user was not bootstrapped (step 5) or `db_iam_user` differs |
| Files stay `PENDING` | Check the loader logs (`/aws/lambda/<name>-loader`) and the DLQ; the key must be `landing/{table}/{job_id}.csv` |
| `401` with a token | Use the **access** token from `initiate-auth`, issued by this user pool and app client |

## Continuous delivery (next step)

Not implemented yet. A GitHub Actions workflow on `main` would:

1. Assume a deployment role through **GitHub OIDC** (no long-lived AWS keys in the repository).
2. Build the arm64 image on a native arm64 runner and push it to ECR tagged with the commit SHA.
3. Run a real `terraform plan` on pull requests (posted as a comment) and `terraform apply` on
   `main`. The CI already runs `terraform test`, a plan against a mocked provider.
4. Invoke the loader Lambda with `{"action": "migrate"}`.
5. Smoke test `GET /health` and an authenticated metrics request.

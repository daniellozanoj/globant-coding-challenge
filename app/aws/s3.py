"""Thin S3 adapter used by the API (presigned uploads) and the event-driven loader."""

from functools import cache
from typing import Any

import boto3
from botocore.config import Config

CSV_CONTENT_TYPE = "text/csv"


@cache
def s3_client(region: str) -> Any:
    # SigV4 is required for presigned URLs in every current region (SigV2 is deprecated).
    return boto3.client("s3", region_name=region, config=Config(signature_version="s3v4"))


def presign_upload(region: str, bucket: str, key: str, expires_in: int) -> str:
    """URL that lets a client PUT one CSV object directly into S3, without AWS credentials."""
    return s3_client(region).generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket, "Key": key, "ContentType": CSV_CONTENT_TYPE},
        ExpiresIn=expires_in,
        HttpMethod="PUT",
    )

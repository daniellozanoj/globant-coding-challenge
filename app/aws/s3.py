"""Thin S3 adapter used by the API (presigned uploads) and the event-driven loader."""

import io
from functools import cache
from typing import Any, TextIO

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


def open_text(region: str, bucket: str, key: str) -> TextIO:
    """Stream an object as UTF-8 text (BOM dropped, newlines kept for the csv module)."""
    body = s3_client(region).get_object(Bucket=bucket, Key=key)["Body"]
    return io.TextIOWrapper(body, encoding="utf-8-sig", newline="")


def put_text(region: str, bucket: str, key: str, content: str, content_type: str) -> None:
    s3_client(region).put_object(
        Bucket=bucket, Key=key, Body=content.encode("utf-8"), ContentType=content_type
    )

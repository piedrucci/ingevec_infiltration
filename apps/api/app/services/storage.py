from functools import lru_cache

import boto3
from botocore.exceptions import ClientError

from app.core.config import get_settings


@lru_cache
def s3_client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=str(settings.S3_ENDPOINT_URL),
        region_name=settings.S3_REGION,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
    )


def put_private_object(key: str, content: bytes, content_type: str) -> None:
    settings = get_settings()
    client = s3_client()
    try:
        client.head_bucket(Bucket=settings.S3_BUCKET)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in {"404", "NoSuchBucket"}:
            raise
        client.create_bucket(Bucket=settings.S3_BUCKET)
    client.put_object(Bucket=settings.S3_BUCKET, Key=key, Body=content, ContentType=content_type)


def get_private_object(key: str) -> bytes:
    settings = get_settings()
    response = s3_client().get_object(Bucket=settings.S3_BUCKET, Key=key)
    body = response["Body"]
    try:
        return body.read()
    finally:
        body.close()


def copy_private_object(source_key: str, destination_key: str) -> None:
    settings = get_settings()
    s3_client().copy_object(
        Bucket=settings.S3_BUCKET,
        Key=destination_key,
        CopySource={"Bucket": settings.S3_BUCKET, "Key": source_key},
    )


def delete_private_object(key: str) -> None:
    settings = get_settings()
    s3_client().delete_object(Bucket=settings.S3_BUCKET, Key=key)

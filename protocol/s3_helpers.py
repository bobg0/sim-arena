"""Thin boto3 helpers used by worker.py and dispatch.py."""

import json
import os
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import ClientError


def _client():
    return boto3.client("s3", region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-2"))


def upload_file(local_path: str, bucket: str, key: str) -> None:
    _client().upload_file(local_path, bucket, key)


def download_file(bucket: str, key: str, local_path: str) -> None:
    Path(local_path).parent.mkdir(parents=True, exist_ok=True)
    _client().download_file(bucket, key, local_path)


def object_exists(bucket: str, key: str) -> bool:
    try:
        _client().head_object(Bucket=bucket, Key=key)
        return True
    except ClientError:
        return False


def put_json(bucket: str, key: str, data: dict) -> None:
    _client().put_object(Bucket=bucket, Key=key, Body=json.dumps(data, indent=2).encode())


def get_json(bucket: str, key: str) -> dict:
    resp = _client().get_object(Bucket=bucket, Key=key)
    return json.loads(resp["Body"].read().decode())


def list_keys(bucket: str, prefix: str) -> list:
    keys = []
    paginator = _client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def delete_object(bucket: str, key: str) -> None:
    _client().delete_object(Bucket=bucket, Key=key)


def copy_object(bucket: str, src_key: str, dst_key: str) -> None:
    """Server-side copy within the same bucket (used for sync_identity_server tests)."""
    _client().copy_object(
        Bucket=bucket,
        CopySource={"Bucket": bucket, "Key": src_key},
        Key=dst_key,
    )


def s3_uri_to_bucket_key(uri: str):
    """Parse 's3://bucket/some/key' → ('bucket', 'some/key')."""
    if not uri.startswith("s3://"):
        raise ValueError(f"Not an S3 URI: {uri}")
    rest = uri[5:]
    bucket, _, key = rest.partition("/")
    return bucket, key

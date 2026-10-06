import base64

import boto3
from botocore.exceptions import ClientError

from .config import settings


def client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
    )


def put(tenant, job_id, shot):
    s3 = client()
    try:
        s3.create_bucket(Bucket=settings.s3_bucket)
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            raise
    key = f"{tenant}/{job_id}/{shot['id']}.png"
    s3.put_object(Bucket=settings.s3_bucket, Key=key, Body=base64.b64decode(shot["png"]), ContentType="image/png")
    return key

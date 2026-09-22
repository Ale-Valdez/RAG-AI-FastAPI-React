from __future__ import annotations

from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.config import Config


class S3DocumentBytes:
    def __init__(
        self,
        *,
        endpoint_url: str,
        region: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        use_path_style: bool,
        client: BaseClient | None = None,
    ) -> None:
        self._endpoint_url = endpoint_url
        self._region = region
        self._bucket = bucket
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._use_path_style = use_path_style
        self._client = client

    def put(
        self,
        *,
        tenant_id: str,
        document_id: str,
        filename: str,
        content: bytes,
    ) -> None:
        self._get_client().put_object(
            Bucket=self._bucket,
            Key=self._key(tenant_id, document_id, filename),
            Body=content,
        )

    def get(self, *, tenant_id: str, document_id: str, filename: str) -> bytes:
        response = self._get_client().get_object(
            Bucket=self._bucket,
            Key=self._key(tenant_id, document_id, filename),
        )
        body = response["Body"].read()
        return bytes(body)

    def delete(self, *, tenant_id: str, document_id: str, filename: str) -> None:
        self._get_client().delete_object(
            Bucket=self._bucket,
            Key=self._key(tenant_id, document_id, filename),
        )

    def _get_client(self) -> Any:
        if self._client is None:
            config = (
                Config(s3={"addressing_style": "path"}) if self._use_path_style else None
            )
            self._client = boto3.client(
                "s3",
                endpoint_url=self._endpoint_url or None,
                region_name=self._region,
                aws_access_key_id=self._access_key_id,
                aws_secret_access_key=self._secret_access_key,
                config=config,
            )
        return self._client

    @staticmethod
    def _key(tenant_id: str, document_id: str, filename: str) -> str:
        return f"{tenant_id}/{document_id}/{filename}"

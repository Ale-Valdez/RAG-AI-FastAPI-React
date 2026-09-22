from __future__ import annotations

from app.infrastructure.config.settings import Settings
from app.infrastructure.storage.s3_document_bytes import S3DocumentBytes
from app.infrastructure.worker.document_job_queue import CeleryDocumentJobQueue


def test_max_document_size_bytes_converts_mb() -> None:
    assert Settings(max_document_size_mb=20).max_document_size_bytes == 20 * 1024 * 1024


def test_s3_document_bytes_put_delete_and_path_style(monkeypatch) -> None:  # noqa: ANN001
    put_calls: list[dict[str, object]] = []
    delete_calls: list[dict[str, object]] = []

    class FakeClient:
        def put_object(self, **kwargs: object) -> None:
            put_calls.append(kwargs)

        def delete_object(self, **kwargs: object) -> None:
            delete_calls.append(kwargs)

    store = S3DocumentBytes(
        endpoint_url="http://garage:3900",
        region="garage",
        bucket="ai-rag-documents",
        access_key_id="key",
        secret_access_key="secret",
        use_path_style=True,
        client=FakeClient(),
    )
    store.put(
        tenant_id="t1",
        document_id="d1",
        filename="handbook.pdf",
        content=b"%PDF-1.4",
    )
    store.delete(tenant_id="t1", document_id="d1", filename="handbook.pdf")

    assert put_calls == [
        {
            "Bucket": "ai-rag-documents",
            "Key": "t1/d1/handbook.pdf",
            "Body": b"%PDF-1.4",
        }
    ]
    assert delete_calls == [
        {"Bucket": "ai-rag-documents", "Key": "t1/d1/handbook.pdf"}
    ]

    captured: dict[str, object] = {}

    def fake_boto_client(service: str, **kwargs: object) -> FakeClient:
        assert service == "s3"
        captured.update(kwargs)
        return FakeClient()

    monkeypatch.setattr(
        "app.infrastructure.storage.s3_document_bytes.boto3.client",
        fake_boto_client,
    )
    S3DocumentBytes(
        endpoint_url="http://garage:3900",
        region="garage",
        bucket="ai-rag-documents",
        access_key_id="key",
        secret_access_key="secret",
        use_path_style=True,
    )._get_client()
    config = captured["config"]
    assert config is not None
    assert config.s3.get("addressing_style") == "path"  # type: ignore[union-attr]


def test_celery_document_job_queue_send_task(monkeypatch) -> None:  # noqa: ANN001
    sent: dict[str, object] = {}

    def fake_send_task(name: str, **kwargs: object) -> None:
        sent["name"] = name
        sent["kwargs"] = kwargs.get("kwargs")

    monkeypatch.setattr(
        "app.infrastructure.worker.document_job_queue.celery_app.send_task",
        fake_send_task,
    )
    CeleryDocumentJobQueue().enqueue(
        tenant_id="t1", user_id="u1", document_id="d1"
    )
    assert sent["name"] == "app.infrastructure.worker.tasks.process_document"
    assert sent["kwargs"] == {
        "tenant_id": "t1",
        "user_id": "u1",
        "document_id": "d1",
    }

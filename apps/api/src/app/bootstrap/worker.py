from __future__ import annotations

from app.application.documents.process_document import ProcessDocument, ProcessOutcome
from app.bootstrap.persistence import LazySessionFactory
from app.domain.actor import Actor
from app.infrastructure.config.settings import Settings, load_settings
from app.infrastructure.ingestion.openai_embeddings import OpenAIEmbeddingGenerator
from app.infrastructure.ingestion.page_chunker import PageAwareChunker
from app.infrastructure.ingestion.pypdf_extractor import PypdfTextExtractor
from app.infrastructure.ingestion.qdrant_chunk_store import QdrantChunkStore
from app.infrastructure.persistence.document_repository import SqlAlchemyDocumentRepository
from app.infrastructure.storage.s3_document_bytes import S3DocumentBytes


class SessionBoundProcessDocument:
    def __init__(
        self,
        open_session: LazySessionFactory,
        bytes_store: S3DocumentBytes,
        extractor: PypdfTextExtractor,
        chunker: PageAwareChunker,
        embeddings: OpenAIEmbeddingGenerator,
        chunk_store: QdrantChunkStore,
        *,
        max_pages: int,
        max_concurrent: int,
    ) -> None:
        self._open_session = open_session
        self._bytes_store = bytes_store
        self._extractor = extractor
        self._chunker = chunker
        self._embeddings = embeddings
        self._chunk_store = chunk_store
        self._max_pages = max_pages
        self._max_concurrent = max_concurrent

    def execute(self, actor: Actor, document_id: str) -> ProcessOutcome:
        session = self._open_session()
        try:
            use_case = ProcessDocument(
                SqlAlchemyDocumentRepository(session),
                self._bytes_store,
                self._extractor,
                self._chunker,
                self._embeddings,
                self._chunk_store,
                max_pages=self._max_pages,
                max_concurrent=self._max_concurrent,
                commit=session.commit,
            )
            return use_case.execute(actor, document_id)
        except Exception:
            session.rollback()
            raise
        else:
            session.commit()
        finally:
            session.close()


def build_process_document(settings: Settings | None = None) -> SessionBoundProcessDocument:
    loaded = settings or load_settings()
    bytes_store = S3DocumentBytes(
        endpoint_url=loaded.s3_endpoint_url,
        region=loaded.s3_region,
        bucket=loaded.s3_bucket,
        access_key_id=loaded.s3_access_key_id,
        secret_access_key=loaded.s3_secret_access_key,
        use_path_style=loaded.s3_use_path_style,
    )
    return SessionBoundProcessDocument(
        LazySessionFactory(loaded.database_url),
        bytes_store,
        PypdfTextExtractor(),
        PageAwareChunker(),
        OpenAIEmbeddingGenerator(
            api_key=loaded.openai_api_key,
            model=loaded.openai_embed_model,
        ),
        QdrantChunkStore(url=loaded.qdrant_url),
        max_pages=loaded.max_document_pages,
        max_concurrent=loaded.max_concurrent_ingestions_per_tenant,
    )

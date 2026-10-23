# RAG

PDF -> Docling extraction -> filter -> HybridChunker -> embeddings -> Qdrant
-> filtered retrieval -> context assembly -> LLM -> answer + sources

Docling `2.142.1` reads the PDF. A project filter drops furniture and other
discarded labels, attaches linked notes, folds table captions into the table,
and marks the document `headed` or `flat`. `HybridChunker` cuts the filtered
document with the OpenAI `cl100k_base` tokenizer at 512 tokens. Chunk bounds
move `chunk_index` when that pin changes. The worker image downloads Docling
models into `DOCLING_ARTIFACTS_PATH` at build time. The API process does not
import the converter.

Each point id is the uuid5 of `document_id:chunk_index`. The payload keeps
`tenant_id`, `document_id`, `filename`, `page` (start, 0-based), `chunk_index`,
and `text`, and adds `section_path`, `heading`, `page_end`, `element_type`
(`text`, `list`, or `table`), and `structure` (`headed` or `flat`). `text` is
`contextualize()`, which joins the heading path and the body with newlines.
Flat documents
that were split repeat the previous text or list chunk's last sentence at the
start of the next one. Headed documents do not. Embeddings use `text` only.
Search filters tenant and document. It does not filter on `structure`.
Citations stay `document_id`, `filename`, `page`, and `chunk_index`.

The page limit uses the PDF page count, including blank pages. Re-ingesting a
document deletes that `document_id`'s points before the new upsert. Documents
already `ready` are not migrated; their points change only on re-ingest.

Cross-tenant retrieval is prohibited.

---
title: 'Docling PDF extraction and chunking'
type: 'feature'
created: '2026-10-23'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'e79a63d7e1865b1a2b6bfe05c3ddc133ba791f3c'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Ingest extracts plain text per page with `PypdfTextExtractor` and cuts each page at 1000 characters in `PageAwareChunker`. Chunks have no heading path, so embeddings, lexical match, and the LLM never see section context. Tables, captions, footnotes, and running headers are not distinguished.

**Approach:** Docling stays the structure extractor. A project filter drops discarded labels, attaches linked notes, and marks the document `headed` or `flat`. `HybridChunker` performs the cut. A mapper builds this project's `TextChunk`. Flat documents that were split overlap the last sentence; headed documents do not. The use case stays extract, chunk, embed `chunk.text`, upsert.

## Boundaries & Constraints

**Always:**
- `tenant_id` comes from `Actor`. Domain and application do not import FastAPI, SQLAlchemy, Celery, Qdrant, LangChain, OpenAI, boto3, or Docling.
- Use-case tests use in-memory fakes. No Docker and no network. The default suite does not download models and does not read a PDF.
- Pin `docling==2.142.1`. Chunk bounds move `chunk_index` on upgrade.
- Point id stays `uuid5` of `document_id:chunk_index`. Embed, store, and show `chunk.text`. That string is `contextualize()` (headings, blank line, body), then the flat overlap edit.
- Keep `tenant_id`, `document_id`, `filename`, `page` (start, 0-based), `chunk_index`, `text`. Add `section_path`, `heading`, `page_end`, `element_type` (`text`|`list`|`table`), `structure` (`headed`|`flat`).
- Do not filter search on `structure`. Do not change `top_k`, hybrid fusion, or citation JSON. `SourceRef.page` stays the start page. `RetrievedChunk` keeps its current fields.
- Tokenizer is OpenAI `cl100k_base` via `OpenAITokenizer`, `max_tokens=512`. Do not construct a HuggingFace tokenizer.
- API and worker share `apps/api/Dockerfile`. The API process must not import the converter or torch. Models are downloaded in the worker image build (`DOCLING_ARTIFACTS_PATH`) and not at runtime.
- Ready documents are not migrated. Existing re-ingest already deletes that `document_id`'s points before upsert. Say so in `docs/rag.md`.
- Page limit stays `page_count > max_pages`, and blank pages still count. `page_count` is the PDF page count, not the block count.
- Heading levels use Docling's library order: `HeadingHierarchyOptions(enabled=True, use_bookmarks=True, use_numbering=True, use_style=True)` and `generate_parsed_pages=True`. A confident bookmark match wins. Numbering, then style, applies when no bookmark matches. `III` and `III.1` are not both level 1 when numbering applies.

**Never:**
- Unstructured, LangChain, parent/child retrieval, citation UI, a different embedding model, OCR to repair split words, non-PDF formats, or a reimplementation of `HybridChunker`'s split and merge.
- Persisting Docling's label enum, bounding boxes, or the document JSON.
- Prepending the filename. Inventing parent headings when every remaining heading is level 1.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Headed group | Title, subtitle, four paragraphs that fit in 512 tokens | One chunk. `contextualize()` text includes the path. `section_path` is those headings. `element_type=text`. `structure=headed` | N/A |
| New subtitle | Body under heading A, then heading B | B's chunk does not contain A's body | N/A |
| Level-1 only | Every remaining heading is level 1 | Each chunk's path is that single heading. No invented parent | N/A |
| Flat short | No headings, body fits in one chunk | `section_path` empty, `heading` null, `structure=flat`, `text` is the body and does not contain the filename. No overlap | N/A |
| Flat cut | No headings, body exceeds 512 tokens and contains sentence terminators | Following body chunk starts with the previous chunk's last sentence. Table chunks are not donors or receivers | N/A |
| Letterhead | Same heading on more than half the pages | That heading is absent from `section_path`. If nothing remains, the document is flat | N/A |
| Table | Table with a caption | One `element_type=table` chunk whose `text` starts with the caption. No caption-only point | N/A |
| Footnote | Note linked to a paragraph or table; another note with no link | Linked note text is at the end of that block. Orphan text is absent | N/A |
| Furniture | Index, page header, page footer, plus the other discarded labels | Those labels are absent from the document passed to `HybridChunker` | N/A |
| Page span | Chunk provenance starts on Docling page 2 and ends on page 4 | `page=1`, `page_end=3` | N/A |
| Page limit | `page_count` 3, including blank pages, `max_pages` 2 | `failed`, no upsert | fail as today |
| Empty body | `page_count` within the limit and no chunks | `failed`, no upsert | fail as today |
| Re-ingest | Same `document_id`, old points present | Old points deleted, then new upsert | unchanged |

</frozen-after-approval>

## Code Map

- `apps/api/src/app/domain/ports/ingestion.py` — `PageText` / `extract_pages` / `chunk_pages` today. Replace with `ContentBlock` (`kind`, `level`, `text`, `page` 0-based), `ExtractedPdf` (`page_count`, `blocks`), and `TextChunk` fields `section_path`, `heading`, `page_end`, `element_type`, `structure`. New fields need defaults so current `TextChunk(...)` call sites keep compiling.
- `apps/api/src/app/application/documents/process_document.py` — lines 75–82: `extract_pages`, `len(pages) > max_pages`, `chunk_pages`. Switch to `extract` → `page_count` → `chunk`. Still embeds `chunk.text` only.
- `apps/api/src/app/infrastructure/ingestion/pypdf_extractor.py` and `page_chunker.py` — delete. `pypdf==6.19.0` leaves `pyproject.toml`.
- `apps/api/src/app/infrastructure/ingestion/qdrant_chunk_store.py` — upsert payload lines 81–88. `_chunk_from_payload` lines 27–35 stays on the old six fields. Search filters lines 111–118 stay tenant + document. `chunk_point_id` lines 38–39 stays.
- `apps/api/src/app/domain/ports/retrieval.py` `RetrievedChunk`; `domain/chat.py` `SourceRef`; `conversations_router.py` `_source_payload`; `conversation_repository.py` source JSON — do not add fields.
- `apps/api/src/app/bootstrap/worker.py` — `build_process_document` wires the pipeline. `tasks.py` line 2 imports that builder at import time; `document_job_queue.py` `send_task` finalizes Celery and imports `tasks`. Move the builder import into the task body so uvicorn never imports Docling.
- `apps/api/tests/fakes.py` — `FakePdfTextExtractor` and `InMemoryChunkStore` upsert dict. `test_process_document.py` page-limit and blank-page tests. `test_document_adapters.py` exact payload equality (lines 299–306) and pypdf test (line 797). `test_tenant_rls.py` `Unused.extract_pages` / `chunk_pages` (lines 476–480).
- `docs/rag.md` — still describes page-aware chunks. `compose.yaml` api and worker both `build.context: ./apps/api` with no target.
- AD-7 required payload keys stay. New keys are additive. Do not edit the architecture spine.

## Tasks & Acceptance

**Execution:**
- [x] `apps/api/src/app/domain/ports/ingestion.py` and `process_document.py` -- extraction returns `ExtractedPdf`; chunking accepts it; page limit uses `page_count` -- use case stays free of Docling
- [x] `apps/api/tests/fakes.py`, `test_process_document.py`, `test_tenant_rls.py` -- fakes and the page-limit / empty-chunk tests follow the new port; drop the 1000-character chunker tests -- application tests never import Docling
- [x] `apps/api/src/app/infrastructure/ingestion/` filter, mapper, and chunk pipeline -- filter a `docling-core` document, run `HybridChunker` with `OpenAITokenizer(cl100k_base, max_tokens=512)`, map to `TextChunk`, then flat sentence overlap -- the cut stays inside `HybridChunker`
- [x] `apps/api/tests/test_docling_chunks.py` -- cover every matrix row except page-limit, empty body, and re-ingest, using in-memory `docling-core` documents -- default suite does not convert a PDF
- [x] `qdrant_chunk_store.py`, `fakes.py` `InMemoryChunkStore`, `test_document_adapters.py` -- write the new payload keys; leave read-side chunks and citation JSON unchanged -- search and chat stay compatible
- [x] `bootstrap/worker.py`, `worker/tasks.py`, `pyproject.toml` -- wire one pipeline per `build_process_document()`; pin `docling==2.142.1` and the OpenAI chunking extra; lazy-import the converter inside the convert method and the builder inside the task -- API import graph does not load torch
- [x] `apps/api/Dockerfile`, `compose.yaml` -- `api` and `worker` targets; worker build runs model download into `DOCLING_ARTIFACTS_PATH` -- runtime does not fetch models
- [x] `docs/rag.md` -- describe this pipeline, the payload, the pin, and that ready points change only on re-ingest

**Acceptance Criteria:**
- Given a pending PDF over the page limit, or an extract that yields no chunks, when `ProcessDocument` runs against fakes, then the document is `failed` and nothing is upserted.
- Given the default `pytest` run, when it finishes, then it passes without Docker, without network, and without a model download.
- Given uvicorn's import graph (`app.bootstrap.http`), when it is loaded, then `docling` and `torch` are not imported.
- Given a headed chunk and a flat cut chunk, when they are upserted, then `text` is what gets embedded and both new and old payload keys are stored. Retrieval still builds `SourceRef` from `document_id`, `filename`, `page`, and `chunk_index` only.

## Implementation Notes

- `docling==2.142.1` is the `worker` extra. `docling-core[chunking-openai]==2.104.0` stays a runtime dependency so the chunker imports without torch. The API image installs the base package. The worker stage installs the extra, prefers the CPU torch index, then downloads models into `DOCLING_ARTIFACTS_PATH`.
- `pydantic-settings` moved to `2.14.0` because `docling-core` 2.104 requires it. `pypdf` is removed.
- `docling-core` 2.104 `contextualize()` joins headings and body with single newlines. Stored `text` is that string. It does not add an extra blank line.
- `HybridChunker(merge_peers=True)` also merges a table into neighboring body text. The mapper calls `HybridChunker._merge_chunks_with_matching_metadata` only on runs that are not tables, so the token merge stays in Docling and a table stays its own chunk.
- Chunk `doc_items` come back as base `DocItem` values. Table detection uses `label == table` and footnote suffixes are keyed by `self_ref`.
- Letterhead uses the conversion `page_count` when the pipeline has it, otherwise `len(document.pages)`.
- Default suite: 245 passed, 10 skipped (`test_tenant_rls.py`, no Postgres). No model download. Loading `app.bootstrap.http` does not import `docling` or `torch`. `create_app()` still raises if `JWT_SECRET` is unset; that happens after the import graph is loaded.
- Review patches: `chunk()` failures mark the document failed; picture captions are inserted at the picture; the worker image warms the tiktoken cache; Kubernetes worker uses the worker image and `DOCLING_ARTIFACTS_PATH`. `docs/rag.md` describes `contextualize()` as newline-joined, which is what docling-core 2.104 returns.

## Spec Change Log

## Review Triage Log

- medium — `process_document.py` `chunk()` sat outside the failure handler, so a chunk exception left the document `processing`. Patched: that call now uses `_fail`. `test_chunk_failure_marks_failed` covers it.
- defer — extract failures return `_fail` without logging the exception. Same `except` as the baseline `extract_pages` path. Logged in `deferred-work.md`.
- false — the page limit runs after `extract` because `page_count` is the conversion result, and the baseline already counted pages after extract. A kill during conversion leaving `processing` is the same committed `mark_processing` the baseline had.
- defer — an empty `ConversionResult.pages` list would make `page_count` 0. `generate_parsed_pages=True` is set, and this suite does not run the converter, so that outcome is unverified.
- false — `chunk` ignores `ExtractedPdf` on purpose. `build_process_document` passes one pipeline as both ports, and each job builds its own. Captions are not a block kind; they are relabeled text before `content_blocks`.
- false — `.` `!` `?` sentence bounds, including a single terminator, are the spec's last-sentence rule. Overlap does not re-cut to 512 tokens.
- medium — the worker image did not warm `cl100k_base`, so the first chunk could download it. Patched: `TIKTOKEN_CACHE_DIR=/opt/tiktoken` is filled at image build. Whether the following PyPI install replaces the CPU torch wheel, and whether `libgomp1` or RapidOCR weights are missing, was not built and is deferred.
- defer — `HeadingHierarchyOptions` and `generate_parsed_pages` are untested. A converter test needs the worker extra and must stay off the default suite.
- false — retrieval still reads the old payload fields. The spec keeps `RetrievedChunk` and `SourceRef.page` unchanged. The upsert of non-default keys is now asserted in `test_qdrant_upsert_uses_uuid5_cosine_and_payload`.
- false — `paragraph`, `field_key`, `field_value`, and `field_heading` are dropped because this slice is PDF-only. An attached table caption is included by `contextualize()`; `test_table_is_its_own_chunk_with_caption_first` starts the table chunk with that caption.
- low — rejected. Private Docling helpers are pinned to `docling==2.142.1` and `docling-core==2.104.0`, which `pip install ".[worker]"` honors. The converter singleton is process-wide and the worker env is set before the first convert.
- defer — partial conversions are not rejected. Whether `convert()` returns a partial document or raises was not executed here.
- false — a footnote whose owner is not a paragraph or table is an orphan. The spec appends notes only for those two.
- false — a footnote on a heading, caption, or formula is not a paragraph or table link, so it is dropped with the orphan rule.
- medium — `_move_subtree` without `pos` appended a picture caption to the end of its parent. Patched: the caption is inserted at the picture's index. The furniture test checks that order.
- defer — a caption and table that together exceed 512 tokens might split. The covered case keeps the caption on the table chunk. The overflow case was not built.
- defer — a bitmap page with no OCR engine might drop text. OCR repair is out of scope, and the converter was not run.
- low — rejected. Compose and the worker image set `DOCLING_ARTIFACTS_PATH`. Failing when it is unset would be a new guard for a misconfigured process.
- medium — `test_blank_pages_still_count_toward_page_limit` used a blank block, so the empty-chunk path could hide a `len(blocks)` check. Patched: the over-limit extract now has a non-blank block and still fails with no upsert.
- medium — the Qdrant payload test stored only default chunk fields. Patched: the point now carries a heading path, `page_end`, `element_type=table`, and `structure=headed`.
- medium — headed chunks and table neighbors did not pin the overlap skip. Patched in `test_docling_chunks.py`.
- medium — letterhead tests never passed `page_count`. Patched: three heading pages against `page_count=8` keep the heading.
- high — the Kubernetes worker still ran `ai-rag-api:latest`, which is now the API stage and has no Docling install. Patched: `ai-rag-worker:latest`, `DOCLING_ARTIFACTS_PATH`, the manifest test, and the README.
- medium — no test ran `DoclingPdfPipeline.extract` then `chunk`. Patched: `test_pipeline_chunks_the_document_from_extract` monkeypatches `_convert_pdf` and does not import `docling`.
- low — `docs/rag.md` said `contextualize()` inserts a blank line. Patched: it now says the stored string is newline-joined, matching docling-core 2.104.

## Design Notes

Decisions that follow from the request and the current code:

- One object built inside `build_process_document()` implements both ports. `extract` converts, filters, and stores the filtered `DoclingDocument` plus `structure`. `chunk` runs `HybridChunker` on that object. It does not rebuild a document from blocks. Each task constructs its own pipeline (`tasks.py` already calls `build_process_document()` per job).
- Blocks on the port are the filtered linear items (`title`, `section_header`, `text`, `list_item`, `table`, `code`, `formula`) so fakes can feed the use case. Production chunking uses the stored Docling document.
- Letterhead: a heading string that occurs on more than half of `page_count` when `page_count >= 2`. Remove it before chunking. If no heading remains, `structure=flat` and the path is cleared. One or more remaining headings, even all at level 1, stay `headed`.
- Last sentence: the suffix after the previous `.`, `!`, or `?`. If the body chunk has no terminator, do not overlap. Overlap only across consecutive `text`/`list` chunks of a flat document. Prepend it to the next chunk's `text` after `contextualize()`.
- `element_type`: `table` when the chunk includes a table; `list` when every body item is a list item; otherwise `text`. Code and formula stay in the surrounding text chunk.
- Discard before `HybridChunker`: `page_header`, `page_footer`, `document_index`, `reference`, `handwritten_text`, `marker`, `empty_value`, `field_hint`, `picture`, `chart`. Picture or chart captions stay as text items. Footnotes are appended to the linked paragraph or table, then removed; orphans are removed. Captions are folded into their table so they are not their own chunk. `checkbox_selected`, `checkbox_unselected`, and `grading_scale` become list items. Containers (`form`, `key_value_region`, `field_region`, `field_item`) are unwrapped. `paragraph`, `field_key`, `field_value`, and `field_heading` are dropped.
- `page` / `page_end` come from chunk provenance. Docling's page numbers are 1-based; subtract 1. Missing provenance uses 0 and 0.
- `heading` is the last `section_path` entry, or null. `page_end` equals `page` when the chunk does not cross a page.
- Import `HybridChunker` and `OpenAITokenizer` from `docling_core`. Import `DocumentConverter` only inside the convert function. `tiktoken.get_encoding("cl100k_base")`.
- A full-PDF converter test is optional and must not run in the default suite. Do not add one unless it is marked off the default run.

## Verification

**Commands:**
- `cd apps/api && uv run --extra dev pytest` -- expected: pass, no Docker, no model download
- `cd apps/api && uv run --extra dev python -c "import app.bootstrap.http"` -- expected: `docling` and `torch` absent from `sys.modules`

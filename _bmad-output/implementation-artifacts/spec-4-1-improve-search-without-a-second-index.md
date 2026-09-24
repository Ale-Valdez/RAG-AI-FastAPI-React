---
title: 'Improve search without a second index'
type: 'feature'
created: '2026-09-24'
status: 'done'
route: 'dispatch'
baseline_commit: '4ddd7828bcd886bb34efbee575fece500636f871'
review_loop_iteration: 1
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A question is embedded once and matched only by dense cosine on `chunks`, so a useful passage can be missed when the wording does not sit near the vector.

**Approach:** On the existing retrieve path, rewrite the query, fuse a dense search with a text match on the same `chunks` collection, then rerank. Isolation, the score cutoff, and citations stay in force.

## Boundaries & Constraints

**Always:**
- Hybrid search, rerank, and query rewrite run inside `RetrieveChunks` and `ChunkRetriever`. `AskQuestion` still retrieves, assembles `chunk.text`, then generates. It does not call a second retriever.
- One collection, `chunks`. Search does not create it and does not change its vector config. Upsert still stores one unnamed cosine vector and the same payload.
- Hybrid is query-time fusion of that dense vector and a match on payload `text`. No sparse vectors, no second collection, and no new Qdrant index.
- A text hit uses the distinctive words of the retrieval query. These words do not have to appear: what, when, where, does, this, that, with, from, have, which. Every other query word of four or more characters must appear in the passage. "what is the policy?" matches a passage that contains "policy". If no distinctive word remains, the text leg adds nothing.
- Every dense query and every text query filters on `actor.tenant_id` and the ready document ids. An optional `document_id` still limits both legs to that one ready document in the same tenant.
- Rewrite and rerank use `OPENAI_CHAT_MODEL` through the official OpenAI SDK. The query vector still uses `OPENAI_EMBED_MODEL` on the rewritten text.
- The stored user message is the typed question. Rewrite is for retrieval only.
- If rewrite fails, search uses the typed question. If rerank fails, the fused order is kept. The ask still completes.
- `SourceRef` stays `document_id`, `filename`, `page`, and `chunk_index`. Empty retrieval still stores the existing refusal and no sources.
- `RAG_SCORE_THRESHOLD` stays the existing environment setting. This environment sets it to 0.25; the code default stays 0.70. Compare each returned chunk score to that configured value. A chunk below it does not ground the answer. Do not add a second cutoff.
- Domain and application tests use in-memory fakes. No Docker.

**Never:**
- Re-embed, delete, or re-ingest existing points. Do not change `ProcessDocument`, document HTTP, auth, or conversation SQL.
- LangChain, a new model vendor, or a RAG engine that chat and ingestion call differently.
- A client-supplied tenant as the only filter. An unfiltered query. Returning a chunk from another tenant or from a document that is not `ready`.
- Putting `score` on `SourceRef`, or moving context assembly out of `AskQuestion`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Tenant scope | Ready chunks for tenants A and B | A's rewritten hybrid query returns only A's ready chunks | N/A |
| One document | A ready `document_id` in A's tenant | Both legs are limited to that document and still filter on A's tenant | N/A |
| Bad document id | Missing, other tenant, or not `ready` | No vector or text query | `NotFoundError` |
| No ready documents | Only pending, processing, or failed | Empty list; nothing is embedded or queried | N/A |
| Saved turn | A grounded answer | User content is the typed question; each source is the four `SourceRef` fields | N/A |
| Adapter failure | Rewrite or rerank raises | Retrieval continues with the typed question or the fused order | Ask does not fail for that reason |
| Below threshold | A chunk score is under the configured `RAG_SCORE_THRESHOLD` | That chunk is dropped. If none remain, the assistant refuses and stores no sources | N/A |
| Distinctive words | Query "what is the policy?"; a ready passage contains "policy" and not "what" | That passage is a text hit | N/A |
| No distinctive word | The query is only words such as "what" and "this" | The text leg adds no hit | N/A |

</frozen-after-approval>

## Code Map

Paths below are under `apps/api/` unless noted.

- `src/app/domain/ports/retrieval.py` — `ChunkRetriever.search` (lines 29–39) takes a vector and ready ids. `RetrievedChunk.to_source_ref` (lines 20–26) drops `score`. Extend `search` with the question string. Add rewrite and rerank protocols here so application does not import OpenAI.
- `src/app/application/retrieval/retrieve_chunks.py` — `RetrieveChunks.execute` (lines 28–46) embeds the typed question, then searches. This is where rewrite, embed, hybrid search, and rerank are ordered. Keep `_ready_ids` (lines 48–63).
- `src/app/application/chat/ask_question.py` — reuse `execute` (lines 52–58): chunks, `chunk.text`, `to_source_ref`, else `_REFUSAL`. Do not change that assembly.
- `src/app/infrastructure/ingestion/qdrant_chunk_store.py` — `_COLLECTION = "chunks"` (line 21). `search` (lines 81–126) calls `query_points` with `tenant_id`, `MatchAny(ready)`, optional `document_id`, and does not create the collection. Add the text leg on payload `text` with the same `must` filter and the distinctive-word rule in Boundaries. Leave `upsert_chunks` and `_ensure_collection` alone.
- `src/app/infrastructure/ingestion/openai_embeddings.py` — reuse `OpenAIEmbeddingGenerator` for the rewritten query.
- `src/app/infrastructure/chat/openai_answer_generator.py` — copy the OpenAI client setup for the rewrite and rerank adapters. Do not change `generate`.
- `src/app/infrastructure/config/settings.py` — reuse `openai_chat_model`, `rag_top_k`, `rag_score_threshold`. No new required setting.
- `src/app/bootstrap/create_app.py` — `SessionBoundAskQuestion` (lines 157–212) builds `RetrieveChunks` with the Qdrant store. Wire the new adapters there. Leave `_default_chat` offline until the first ask.
- `src/app/domain/ports/ingestion.py` — `EmbeddingGenerator.embed`. Do not add search to `ChunkVectorStore`.
- `tests/fakes.py` — `InMemoryChunkStore.search` mirrors the port. Extend it; do not require Qdrant.
- `tests/test_retrieve_chunks.py`, `tests/test_ask_question.py`, `tests/test_document_adapters.py` — keep the tenant, ready, `NotFoundError`, and "search does not create a collection" cases.

## Tasks & Acceptance

**Execution:**
- [x] `apps/api/src/app/domain/ports/retrieval.py` — pass the question string into `search` and add rewrite and rerank protocols — chat keeps one retrieve port
- [x] `apps/api/src/app/infrastructure/retrieval/` — add query-rewrite and rerank adapters on `OPENAI_CHAT_MODEL`, and the distinctive-word text score — failures fall back as in the matrix
- [x] `apps/api/src/app/infrastructure/ingestion/qdrant_chunk_store.py` — fuse dense `query_points` with a filtered text match on `chunks` — same tenant and ready filters, no new collection or index
- [x] `apps/api/src/app/application/retrieval/retrieve_chunks.py` — rewrite, embed the rewritten text, search, rerank, then apply the threshold decision in Boundaries — ready-id rules stay
- [x] `apps/api/src/app/bootstrap/create_app.py` — construct those adapters inside `SessionBoundAskQuestion` — `AskQuestion` stays retrieve-then-generate
- [x] `apps/api/tests/fakes.py`, `apps/api/tests/test_retrieve_chunks.py`, and `apps/api/tests/test_document_adapters.py` — cover the matrix, including distinctive words and the threshold — in-memory fakes, no Docker

**Acceptance Criteria:**
- Given the retrieve and embed ports and `chunks`, when hybrid search, rerank, and query rewrite run, then each sits on that path and search does not create a collection or an unfiltered index
- Given chunks for tenants A and B, when a rewritten hybrid query runs as A, then every leg filters on A's `tenant_id` and only A's `ready` documents, and a `document_id` still limits both legs
- Given the query "what is the policy?" and a ready passage that contains "policy" and not "what", when retrieval runs, then that passage is a text hit
- Given a grounded answer, when the assistant message is saved, then each `SourceRef` is `document_id`, `filename`, `page`, and `chunk_index`, and the user message is the typed question
- Given the threshold decision in Boundaries, when retrieval runs, then a chunk that does not clear `RAG_SCORE_THRESHOLD` does not ground the answer
- Given these tests, when they run, then they use in-memory fakes and do not require Docker

## Implementation Notes

- Text match scrolls payload `text` under the same tenant and ready filter. A hit scores 1.0 only when every query word of four or more characters appears in the passage.
- Fusion is reciprocal rank. The chunk keeps the higher of its dense and text scores, and that score is compared with `RAG_SCORE_THRESHOLD`.
- Rewrite and rerank failures fall back without failing the ask. `cd apps/api && uv run --extra dev pytest`: 175 passed.
- That implementation was reverted. Text matches follow the distinctive-word rule in Boundaries. A passage does not have to contain words such as "what".
- Reimplemented with that rule. Text hits are fused before `top_k`. The rerank prompt says to copy the 0-based bracket indexes. `cd apps/api && uv run --extra dev pytest`: 177 passed.

## Spec Change Log

## Review Triage Log

- `medium` — `lexical_score` returns 1.0 only when every token of length 4 or more is in the passage. "what is the policy?" therefore requires the word "what", and a longer rewrite makes that match fail. `hybrid.py` lines 13–20 and 46–50.
- `low` — A text scroll reads every ready point in pages of 128, and a scroll error or a bad payload raises out of `search` after dense hits were already built (`qdrant_chunk_store.py` 109–179, 205–212). Everyday corpora are small, upsert always writes the citation fields, and a cap or a new fallback branch is more than a direct correction.
- `medium` — Lexical scores are only 0 or 1, then `hits[:top_k]` keeps an alphabetical slice (`qdrant_chunk_store.py` 178–179). Later full matches never reach fusion.
- `low` — Equal reciprocal-rank scores break ties by `document_id` (`hybrid.py` 42). With the default `top_k` of 5, a rank-1 text hit stays in the top two. The kept value is `hit.score`, not the rank weight.
- `medium` — Each leg is cut to `top_k` before `fuse_hits` (`qdrant_chunk_store.py` 131 and 179). A chunk just outside both tops cannot be promoted. A repeated key in one list would add rank twice; neither leg inserts the same point twice.
- `false` — A text hit is scored 1.0 and the use case drops scores below the configured `RAG_SCORE_THRESHOLD` (`retrieve_chunks.py` 75). The threshold still applies; a perfect token match is above 0.25 and 0.70.
- `medium` — `_rank_order` accepts only the exact 0-based permutation (`openai_chunk_reranker.py` 44–47). A 1-based reply raises, and `RetrieveChunks` keeps fused order, so rerank does not run. The prompt shows `[0]` labels and never says to copy them.
- `medium` — `_same_chunks` compares only `(document_id, chunk_index)` (`retrieve_chunks.py` 111–115). The shipped reranker returns the same objects, so text and page stay. A long rewrite is embedded as-is and then fails the all-token text match. Failures are swallowed with no log, which the spec requires for the ask. Rerank receives the retrieval query, which is the rewrite.
- `medium` — `test_ask_builds_rewrite_and_rerank_on_first_use` only calls `_clients()`. Dropping `rewriter` and `reranker` from `SessionBoundAskQuestion.execute` (`create_app.py` 193–200) would still pass. The in-memory fake stringifies non-string `text`; Qdrant skips it. That fake path is not an everyday point.
- `false` — A scrolled payload missing citation fields would raise in `_chunk_from_payload`. Upsert always writes `document_id`, `filename`, `page`, `chunk_index`, and `text`, so that payload is not produced.
- `false` — `int(True)` would cite page 1. Upsert stores `chunk.page` and `chunk.chunk_index` as ints, not booleans.
- `low` — If the text scroll raises, `search` raises and the dense list is discarded (`qdrant_chunk_store.py` 109–116). A scroll failure after a successful dense query is not an everyday path, and the fix adds a fallback branch.
- `low` — A rerank result that is not a sequence throws in `_same_chunks` outside the `except` (`retrieve_chunks.py` 84–90). `OpenAIChunkReranker` returns a list or raises, and the raise is already caught.
- `low` — A rerank result can keep the same ids and change `text`, `page`, or `score`. The shipped reranker reorders the original objects (`openai_chunk_reranker.py` 41). Closing that for every adapter adds a field-by-field guard.
- `low` — If embedding the rewritten query raises, the ask fails (`retrieve_chunks.py` 63–64). Embed errors already failed the ask before this story. The spec fallback covers rewrite and rerank, and this fix adds another branch.
- `low` — `InMemoryChunkStore` calls `str(point["text"])` (`fakes.py` 320). Production skips non-strings. The mismatch shows up only for a malformed fake point, and the fix adds a type guard.
- `medium` — Verification gap: production `execute` never has to pass the constructed rewriter and reranker into `RetrieveChunks`. Evidence filed by the verification-gap layer. Disposition there: patch.
- `medium` — Verification gap: no test asserts the reranker receives the rewritten query. Changing `_rerank(query, hits)` to `_rerank(question, hits)` stays green. Disposition there: patch.
- `medium` — Verification gap: a rerank return that does not raise, but is a different chunk set, is not pinned. Deleting the `_same_chunks` branch stays green. Disposition there: patch.
- `medium` — Verification gap: scroll fakes return a single page. Ignoring `next_offset` stays green, so matches past the first 128 ready points can disappear. Disposition there: patch.
- `medium` — Verification gap: no fixture separates `all(...)` from `any(...)`, or the four-character cutoff from a neighboring cutoff. Disposition there: patch.
- `medium` — Verification gap: no chunk is on both the dense list and the text list, so replacing rank addition with assignment stays green. Disposition there: patch.
- `carried low` — A text scroll still reads every ready point, and a scroll or payload error still leaves `search` after dense hits were built. Same claim as the prior low row. Not patched again.
- `carried low` — Equal fused weights still break ties by `document_id`. Same claim as the prior low row. Not patched again.
- `carried low` — `_same_chunks` still compares only document id and chunk index. The shipped reranker still returns the original objects. Same claim as the prior low row. Not patched again.
- `carried low` — Embedding the rewritten query still sits outside the rewrite fallback. Same claim as the prior low row. Not patched again.
- `carried false` — `int()` would accept a boolean page. Upsert still stores ints, so that payload is not produced. Same claim as the prior false row.
- `carried low` — The in-memory dense leg still stringifies a non-string `text`. Same claim as the prior low row. Not patched again.
- `low` — Lexical hits are all scored 1.0 and sorted by document id before fusion, so a later id can lose `top_k` when many passages match. Equal text hits have no better score; replacing that order adds a new ranking rule.
- `low` — `_rank_order` still requires a full 0-based permutation. The prompt now says to copy the bracket indexes that start at 0. A reply that does not is a rerank failure, and the spec keeps fused order.
- `low` — The rewrite prompt does not guarantee the word "policy" survives. It asks for a short query of distinctive words. An embed error on that text still fails the ask, which is the carried case above.
- `low` — Chunk text is in the same rerank message the parser reads. A passage can nudge the order. Separating that text is more than a direct correction.
- `false` — Dense hits are limited to `top_k` before fusion. A text match outside that window is still added, because the text leg is not cut before `fuse_hits`.
- `low` — A scroll offset that cycles would not stop. Qdrant returns a forward offset or none on this client. A seen-set is an extra guard.
- `low` — A negative `top_k` would slice from the end. The setting is a positive count, default 5.
- `medium` — `query_words` uses `[a-z0-9]+`, so an accented word such as "política" is split and the text leg misses it. `hybrid.py` word pattern.
- `medium` — Verification gap: no capitalized passage is asserted. Deleting `.lower()` stays green. Disposition there: patch.
- `medium` — Verification gap: no longer token such as "policymaking" is asserted to miss the word "policy". A substring check stays green. Disposition there: patch.
- `medium` — Verification gap: two text-only hits in reverse id order are not asserted, so deleting the document-id sort stays green. Disposition there: patch.

## Design Notes

Existing points stay as one cosine vector. A sparse or named vector would mean re-embedding, which this epic does not do. The text leg reads payload `text` under the same filter as the dense leg. Fuse the two lists, then apply `top_k`. Do not keep an alphabetical slice of text hits before fusion. The rerank prompt tells the model to copy the bracket indexes, which start at 0. Tests also cover a second scroll page, a chunk found by both legs, the reranker receiving the rewritten query, a different rerank set keeping fused order, and `SessionBoundAskQuestion.execute` passing the wired adapters. `AskQuestion` still treats an empty list as the refusal.

## Verification

**Commands:**
- `cd apps/api && uv run --extra dev pytest` -- expected: existing tests pass, and the new retrieval tests pass without Docker

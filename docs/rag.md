# RAG

PDF -> extraction -> page-aware chunks -> embeddings -> Qdrant -> filtered retrieval
-> context assembly -> LLM -> answer + sources

Qdrant payload must include `tenant_id`, `document_id`, `filename`, `page`,
`chunk_index`. Cross-tenant retrieval is prohibited.

Later stages: hybrid retrieval, reranking, query rewriting, and context evaluation.

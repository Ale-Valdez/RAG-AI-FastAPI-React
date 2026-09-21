# HTTP JSON envelope

Product routes under `/api/v1` always use this envelope. HTTP status still carries 401 / 403 / 404 / 409. This is AD-10's JSON body.

## Success

```json
{
  "data": {},
  "error": null
}
```

`data` is a JSON object (resource or a nested collection). It is never a top-level array. Per-endpoint fields inside `data` are named by the owning slice.

## Failure

```json
{
  "data": null,
  "error": {
    "code": "DOCUMENT_NOT_FOUND",
    "message": "Document not found"
  }
}
```

`error.code` is a stable uppercase snake_case machine code. `error.message` is the human string. `DOCUMENT_NOT_FOUND` is the not-found example; slices add codes as they land. The web client must not invent codes the API did not return.

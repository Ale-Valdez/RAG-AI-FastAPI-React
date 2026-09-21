# Domain model

Tenant -> User -> Conversation -> Message
Tenant -> Document

Document lifecycle:

```text
PENDING -> PROCESSING -> READY
                    \-> FAILED
```

Users authenticate and belong to a tenant. Tenant users upload PDFs. Documents
process asynchronously. Users ask questions over permitted documents. Answers
include source and page references. Conversations persist.

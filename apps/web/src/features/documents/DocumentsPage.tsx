import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, apiErrorMessage } from "../../api/client";
import { EmptyState, ErrorState, LoadingState } from "../../shared/states";
import {
  deleteDocument,
  listDocuments,
  reingestDocument,
  uploadDocument,
  type LibraryDocument,
} from "./api";

const POLL_MS = 3000;

function isActive(status: string): boolean {
  return status === "pending" || status === "processing";
}

function canReingest(status: string): boolean {
  return status === "ready" || status === "failed";
}

export default function DocumentsPage() {
  const fileInput = useRef<HTMLInputElement>(null);
  const documentsRef = useRef<LibraryDocument[] | null>(null);
  const [documents, setDocuments] = useState<LibraryDocument[] | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actingId, setActingId] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timer = 0;

    const load = async () => {
      try {
        const rows = await listDocuments();
        if (cancelled) return;
        documentsRef.current = rows;
        setDocuments(rows);
        setLoadError(null);
        if (rows.some((row) => isActive(row.status))) {
          timer = window.setTimeout(() => {
            void load();
          }, POLL_MS);
        }
      } catch (reason: unknown) {
        if (cancelled) return;
        if (reason instanceof ApiError && reason.status === 401) return;
        setLoadError(apiErrorMessage(reason));
        if (documentsRef.current?.some((row) => isActive(row.status))) {
          timer = window.setTimeout(() => {
            void load();
          }, POLL_MS);
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [revision]);

  async function onUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || actingId) return;
    setActionError(null);
    setActingId("upload");
    try {
      const created = await uploadDocument(file);
      const next = [
        created,
        ...(documentsRef.current ?? []).filter((row) => row.id !== created.id),
      ];
      documentsRef.current = next;
      setDocuments(next);
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
      setRevision((value) => value + 1);
    } catch (reason: unknown) {
      if (reason instanceof ApiError && reason.status === 401) return;
      setActionError(apiErrorMessage(reason));
    } finally {
      setActingId(null);
    }
  }

  async function onDelete(document: LibraryDocument) {
    if (actingId) return;
    if (!window.confirm(`Delete ${document.filename}?`)) return;
    setActionError(null);
    setActingId(document.id);
    try {
      await deleteDocument(document.id);
      const next = (documentsRef.current ?? []).filter((row) => row.id !== document.id);
      documentsRef.current = next;
      setDocuments(next);
      setRevision((value) => value + 1);
    } catch (reason: unknown) {
      if (reason instanceof ApiError && reason.status === 401) return;
      setActionError(apiErrorMessage(reason));
    } finally {
      setActingId(null);
    }
  }

  async function onReingest(document: LibraryDocument) {
    if (actingId || !canReingest(document.status)) return;
    setActionError(null);
    setActingId(document.id);
    try {
      const updated = await reingestDocument(document.id);
      const next = (documentsRef.current ?? []).map((row) =>
        row.id === updated.id ? updated : row,
      );
      documentsRef.current = next;
      setDocuments(next);
      setRevision((value) => value + 1);
    } catch (reason: unknown) {
      if (reason instanceof ApiError && reason.status === 401) return;
      setActionError(apiErrorMessage(reason));
    } finally {
      setActingId(null);
    }
  }

  const busy = actingId !== null;

  return (
    <section className="panel">
      <h2>Documents</h2>
      <form className="form" onSubmit={onUpload}>
        <label>
          PDF
          <input
            ref={fileInput}
            type="file"
            accept=".pdf,application/pdf"
            disabled={busy}
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <button type="submit" disabled={busy || !file}>
          Upload
        </button>
      </form>
      {actionError ? <p className="error">{actionError}</p> : null}
      {documents === null && !loadError ? <LoadingState label="Loading documents…" /> : null}
      {documents === null && loadError ? <ErrorState message={loadError} /> : null}
      {documents && loadError ? <p className="error">{loadError}</p> : null}
      {documents && documents.length === 0 ? (
        <EmptyState
          title="No documents yet"
          detail="Upload a PDF. Files stay in this tenant's library."
        />
      ) : null}
      {documents && documents.length > 0 ? (
        <ul className="library">
            {documents.map((document) => (
              <li key={document.id}>
                <span className="name">{document.filename}</span>
                <span className={`status status-${document.status}`}>{document.status}</span>
                <span className="row-actions">
                  {canReingest(document.status) ? (
                    <button
                      type="button"
                      className="secondary"
                      disabled={busy}
                      onClick={() => void onReingest(document)}
                    >
                      Reingest
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="secondary"
                    disabled={busy}
                    onClick={() => void onDelete(document)}
                  >
                    Delete
                  </button>
                </span>
              </li>
            ))}
        </ul>
      ) : null}
    </section>
  );
}

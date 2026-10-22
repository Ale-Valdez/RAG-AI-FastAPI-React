import { useEffect, useRef, useState } from "react";
import { ApiError, apiErrorMessage } from "../../api/client";
import {
  deleteDocument,
  listDocuments,
  reingestDocument,
  uploadDocument,
  type LibraryDocument,
} from "./api";
import { canReingest, isActive } from "./documentStatus";

const POLL_MS = 3000;

export function useDocumentLibrary() {
  const documentsRef = useRef<LibraryDocument[] | null>(null);
  const inFlight = useRef(false);
  const generation = useRef(0);
  const [documents, setDocuments] = useState<LibraryDocument[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actingId, setActingId] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const generationAtStart = generation.current;
    let cancelled = false;
    let timer = 0;

    const isCurrent = () => !cancelled && generationAtStart === generation.current;

    const load = async () => {
      try {
        const rows = await listDocuments();
        if (!isCurrent()) return;
        documentsRef.current = rows;
        setDocuments(rows);
        setLoadError(null);
        if (rows.some((row) => isActive(row.status))) {
          timer = window.setTimeout(() => {
            void load();
          }, POLL_MS);
        }
      } catch (reason: unknown) {
        if (!isCurrent()) return;
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

  function replaceDocuments(next: LibraryDocument[]) {
    generation.current += 1;
    documentsRef.current = next;
    setDocuments(next);
    setRevision((value) => value + 1);
  }

  async function run(id: string, action: () => Promise<void>): Promise<boolean> {
    if (inFlight.current) return false;
    inFlight.current = true;
    setActionError(null);
    setActingId(id);
    try {
      await action();
      return true;
    } catch (reason: unknown) {
      if (reason instanceof ApiError && reason.status === 401) return false;
      setActionError(apiErrorMessage(reason));
      return false;
    } finally {
      inFlight.current = false;
      setActingId(null);
    }
  }

  function upload(file: File): Promise<boolean> {
    return run("upload", async () => {
      const created = await uploadDocument(file);
      const next = [
        created,
        ...(documentsRef.current ?? []).filter((row) => row.id !== created.id),
      ];
      replaceDocuments(next);
    });
  }

  function reingest(document: LibraryDocument): Promise<boolean> {
    if (inFlight.current || !canReingest(document.status)) return Promise.resolve(false);
    return run(document.id, async () => {
      const updated = await reingestDocument(document.id);
      const next = (documentsRef.current ?? []).map((row) =>
        row.id === updated.id ? updated : row,
      );
      replaceDocuments(next);
    });
  }

  function remove(document: LibraryDocument): Promise<boolean> {
    if (inFlight.current) return Promise.resolve(false);
    if (!window.confirm(`Delete ${document.filename}?`)) return Promise.resolve(false);
    return run(document.id, async () => {
      await deleteDocument(document.id);
      const next = (documentsRef.current ?? []).filter((row) => row.id !== document.id);
      replaceDocuments(next);
    });
  }

  return {
    documents,
    loadError,
    actionError,
    busy: actingId !== null,
    upload,
    reingest,
    remove,
  };
}

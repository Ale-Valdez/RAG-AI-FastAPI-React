import { useEffect, useRef, useState } from "react";
import { apiErrorMessage } from "../../../api/client";
import { ErrorState, LoadingState } from "../../../shared/states";
import { getDocumentFile } from "../api";

export type ActiveSource = {
  documentId: string;
  filename: string;
  page: number;
};

/** Stored pages are 0-based. The label matches a PDF viewer's 1-based page. */
export function sourcePageLabel(page: number): number {
  return page + 1;
}

export default function SourcePanel({
  source,
  onClose,
}: {
  source: ActiveSource;
  onClose: () => void;
}) {
  const [pdf, setPdf] = useState<Blob | null>(null);
  const [loadedId, setLoadedId] = useState<string | null>(null);
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const pageLabel = sourcePageLabel(source.page);
  const matchesDocument = loadedId === source.documentId;
  const visibleError = matchesDocument ? error : null;
  const visibleUrl = matchesDocument && error === null ? fileUrl : null;

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setPdf(null);
    setLoadedId(null);
    const documentId = source.documentId;
    getDocumentFile(documentId)
      .then((blob) => {
        if (cancelled) return;
        setPdf(blob);
        setLoadedId(documentId);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setError(apiErrorMessage(reason));
        setLoadedId(documentId);
      });
    return () => {
      cancelled = true;
    };
  }, [source.documentId]);

  useEffect(() => {
    const narrow = window.matchMedia("(max-width: 1023px)").matches;
    if (narrow) closeRef.current?.focus();
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  useEffect(() => {
    if (!pdf || loadedId !== source.documentId) {
      setFileUrl(null);
      return;
    }
    const objectUrl = URL.createObjectURL(pdf);
    setFileUrl(objectUrl);
    return () => {
      URL.revokeObjectURL(objectUrl);
    };
  }, [pdf, loadedId, source.documentId, source.page]);

  return (
    <aside
      id="source-panel"
      aria-label="Source"
      className="card flex h-full min-h-0 min-w-0 flex-col overflow-hidden"
    >
      <div className="mb-3 flex shrink-0 items-center justify-between gap-2">
        <p className="m-0 flex min-w-0 flex-1 items-baseline gap-2">
          <span className="truncate font-medium text-gray-900" title={source.filename}>
            {source.filename}
          </span>
          <span className="shrink-0 font-normal text-gray-500">p. {pageLabel}</span>
        </p>
        <button
          ref={closeRef}
          type="button"
          aria-label="Hide source"
          onClick={onClose}
          className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-gray-200 bg-white text-gray-600 shadow-sm transition hover:border-blue-300 hover:text-blue-700"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="size-4"
            aria-hidden="true"
          >
            <path strokeLinecap="round" d="M6 6l12 12M18 6 6 18" />
          </svg>
        </button>
      </div>
      {visibleError === null && visibleUrl === null ? (
        <LoadingState label="Loading source…" />
      ) : null}
      {visibleError !== null ? <ErrorState message={visibleError} /> : null}
      {visibleUrl !== null ? (
        <iframe
          title={`${source.filename}, page ${pageLabel}`}
          src={`${visibleUrl}#page=${pageLabel}&view=FitH`}
          className="mt-3 min-h-0 w-full flex-1 border-0"
        />
      ) : null}
    </aside>
  );
}

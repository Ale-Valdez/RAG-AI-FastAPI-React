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
  return (
    <aside
      id="source-panel"
      className="card flex h-full max-h-48 min-h-0 min-w-0 flex-col overflow-hidden lg:max-h-none"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="m-0 text-lg font-bold">Source</h2>
        <button
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
      <p className="m-0 truncate font-medium text-gray-900" title={source.filename}>
        {source.filename}
      </p>
      <p className="m-0 mt-1 text-sm text-gray-500">Page {sourcePageLabel(source.page)}</p>
    </aside>
  );
}

import type { LibraryDocument } from "../api";
import { canReingest } from "../documentStatus";

type DocumentsTableProps = {
  documents: LibraryDocument[];
  busy: boolean;
  onReingest: (document: LibraryDocument) => void;
  onDelete: (document: LibraryDocument) => void;
};

type StatusInfo = {
  title: string;
  color: string;
};

function StatusIcon({ status }: { status: LibraryDocument["status"] }) {
   const statusInfo: Record<LibraryDocument["status"], StatusInfo> = {
    "pending": {
        title: "Pending",
        color: "yellow-400",
    },
    "processing": {
        title: "Processing",
        color: "blue-400",
    },
    "ready": {
        title: "Ready",
        color: "green-500",
    },
    "failed": {
        title: "Failed",
        color: "red-500",
    },
   };
  return (
    <span title={statusInfo[status]?.title} className="inline-flex items-center gap-1">
      <span className={`w-4 h-4 rounded-full bg-${statusInfo[status]?.color} inline-block`} />
      <span className="sr-only">{statusInfo[status]?.title}</span>
    </span>
  );
}

export default function DocumentsTableComponent({
  documents,
  busy,
  onReingest,
  onDelete,
}: DocumentsTableProps) {
  return (
   
    <table className="table-auto w-full border-separate border-spacing-2 border border-gray-200 rounded-md p-2">
        <thead>
            <tr>
                <th>Name</th>
                <th>Status</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody className="border-spacing-2">
            {documents.map((document) => (
                <tr key={document.id} className="hover:bg-gray-100 dark:hover:bg-gray-800 hover:cursor-pointer hover:
             transition-colors duration-200 hover:text-gray-50 dark:hover:text-gray-50">
                    <td className="border border-x-0 border-gray-200 dark:border-gray-200  p-2">{document.filename}</td>
                    <td className="status status-icon text-center border border-x-0 border-gray-200 dark:border-gray-200 p-2">
                      <StatusIcon status={document.status} />
                    </td>
               
                    <td className="flex gap-2 border border-x-0 border-gray-200 dark:border-gray-200  p-2">
                        {canReingest(document.status) ? (
                            <button
                                type="button"
                                className="icon-button secondary border-none"
                                disabled={busy}
                                title="Reingest"
                                onClick={() => void onReingest(document)}
                            >
                                <span role="img" aria-label="Reingest">🔄</span>
                            </button>
                        ) : null}
                        <button
                            type="button"
                            className="icon-button secondary border-none"
                            disabled={busy}
                            title="Delete"
                            onClick={() => void onDelete(document)}
                        >
                            <span role="img" aria-label="Delete">🗑️</span>
                        </button>
                    </td>
               
                </tr>
            ))}
        </tbody>
    </table>

  );
}

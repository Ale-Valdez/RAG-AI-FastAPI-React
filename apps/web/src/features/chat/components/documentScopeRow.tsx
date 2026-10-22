import type { LibraryDocument } from "../../documents/api";

type DocumentScopeRowProps = {
  documents: LibraryDocument[];
  value: string;
  disabled: boolean;
  onChange: (documentId: string) => void;
};

export default function DocumentScopeRow({
  documents,
  value,
  disabled,
  onChange,
}: DocumentScopeRowProps) {
  return (
    <div className="flex flex-col gap-2">
      <span className="text-sm font-medium text-gray-700">Document</span>
      <div className="flex flex-nowrap gap-2 overflow-x-auto pb-1" role="group" aria-label="Document">
        <ScopeBox
          label="All ready documents"
          selected={value === ""}
          disabled={disabled}
          onSelect={() => onChange("")}
        />
        {documents.map((item) => (
          <ScopeBox
            key={item.id}
            label={item.filename}
            selected={value === item.id}
            disabled={disabled}
            onSelect={() => onChange(item.id)}
          />
        ))}
      </div>
    </div>
  );
}

function ScopeBox({
  label,
  selected,
  disabled,
  onSelect,
}: {
  label: string;
  selected: boolean;
  disabled: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      disabled={disabled}
      onClick={onSelect}
      className={`shrink-0 rounded-full border px-3 py-1 text-sm shadow-sm transition ${
        selected
          ? "border-blue-500 bg-blue-50 text-blue-700"
          : "border-gray-200 bg-white text-gray-700 hover:border-blue-300"
      }`}
    >
      {label}
    </button>
  );
}

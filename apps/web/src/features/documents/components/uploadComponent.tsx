import { useRef, useState, type FormEvent } from "react";

type UploadComponentProps = {
  busy: boolean;
  onUpload: (file: File) => Promise<boolean>;
};

export default function UploadComponent({ busy, onUpload }: UploadComponentProps) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || busy) return;
    const accepted = await onUpload(file);
    if (!accepted) return;
    setFile(null);
    if (fileInput.current) fileInput.current.value = "";
  }

  return (
    <form className="form" onSubmit={(event) => void onSubmit(event)}>
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
  );
}

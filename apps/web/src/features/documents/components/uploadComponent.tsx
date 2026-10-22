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
        <form className="w-full flex flex-col sm:flex-row items-center justify-center gap-3 px-4 py-4" onSubmit={(event) => void onSubmit(event)}>
            <label className="relative flex-1 cursor-pointer">
                <input
                    className="peer absolute inset-0 w-full h-full opacity-0 cursor-pointer z-20"
                    ref={fileInput}
                    type="file"
                    accept=".pdf,application/pdf"
                    disabled={busy}
                    onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                />
                <div className="w-full flex items-center gap-2 border border-gray-300 dark:border-gray-300 rounded-[25px] py-2 px-4 bg-white shadow-sm transition ring-1 ring-transparent peer-focus:ring-blue-400 peer-hover:border-blue-300">
                    <span className="material-symbols-outlined text-blue-500 text-xl">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="size-6">
                            <path strokeLinecap="round" strokeLinejoin="round" d="m18.375 12.739-7.693 7.693a4.5 4.5 0 0 1-6.364-6.364l10.94-10.94A3 3 0 1 1 19.5 7.372L8.552 18.32m.009-.01-.01.01m5.699-9.941-7.81 7.81a1.5 1.5 0 0 0 2.112 2.13" />
                        </svg>
                    </span>
                    <span className={`flex-1 truncate text-gray-600 ${file ? 'opacity-100' : 'opacity-50'}`}>
                        {file ? file.name : "Select a PDF file to upload"}
                    </span>
                    {file && (
                        <button
                            type="button"
                            tabIndex={-1}
                            className="text-gray-400 hover:text-red-500 transition p-1 rounded-full z-30"
                            onClick={() => {
                                setFile(null);
                                if (fileInput.current) fileInput.current.value = "";
                            }}
                            aria-label="Remove selected file"
                            disabled={busy}
                        >
                            <span className="material-symbols-outlined text-base"><svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="size-6">
                                <path strokeLinecap="round" strokeLinejoin="round" d="m9.75 9.75 4.5 4.5m0-4.5-4.5 4.5M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                            </svg>
                            </span>
                        </button>
                    )}
                </div>
            </label>
            <button
                type="submit"
                className="ml-0 sm:ml-3 mt-2 sm:mt-0 px-5 py-2 rounded-[25px] bg-blue-500 hover:bg-blue-600 text-white font-semibold text-base shadow transition disabled:bg-gray-300 disabled:cursor-not-allowed"
                disabled={busy || !file}
            >
                Upload
            </button>
        </form>
    );
}

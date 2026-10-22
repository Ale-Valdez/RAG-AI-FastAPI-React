import { useLayoutEffect, useRef, type FormEvent, type KeyboardEvent } from "react";

type ComposerProps = {
  question: string;
  disabled: boolean;
  sendDisabled: boolean;
  onQuestionChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

export default function Composer({
  question,
  disabled,
  sendDisabled,
  onQuestionChange,
  onSubmit,
}: ComposerProps) {
  const field = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    const element = field.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 128)}px`;
  }, [question]);

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    event.currentTarget.form?.requestSubmit();
  }

  return (
    <form
      className="sticky bottom-0 z-10 mt-3 shrink-0 flex items-end gap-2 rounded-full border border-gray-200 bg-white py-1.5 pr-1.5 pl-4 shadow-md focus-within:ring-2 focus-within:ring-blue-400"
      onSubmit={onSubmit}
    >
      <textarea
        ref={field}
        aria-label="Question"
        placeholder="Ask anything"
        rows={1}
        className="max-h-32 min-h-10 flex-1 resize-none border-0 bg-transparent px-0 py-2 shadow-none outline-none placeholder:text-gray-400"
        value={question}
        disabled={disabled}
        onChange={(event) => onQuestionChange(event.target.value)}
        onKeyDown={onKeyDown}
      />
      <button
        type="submit"
        aria-label="Send"
        className="mb-0.5 flex size-10 shrink-0 items-center justify-center rounded-full bg-blue-500 p-0 text-white shadow transition hover:bg-blue-600 disabled:cursor-not-allowed disabled:bg-gray-300 disabled:opacity-100"
        disabled={sendDisabled}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className="size-5"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 19V5" />
          <path strokeLinecap="round" strokeLinejoin="round" d="m6 11 6-6 6 6" />
        </svg>
      </button>
    </form>
  );
}

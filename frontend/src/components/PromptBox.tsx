"use client";

import { useRef, useState } from "react";
import { ACCEPTED_EXTENSIONS } from "@/lib/files";

type Props = {
  onFiles: (files: FileList) => void;
  onSend: (text: string) => void;
};

/** The bar along the bottom: attach a file, or type a question. */
export default function PromptBox({ onFiles, onSend }: Props) {
  const [text, setText] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);

  function grow() {
    const el = textarea.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }

  function send() {
    const trimmed = text.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setText("");
    if (textarea.current) textarea.current.style.height = "auto";
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-5 pt-2">
      <div
        className="flex items-end gap-2 rounded-3xl border border-border bg-surface
          px-3 py-2.5 focus-within:border-accent"
      >
        <input
          ref={fileInput}
          type="file"
          accept={ACCEPTED_EXTENSIONS}
          multiple
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) onFiles(e.target.files);
            e.target.value = "";
          }}
        />

        <button
          onClick={() => fileInput.current?.click()}
          aria-label="Attach an Excel sheet or a voice note"
          title="Attach an Excel sheet or a voice note"
          className="shrink-0 rounded-full p-2.5 text-muted hover:bg-surface-2 hover:text-text"
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M21.44 11.05l-8.49 8.49a5.5 5.5 0 01-7.78-7.78l8.49-8.49a3.67 3.67 0 115.18 5.18l-8.49 8.49a1.83 1.83 0 11-2.59-2.59l7.78-7.78"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>

        <textarea
          ref={textarea}
          rows={1}
          value={text}
          placeholder="Ask something, or drop an Excel sheet or voice note"
          onChange={(e) => {
            setText(e.target.value);
            grow();
          }}
          onKeyDown={(e) => {
            // Enter sends. Shift+Enter starts a new line.
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          className="max-h-[200px] flex-1 resize-none bg-transparent py-2.5 text-[17px]
            leading-6 outline-none placeholder:text-muted"
        />

        <button
          onClick={send}
          disabled={!text.trim()}
          aria-label="Send"
          className="shrink-0 rounded-full bg-accent p-2.5 text-accent-fg
            disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-muted"
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M12 19V5M5 12l7-7 7 7"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </div>

      <p className="pt-2.5 text-center text-xs text-muted">
        Mock data only. Always check important details before acting on them.
      </p>
    </div>
  );
}

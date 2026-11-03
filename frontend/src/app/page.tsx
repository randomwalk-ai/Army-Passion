"use client";

import { useRef, useState } from "react";
import Conversation, { type Entry } from "@/components/Conversation";
import PromptBox from "@/components/PromptBox";
import Sidebar from "@/components/Sidebar";
import { uploadSheet } from "@/lib/api";
import { classify } from "@/lib/files";

export default function Home() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [dragging, setDragging] = useState(false);

  // Drag events fire for every child element, so count them instead of
  // toggling a flag — otherwise the overlay flickers as the pointer moves.
  const dragDepth = useRef(0);

  function update(id: string, changes: Partial<Extract<Entry, { kind: "file" }>>) {
    setEntries((prev) =>
      prev.map((entry) =>
        entry.id === id && entry.kind === "file" ? { ...entry, ...changes } : entry,
      ),
    );
  }

  function addFiles(files: FileList) {
    for (const file of Array.from(files)) {
      const id = crypto.randomUUID();
      const fileKind = classify(file);

      setEntries((prev) => [
        ...prev,
        {
          id,
          kind: "file",
          name: file.name,
          size: file.size,
          fileKind,
          state: fileKind === "excel" ? "reading" : undefined,
          // Audio and documents are uploaded by their own components, which need the file.
          file: fileKind === "audio" || fileKind === "document" ? file : undefined,
        },
      ]);

      if (fileKind === "excel") {
        uploadSheet(file)
          .then((upload) => update(id, { state: "ready", upload }))
          .catch((error: unknown) =>
            update(id, {
              state: "failed",
              error:
                error instanceof Error
                  ? error.message
                  : "I could not reach the server. Is the backend running?",
            }),
          );
      }
    }
  }


  function addText(text: string) {
    setEntries((prev) => [...prev, { id: crypto.randomUUID(), kind: "text", text }]);
  }

  return (
    <div className="flex h-dvh overflow-hidden bg-bg">
      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewChat={() => {
          setEntries([]);
          setSidebarOpen(false);
        }}
      />

      <main
        className="relative flex min-w-0 flex-1 flex-col"
        onDragEnter={(e) => {
          e.preventDefault();
          dragDepth.current += 1;
          if (e.dataTransfer.types.includes("Files")) setDragging(true);
        }}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={(e) => {
          e.preventDefault();
          dragDepth.current -= 1;
          if (dragDepth.current <= 0) setDragging(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          dragDepth.current = 0;
          setDragging(false);
          if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files);
        }}
      >
        <header className="flex h-14 shrink-0 items-center gap-2 px-3 md:px-5">
          <button
            onClick={() => setSidebarOpen(true)}
            aria-label="Open menu"
            className="rounded-lg p-2 text-muted hover:bg-surface-2 hover:text-text md:hidden"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="M4 7h16M4 12h16M4 17h16"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </button>
          <span className="text-base font-medium text-muted md:hidden">Army Passion</span>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto">
          <Conversation
            entries={entries}
            onMappingConfirmed={(id) => update(id, { mappingConfirmed: true })}
          />
        </div>

        <PromptBox onFiles={addFiles} onSend={addText} />

        {dragging && (
          <div className="pointer-events-none absolute inset-3 z-20 flex items-center justify-center">
            <div
              className="flex h-full w-full items-center justify-center rounded-3xl border-2
                border-dashed border-accent bg-accent-soft/90"
            >
              <p className="text-xl font-medium text-text">
                Drop the file here
              </p>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

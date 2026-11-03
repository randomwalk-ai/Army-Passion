"use client";

import ColumnMapping from "@/components/ColumnMapping";
import DocumentUpload from "@/components/DocumentUpload";
import ImportPreview from "@/components/ImportPreview";
import VoiceNote from "@/components/VoiceNote";
import type { UploadResult } from "@/lib/api";
import { CURRENT_USER } from "@/lib/currentUser";
import { formatSize, type DroppedKind } from "@/lib/files";

export type Entry =
  | { id: string; kind: "text"; text: string }
  | {
      id: string;
      kind: "file";
      name: string;
      size: number;
      fileKind: DroppedKind;
      /** Only Excel files go to the server; this tracks how that went. */
      state?: "reading" | "ready" | "failed";
      error?: string;
      upload?: UploadResult;
      mappingConfirmed?: boolean;
      /** Kept for audio and documents, which their own components upload. */
      file?: File;
    };

type Props = {
  entries: Entry[];
  onMappingConfirmed: (entryId: string) => void;
};

/** What the colonel is told when a file lands. Step 1 only announces it;
 *  the real reading of the file comes in the next steps. */
const NEXT_STEP: Record<DroppedKind, { title: string; detail: string }> = {
  excel: {
    title: "Excel sheet received",
    detail:
      "Next: I will read the columns, show you what each one means, and then a summary of what will change. Nothing is saved until you confirm.",
  },
  audio: {
    title: "Voice note received",
    detail:
      "Next: you choose which family this is about — or say it is a new family — and then I will write out what was said.",
  },
  document: {
    title: "Document received",
    detail: "Next: choose the family, and who in it the document belongs to.",
  },
  unsupported: {
    title: "I cannot read this file",
    detail:
      "I can take Excel sheets (.xlsx, .xls, .csv), voice notes (.mp3, .m4a, .wav), and documents (.pdf, .jpg, .png).",
  },
};

function FileIcon({ kind }: { kind: DroppedKind }) {
  if (kind === "audio") {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M12 3v18M7 8v8M17 8v8M3 11v2M21 11v2"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  if (kind === "document") {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M7 3.5h7l4 4V20a.5.5 0 0 1-.5.5h-10A.5.5 0 0 1 7 20V3.5z"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinejoin="round"
        />
        <path d="M14 3.5V8h4M9.5 12.5h5M9.5 16h5" stroke="currentColor" strokeWidth="1.8" />
      </svg>
    );
  }
  if (kind === "excel") {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect
          x="3.5"
          y="4"
          width="17"
          height="16"
          rx="2"
          stroke="currentColor"
          strokeWidth="1.8"
        />
        <path d="M3.5 9.5h17M9.5 9.5V20M3.5 15h17" stroke="currentColor" strokeWidth="1.8" />
      </svg>
    );
  }
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8" />
      <path d="M12 7.5v5.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <circle cx="12" cy="16.5" r="1.1" fill="currentColor" />
    </svg>
  );
}

function EmptyState() {
  const suggestions = [
    {
      title: "Upload an Excel sheet",
      body: "Drop the widows sheet here. I will show you what changes before anything is saved.",
    },
    {
      title: "Upload a voice note",
      body: "Drop a recording of a call. I will write out what was said and attach it to the family.",
    },
  ];

  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col justify-center px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
        Good to see you, {CURRENT_USER.name.split(" ")[0]}
      </h1>
      <p className="mt-3 text-lg text-muted">What would you like to do today?</p>

      <div className="mt-8 grid gap-3 sm:grid-cols-2">
        {suggestions.map((s) => (
          <div key={s.title} className="rounded-2xl border border-border bg-surface p-5">
            <h2 className="text-base font-semibold">{s.title}</h2>
            <p className="mt-1.5 text-[15px] leading-relaxed text-muted">{s.body}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

/** What the system says back about a file, once it knows. */
function FileReply({
  entry,
  onMappingConfirmed,
}: {
  entry: Extract<Entry, { kind: "file" }>;
  onMappingConfirmed: (entryId: string) => void;
}) {
  if (entry.fileKind === "audio" && entry.file) {
    return <VoiceNote file={entry.file} />;
  }

  if (entry.fileKind === "document" && entry.file) {
    return <DocumentUpload file={entry.file} />;
  }

  if (entry.fileKind === "excel") {
    if (entry.state === "reading") {
      return <p className="text-[17px] text-muted">Reading the sheet...</p>;
    }
    if (entry.state === "failed") {
      return (
        <div>
          <p className="text-[17px] font-medium text-danger">
            I could not read that sheet
          </p>
          <p className="mt-1 text-[17px] leading-relaxed text-muted">{entry.error}</p>
        </div>
      );
    }
    if (entry.upload) {
      if (entry.mappingConfirmed) {
        return <ImportPreview importId={entry.upload.import_id} />;
      }
      return (
        <ColumnMapping
          result={entry.upload}
          onConfirmed={() => onMappingConfirmed(entry.id)}
        />
      );
    }
  }

  const step = NEXT_STEP[entry.fileKind];
  return (
    <div>
      <p className="text-[17px] font-medium">{step.title}</p>
      <p className="mt-1 text-[17px] leading-relaxed text-muted">{step.detail}</p>
    </div>
  );
}

export default function Conversation({ entries, onMappingConfirmed }: Props) {
  if (entries.length === 0) return <EmptyState />;

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-8">
      {entries.map((entry) =>
        entry.kind === "text" ? (
          <div key={entry.id} className="flex justify-end">
            <p
              className="max-w-[85%] whitespace-pre-wrap rounded-3xl bg-surface-2 px-5 py-3
                text-[17px] leading-relaxed"
            >
              {entry.text}
            </p>
          </div>
        ) : (
          <div key={entry.id} className="space-y-3">
            <div className="flex justify-end">
              <div
                className="flex max-w-[85%] items-center gap-3 rounded-2xl border border-border
                  bg-surface px-4 py-3"
              >
                <span
                  className={
                    entry.fileKind === "unsupported" ? "text-danger" : "text-accent"
                  }
                >
                  <FileIcon kind={entry.fileKind} />
                </span>
                <div className="min-w-0">
                  <p className="truncate text-[15px] font-medium">{entry.name}</p>
                  <p className="text-xs text-muted">{formatSize(entry.size)}</p>
                </div>
              </div>
            </div>

            <div className="max-w-full">
              <FileReply entry={entry} onMappingConfirmed={onMappingConfirmed} />
            </div>
          </div>
        ),
      )}
    </div>
  );
}

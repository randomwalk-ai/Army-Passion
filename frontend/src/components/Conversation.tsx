"use client";

import ColumnMapping from "@/components/ColumnMapping";
import DocumentUpload from "@/components/DocumentUpload";
import ImportPreview from "@/components/ImportPreview";
import VoiceNote from "@/components/VoiceNote";
import { useEffect, useState } from "react";
import {
  exportAnswerExcel,
  getSuggestions,
  type AskAnswer,
  type SuggestionCard,
  type UploadResult,
} from "@/lib/api";
import { CURRENT_USER } from "@/lib/currentUser";
import { formatSize, type DroppedKind } from "@/lib/files";

export type Entry =
  | { id: string; kind: "text"; text: string }
  | {
      id: string;
      kind: "answer";
      state: "thinking" | "ready" | "failed";
      answer?: AskAnswer;
      error?: string;
    }
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
  onSuggestion: (suggestion: SuggestionCard) => void;
  /** A clarifying option, a follow-up chip, or a clicked family row — ask it
   *  as the next question, the same as if he had typed it. */
  onAsk: (question: string) => void;
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

/** Today's suggested questions, worked out from the data by the backend. */
function EmptyState({ onSuggestion }: { onSuggestion: (s: SuggestionCard) => void }) {
  const [cards, setCards] = useState<SuggestionCard[] | null>(null);

  useEffect(() => {
    getSuggestions()
      .then(setCards)
      // No suggestions is not worth an error; he can still type a question.
      .catch(() => setCards([]));
  }, []);

  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col justify-center px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
        Good to see you, {CURRENT_USER.name.split(" ")[0]}
      </h1>
      <p className="mt-3 text-lg text-muted">
        Ask me anything about the families, or try one of today&apos;s questions.
      </p>

      {cards === null ? (
        <p className="mt-8 text-[17px] text-muted">Looking at today&apos;s data...</p>
      ) : (
        cards.length > 0 && (
          <ul className="mt-8 space-y-3">
            {cards.map((card) => (
              <li key={card.key}>
                <button
                  type="button"
                  onClick={() => onSuggestion(card)}
                  className="flex w-full items-center gap-4 rounded-2xl border border-border
                    bg-surface px-5 py-4 text-left hover:bg-surface-2"
                >
                  <span className="flex-1 text-[17px] leading-snug">{card.text}</span>
                  <svg
                    width="20"
                    height="20"
                    viewBox="0 0 24 24"
                    fill="none"
                    aria-hidden="true"
                    className="shrink-0 text-muted"
                  >
                    <path
                      d="M9 6l6 6-6 6"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </button>
              </li>
            ))}
          </ul>
        )
      )}
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

function showCell(value: string | number | boolean | null): string {
  if (value === null) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return value.toLocaleString("en-IN");
  return value;
}

/** The reply to a typed question: a plain message, a table, a question back,
 *  or (only for a real problem, e.g. the server being unreachable) an error. */
/** Follow-up questions worth one click, chosen from what the table shows. */
function followUps(answer: AskAnswer, single: boolean): string[] {
  const has = (word: string) => answer.columns.some((c) => c.toLowerCase().includes(word));
  const chips: string[] = [];
  if (single) chips.push("List them");
  else if (answer.rows.length > 0) {
    if (!has("phone")) chips.push("Show their phone numbers");
    if (!has("district")) chips.push("Show their district");
    // Sorting by district only helps when there is more than one district.
    const district = answer.columns.findIndex((c) => c.toLowerCase().includes("district"));
    if (district >= 0 && new Set(answer.rows.map((r) => r[district])).size > 1) {
      chips.push("Sort by district");
    }
  }
  return chips;
}

/** Download what is on screen as an Excel file. */
function DownloadExcel({ answer }: { answer: AskAnswer }) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  async function download() {
    setBusy(true);
    setFailed(false);
    try {
      const blob = await exportAnswerExcel(answer);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${answer.title.replace(/[^\w .-]/g, "").trim() || "Answer"}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        onClick={download}
        disabled={busy}
        className="rounded-full border border-border bg-surface px-4 py-2 text-[15px]
          hover:bg-surface-2 disabled:opacity-60"
      >
        {busy ? "Preparing..." : "Download Excel"}
      </button>
      {failed && <span className="text-sm text-danger">Could not download. Try again.</span>}
    </span>
  );
}

function AnswerReply({
  entry,
  onAsk,
}: {
  entry: Extract<Entry, { kind: "answer" }>;
  onAsk: (question: string) => void;
}) {
  if (entry.state === "thinking") {
    return <p className="text-[17px] text-muted">Looking this up...</p>;
  }
  const answer = entry.answer;
  // A real problem: the network failed, or the server itself reported one.
  if (entry.state === "failed" || !answer || answer.kind === "error") {
    return (
      <div>
        <p className="text-[17px] font-medium text-danger">Something went wrong</p>
        <p className="mt-1 text-[17px] leading-relaxed text-muted">
          {entry.error ?? answer?.error}
        </p>
      </div>
    );
  }

  if (answer.kind === "message") {
    return <p className="text-[17px] leading-relaxed">{answer.message}</p>;
  }

  if (answer.kind === "clarify") {
    return (
      <div className="space-y-3">
        <p className="text-[17px] leading-relaxed">{answer.message}</p>
        {answer.options.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {answer.options.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => onAsk(option)}
                className="rounded-full border border-border bg-surface px-4 py-2 text-[15px]
                  hover:bg-surface-2"
              >
                {option}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  // A single number ("how many...") reads better as a sentence than as a table.
  const single = answer.rows.length === 1 && answer.columns.length === 1;
  // A row with a family code opens that family when clicked.
  const codeColumn = answer.columns.findIndex((c) => c.toLowerCase() === "family code");
  const chips = followUps(answer, single);
  return (
    <div className="space-y-3">
      <p className="text-[17px] font-medium">{answer.title}</p>
      {single ? (
        <p className="text-3xl font-semibold">{showCell(answer.rows[0][0])}</p>
      ) : answer.rows.length === 0 ? (
        <p className="text-[17px] text-muted">Nothing matched.</p>
      ) : (
        <>
          <p className="text-[15px] text-muted">
            {answer.truncated
              ? `Showing the first ${answer.count} results. Ask a narrower question to see the rest.`
              : `${answer.count} result${answer.count === 1 ? "" : "s"}`}
          </p>
          <div className="max-h-[60vh] overflow-auto rounded-2xl border border-border">
            <table className="w-full border-collapse text-left text-[15px]">
              <thead className="sticky top-0 bg-surface-2">
                <tr>
                  {answer.columns.map((column) => (
                    <th key={column} className="whitespace-nowrap px-4 py-2.5 font-medium">
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {answer.rows.map((row, i) => {
                  const code = codeColumn >= 0 ? row[codeColumn] : null;
                  const open = typeof code === "string" && code ? () => onAsk(`details of ${code}`) : undefined;
                  return (
                    <tr
                      key={i}
                      onClick={open}
                      title={open ? "Open this family" : undefined}
                      className={`border-t border-border ${open ? "cursor-pointer hover:bg-surface-2" : ""}`}
                    >
                      {row.map((cell, j) => (
                        <td key={j} className="whitespace-nowrap px-4 py-2.5">
                          {showCell(cell)}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {codeColumn >= 0 && (
            <p className="text-sm text-muted">Click a row to open that family.</p>
          )}
        </>
      )}
      {(answer.rows.length > 0 || chips.length > 0) && (
        <div className="flex flex-wrap items-center gap-2">
          {!single && answer.rows.length > 0 && <DownloadExcel answer={answer} />}
          {chips.map((chip) => (
            <button
              key={chip}
              type="button"
              onClick={() => onAsk(chip)}
              className="rounded-full border border-border bg-surface px-4 py-2 text-[15px]
                text-muted hover:bg-surface-2 hover:text-text"
            >
              {chip}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Conversation({
  entries,
  onMappingConfirmed,
  onSuggestion,
  onAsk,
}: Props) {
  if (entries.length === 0) return <EmptyState onSuggestion={onSuggestion} />;

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-8">
      {entries.map((entry) =>
        entry.kind === "answer" ? (
          <div key={entry.id} className="max-w-full">
            <AnswerReply entry={entry} onAsk={onAsk} />
          </div>
        ) : entry.kind === "text" ? (
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

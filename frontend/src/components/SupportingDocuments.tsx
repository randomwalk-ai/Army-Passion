"use client";

/**
 * A family's supporting documents: at least 1, at most 4.
 *
 * `SupportingDocuments` manages the files already saved for a family.
 * `DocumentPicker` collects files for a family that is not saved yet (the
 * Add-a-family form); they are uploaded once the family exists.
 */

import { useEffect, useRef, useState } from "react";
import { Notice, errorText } from "@/components/ui";
import {
  addSupportingDocument,
  documentFileUrl,
  listDocumentTypes,
  listSupportingDocuments,
  removeSupportingDocument,
  type DocumentItem,
  type DocumentTypeItem,
  type SupportingDocuments as Supporting,
} from "@/lib/api";
import { formatSize } from "@/lib/files";

export const MIN_DOCUMENTS = 1;
export const MAX_DOCUMENTS = 4;
const ACCEPT = ".pdf,.jpg,.jpeg,.png,.webp,application/pdf,image/jpeg,image/png,image/webp";
const ALLOWED = /\.(pdf|jpe?g|png|webp)$/i;
const MAX_BYTES = 20 * 1024 * 1024;

/** Why a picked file can't be taken, or null if it is fine. */
function problemWith(file: File): string | null {
  if (!ALLOWED.test(file.name)) return `“${file.name}” is not a PDF or a photo.`;
  if (file.size === 0) return `“${file.name}” is empty.`;
  if (file.size > MAX_BYTES) return `“${file.name}” is larger than 20 MB.`;
  return null;
}

// The types are the same for every family; fetch them once.
let typesCache: Promise<DocumentTypeItem[]> | null = null;
function useDocumentTypes(): DocumentTypeItem[] {
  const [types, setTypes] = useState<DocumentTypeItem[]>([]);
  useEffect(() => {
    typesCache ??= listDocumentTypes().catch(() => {
      typesCache = null;
      return [];
    });
    let live = true;
    typesCache.then((t) => live && setTypes(t));
    return () => {
      live = false;
    };
  }, []);
  return types;
}

function TypeSelect({
  value,
  onChange,
  id,
}: {
  value: string;
  onChange: (value: string) => void;
  id?: string;
}) {
  const types = useDocumentTypes();
  return (
    <select
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="min-h-12 w-full min-w-0 rounded-xl border border-border bg-bg px-3 text-[17px] outline-none focus:border-accent sm:w-auto"
    >
      {types.length === 0 && <option value="other">Other</option>}
      {types.map((t) => (
        <option key={t.key} value={t.key}>
          {t.label}
        </option>
      ))}
    </select>
  );
}

function FileIcon({ name }: { name: string | null }) {
  const isPdf = /\.pdf$/i.test(name ?? "");
  return (
    <span
      className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-[12px] font-bold text-accent"
      aria-hidden="true"
    >
      {isPdf ? "PDF" : "IMG"}
    </span>
  );
}

function Counter({ count }: { count: number }) {
  const short = count < MIN_DOCUMENTS;
  return (
    <div className="flex items-center gap-3">
      <div className="flex gap-1" aria-hidden="true">
        {Array.from({ length: MAX_DOCUMENTS }, (_, i) => (
          <span
            key={i}
            className={`h-2 w-7 rounded-full ${i < count ? "bg-accent" : short && i === 0 ? "bg-warning/60" : "bg-surface-2"}`}
          />
        ))}
      </div>
      <span className={`text-[15px] ${short ? "font-medium text-warning" : "text-muted"}`}>
        {count} of {MAX_DOCUMENTS}
        {short ? " · at least 1 needed" : ""}
      </span>
    </div>
  );
}

/** The saved documents of one family, with add and remove. */
export function SupportingDocuments({
  familyId,
  onChange,
}: {
  familyId: number;
  /** Called with the new list whenever it loads or changes. */
  onChange?: (documents: DocumentItem[]) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [data, setData] = useState<Supporting | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [docType, setDocType] = useState("other");
  const [busy, setBusy] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<number | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  function show(next: Supporting) {
    setData(next);
    onChangeRef.current?.(next.documents);
  }

  useEffect(() => {
    let live = true;
    setData(null);
    setError(null);
    listSupportingDocuments(familyId)
      .then((d) => live && show(d))
      .catch((e) => live && setError(errorText(e)));
    return () => {
      live = false;
    };
  }, [familyId]);

  async function add(files: FileList | null) {
    if (!files || !data) return;
    setError(null);
    const room = data.maximum - data.documents.length;
    const picked = Array.from(files);
    const problems = picked.map(problemWith).filter(Boolean) as string[];
    const usable = picked.filter((f) => !problemWith(f)).slice(0, room);
    if (picked.length - problems.length > room) {
      problems.push(`Only ${room} more ${room === 1 ? "document fits" : "documents fit"}, so the rest were left out.`);
    }
    let latest = data;
    for (const [index, file] of usable.entries()) {
      setBusy(`Uploading ${usable.length > 1 ? `${index + 1} of ${usable.length}` : file.name}…`);
      try {
        latest = await addSupportingDocument(familyId, file, docType);
        show(latest);
      } catch (e) {
        problems.push(`${file.name}: ${errorText(e)}`);
      }
    }
    setBusy(null);
    if (problems.length) setError(problems.join(" "));
    if (input.current) input.current.value = "";
  }

  async function remove(documentId: number) {
    setConfirming(null);
    setError(null);
    setBusy("Removing…");
    try {
      show(await removeSupportingDocument(familyId, documentId));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(null);
    }
  }

  if (!data) {
    return error ? (
      <Notice tone="danger" title="The documents could not be loaded">
        {error}
      </Notice>
    ) : (
      <p className="py-3 text-[16px] text-muted" role="status">
        Loading documents…
      </p>
    );
  }

  const count = data.documents.length;
  const full = count >= data.maximum;

  return (
    <div className="space-y-3">
      <Counter count={count} />

      {count > 0 && (
        <ul className="space-y-2">
          {data.documents.map((d) => (
            <li key={d.document_id} className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-bg p-3">
              <FileIcon name={d.filename} />
              <div className="min-w-0 flex-1 basis-40">
                <p className="text-[16px] font-medium">{d.doc_type_label}</p>
                <p className="truncate text-[14px] text-muted">
                  {d.filename}
                  {d.size_bytes ? ` · ${formatSize(d.size_bytes)}` : ""}
                  {d.uploaded_on ? ` · ${d.uploaded_on}` : ""}
                </p>
              </div>
              {confirming === d.document_id ? (
                <div className="flex w-full items-center justify-end gap-2 sm:w-auto">
                  <span className="text-[15px]">Remove it?</span>
                  <button
                    onClick={() => remove(d.document_id)}
                    className="min-h-11 rounded-full bg-danger px-4 text-[15px] font-semibold text-bg"
                  >
                    Yes, remove
                  </button>
                  <button
                    onClick={() => setConfirming(null)}
                    className="min-h-11 rounded-full border border-border px-4 text-[15px]"
                  >
                    Keep
                  </button>
                </div>
              ) : (
                <div className="flex w-full justify-end gap-2 sm:w-auto">
                  {d.has_file && (
                    <a
                      href={documentFileUrl(d.document_id)}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex min-h-11 items-center rounded-full border border-border px-4 text-[15px] font-medium hover:bg-surface-2"
                    >
                      View
                    </a>
                  )}
                  <button
                    onClick={() => setConfirming(d.document_id)}
                    disabled={count <= data.minimum || busy !== null}
                    title={count <= data.minimum ? "A family needs at least one document. Add the new one first." : undefined}
                    className="min-h-11 rounded-full px-3 text-[15px] text-muted underline hover:text-danger disabled:no-underline disabled:opacity-40"
                  >
                    Remove
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {count === data.minimum && count > 0 && (
        <p className="text-[14px] text-muted">To swap the only document, add the new one first, then remove the old one.</p>
      )}

      {full ? (
        <p className="rounded-xl bg-surface-2 px-4 py-3 text-[15px] text-muted">
          All {data.maximum} places are used. Remove one to add another.
        </p>
      ) : (
        <div className="flex flex-col gap-2 rounded-xl border border-dashed border-border p-3 sm:flex-row sm:items-center">
          <label htmlFor={`doc-type-${familyId}`} className="text-[15px] text-muted sm:shrink-0">
            What is it?
          </label>
          <TypeSelect id={`doc-type-${familyId}`} value={docType} onChange={setDocType} />
          <input
            ref={input}
            type="file"
            accept={ACCEPT}
            multiple
            className="sr-only"
            aria-label="Choose documents"
            onChange={(e) => add(e.target.files)}
          />
          <button
            onClick={() => input.current?.click()}
            disabled={busy !== null}
            className="inline-flex min-h-12 items-center justify-center gap-2 rounded-full bg-accent px-5 text-[16px] font-semibold text-accent-fg disabled:bg-surface-2 disabled:text-muted sm:ml-auto"
          >
            {busy ?? (count === 0 ? "Add a document" : "Add another")}
          </button>
        </div>
      )}
      <p className="text-[14px] text-muted">PDF or a photo (JPG, PNG), up to 20 MB each. On a phone you can take a photo.</p>

      {error && (
        <Notice tone="danger" title="Not everything was added" onClose={() => setError(null)}>
          {error}
        </Notice>
      )}
    </div>
  );
}

export type PickedDocument = { file: File; docType: string };

/** Files chosen for a family that is not saved yet. */
export function DocumentPicker({
  value,
  onChange,
  error,
}: {
  value: PickedDocument[];
  onChange: (value: PickedDocument[]) => void;
  error?: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [problem, setProblem] = useState<string | null>(null);

  function pick(files: FileList | null) {
    if (!files) return;
    const room = MAX_DOCUMENTS - value.length;
    const picked = Array.from(files);
    const problems = picked.map(problemWith).filter(Boolean) as string[];
    const usable = picked.filter((f) => !problemWith(f));
    if (usable.length > room) problems.push(`Only ${MAX_DOCUMENTS} documents fit, so the rest were left out.`);
    setProblem(problems.length ? problems.join(" ") : null);
    onChange([...value, ...usable.slice(0, room).map((file) => ({ file, docType: "other" }))]);
    if (input.current) input.current.value = "";
  }

  return (
    <div className="space-y-3">
      <Counter count={value.length} />
      {value.length > 0 && (
        <ul className="space-y-2">
          {value.map((item, index) => (
            <li key={`${item.file.name}-${index}`} className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-bg p-3">
              <FileIcon name={item.file.name} />
              <div className="min-w-0 flex-1 basis-40">
                <p className="truncate text-[16px] font-medium">{item.file.name}</p>
                <p className="text-[14px] text-muted">{formatSize(item.file.size)}</p>
              </div>
              <div className="flex w-full items-center gap-2 sm:w-auto">
                <TypeSelect
                  value={item.docType}
                  onChange={(docType) => onChange(value.map((v, i) => (i === index ? { ...v, docType } : v)))}
                />
                <button
                  type="button"
                  onClick={() => onChange(value.filter((_, i) => i !== index))}
                  aria-label={`Remove ${item.file.name}`}
                  className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-muted hover:bg-surface-2 hover:text-danger"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        multiple
        className="sr-only"
        aria-label="Choose documents"
        onChange={(e) => pick(e.target.files)}
      />
      {value.length < MAX_DOCUMENTS && (
        <button
          type="button"
          onClick={() => input.current?.click()}
          className="flex min-h-14 w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border text-[17px] font-medium text-accent hover:border-accent hover:bg-accent-soft"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          {value.length === 0 ? "Choose documents" : "Add another"}
        </button>
      )}
      <p className="text-[14px] text-muted">PDF or a photo (JPG, PNG), up to 20 MB each. On a phone you can take a photo.</p>
      {(error || problem) && <p className="text-[15px] text-danger">{error ?? problem}</p>}
    </div>
  );
}

/**
 * Works out what the colonel just dropped, so the right flow can start.
 *
 * He never picks "import mode" — he drops a file and the system decides.
 */

export type DroppedKind = "excel" | "audio" | "document" | "unsupported";

const EXCEL_EXTENSIONS = ["xlsx", "xls", "csv"];
const AUDIO_EXTENSIONS = ["mp3", "m4a", "wav", "ogg", "opus", "aac", "webm"];
// PDFs and photos are documents to attach to a family or child.
const DOCUMENT_EXTENSIONS = ["pdf", "jpg", "jpeg", "png", "webp"];

export function extensionOf(filename: string): string {
  const parts = filename.toLowerCase().split(".");
  return parts.length > 1 ? parts[parts.length - 1] : "";
}

export function classify(file: File): DroppedKind {
  const ext = extensionOf(file.name);
  if (EXCEL_EXTENSIONS.includes(ext)) return "excel";
  if (AUDIO_EXTENSIONS.includes(ext)) return "audio";
  if (DOCUMENT_EXTENSIONS.includes(ext)) return "document";
  // Some browsers give a useful MIME type even when the extension is odd.
  if (file.type.startsWith("audio/")) return "audio";
  return "unsupported";
}

export const ACCEPTED_EXTENSIONS = [
  ...EXCEL_EXTENSIONS,
  ...AUDIO_EXTENSIONS,
  ...DOCUMENT_EXTENSIONS,
]
  .map((e) => `.${e}`)
  .join(",");

/** "2.4 MB" — readable sizes rather than raw bytes. */
export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Talking to the backend. */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8010";

export type TargetField = {
  key: string;
  label: string;
  group: string;
  required: boolean;
};

export type Column = {
  source_heading: string;
  column_index: number;
  target_key: string | null;
  confidence: number;
  reason: string;
  samples: string[];
  /** A name proposed for a column that fits none of our fields. */
  suggested_new_field: string | null;
};

export type UploadResult = {
  import_id: number;
  filename: string;
  sheet_name: string | null;
  header_row_number: number | null;
  row_count: number;
  columns: Column[];
  missing_required: TargetField[];
  target_fields: TargetField[];
  remembered: boolean;
  remembered_label: string | null;
};

export type MappingResult = {
  import_id: number;
  status: string;
  mapping: Record<string, string>;
  missing_required: TargetField[];
  remembered: boolean;
};

export const IGNORE = "__ignore__";

/** FastAPI puts the readable reason in `detail`. */
async function failureMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
  } catch {
    // fall through to the generic message
  }
  return `Something went wrong (${response.status}).`;
}

export async function uploadSheet(file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);

  const response = await fetch(`${API_BASE}/api/imports/upload`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.json();
}

export type FieldChange = {
  field_name: string;
  label: string;
  old_value: string | null;
  new_value: string | null;
};

export type RowProblem = {
  field: string;
  code: string;
  severity: string;
  message: string;
};

export type EditableField = {
  field_key: string;
  label: string;
  value: string;
  edited: boolean;
};

export type RowPreview = {
  row_number: number;
  action:
    | "create"
    | "update"
    | "unchanged"
    | "needs_decision"
    | "duplicate_in_file"
    | "skipped"
    | "excluded";
  fields: EditableField[];
  edited_fields: string[];
  skipped_by_user: boolean;
  widow_name: string | null;
  soldier_name: string | null;
  district: string | null;
  matched_family_id: number | null;
  matched_family_code: string | null;
  match_score: number;
  match_reasons: string[];
  other_matches: { family_id: number; family_code: string; score: number }[];
  changes: FieldChange[];
  problems: RowProblem[];
  duplicate_of_row: number | null;
};

export type ActiveColumn = {
  field_key: string;
  label: string;
  required: boolean;
  /** The sheet heading feeding it, or null if added on the preview. */
  source_heading: string | null;
  added: boolean;
  default_value: string | null;
};

export type PreviewResult = {
  import_id: number;
  filename: string;
  total_rows: number;
  counts: Record<string, number>;
  problem_count: number;
  rows: RowPreview[];
  active_columns: ActiveColumn[];
  addable_fields: TargetField[];
};

export async function editImportColumns(
  importId: number,
  body: {
    remove_headings?: string[];
    add_fields?: Record<string, string>;
    remove_added?: string[];
  },
): Promise<PreviewResult> {
  const response = await fetch(`${API_BASE}/api/imports/${importId}/columns`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.json();
}

export async function retireCustomField(key: string): Promise<void> {
  const response = await fetch(
    `${API_BASE}/api/custom-fields/${encodeURIComponent(key)}`,
    { method: "DELETE" },
  );
  if (!response.ok) throw new Error(await failureMessage(response));
}

export type CommitResult = {
  import_id: number;
  status: string;
  created: number;
  updated: number;
  unchanged: number;
  skipped: number;
  duplicates_flagged: number;
  needs_decision: number;
  excluded: number;
  fields_changed: number;
  fields_corrected: number;
  issues_raised: number;
  new_family_codes: string[];
};

export async function editImportRow(
  importId: number,
  rowNumber: number,
  body: { values?: Record<string, string>; skip?: boolean },
): Promise<PreviewResult> {
  const response = await fetch(
    `${API_BASE}/api/imports/${importId}/rows/${rowNumber}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values: body.values ?? {}, skip: body.skip ?? false }),
    },
  );
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.json();
}

export async function previewImport(importId: number): Promise<PreviewResult> {
  const response = await fetch(`${API_BASE}/api/imports/${importId}/preview`, {
    method: "POST",
  });
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.json();
}

export async function commitImport(importId: number): Promise<CommitResult> {
  const response = await fetch(`${API_BASE}/api/imports/${importId}/commit`, {
    method: "POST",
  });
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.json();
}

// --- extra fields -------------------------------------------------------

export type CustomField = {
  key: string;
  label: string;
  description: string | null;
  first_seen_as: string | null;
  times_used: number;
};

/** Prefix that marks a mapping target as an extra field. */
export const EXTRA_PREFIX = "extra:";

export async function createCustomField(
  label: string,
  firstSeenAs?: string,
  importId?: number,
): Promise<CustomField> {
  const response = await fetch(`${API_BASE}/api/custom-fields`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      label,
      first_seen_as: firstSeenAs,
      import_id: importId,
    }),
  });
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.json();
}

// --- documents ----------------------------------------------------------

export type FamilyMemberItem = {
  member_id: number;
  full_name: string;
  relation: string;
  date_of_birth: string | null;
};

export type DocumentTypeItem = { key: string; label: string };

export type DocumentItem = {
  document_id: number;
  family_id: number;
  member_id: number | null;
  belongs_to: string;
  doc_type: string;
  doc_type_label: string;
  filename: string | null;
  size_bytes: number | null;
  status: string;
  uploaded_on: string | null;
  has_file: boolean;
};

export async function listFamilyMembers(familyId: number): Promise<FamilyMemberItem[]> {
  const response = await fetch(`${API_BASE}/api/families/${familyId}/members`);
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.json();
}

export async function listDocumentTypes(): Promise<DocumentTypeItem[]> {
  const response = await fetch(`${API_BASE}/api/document-types`);
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.json();
}

export async function listFamilyDocuments(familyId: number): Promise<DocumentItem[]> {
  const response = await fetch(`${API_BASE}/api/families/${familyId}/documents`);
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.json();
}

export async function uploadDocument(
  familyId: number,
  file: File,
  docType: string,
  memberId: number | null,
): Promise<DocumentItem> {
  const form = new FormData();
  form.append("file", file);
  form.append("doc_type", docType);
  if (memberId !== null) form.append("member_id", String(memberId));
  const response = await fetch(`${API_BASE}/api/families/${familyId}/documents`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.json();
}

export function documentFileUrl(documentId: number): string {
  return `${API_BASE}/api/documents/${documentId}/file`;
}

// --- voice notes --------------------------------------------------------

export type FamilySearchItem = {
  family_id: number;
  family_code: string;
  primary_contact_name: string;
  soldier_name: string | null;
  district: string | null;
  state: string | null;
  is_draft: boolean;
};

export type VoiceUploadResult = {
  voice_id: number;
  filename: string;
  language: string;
  transcript: string;
  summary: string | null;
  confidence: number | null;
  duration_seconds: number | null;
  provider: string;
  heard: Record<string, unknown>;
  sentiment: string | null;
  follow_up_needed: boolean;
  follow_up_note: string | null;
  looks_like_new_family: boolean;
  suggested_new_family: Record<string, string>;
  suggested_family_id: number | null;
  suggested_family_code: string | null;
  suggested_family_confidence: number;
  suggested_family_reason: string | null;
  suggested_field_changes: {
    field_key: string;
    label: string;
    new_value: string;
    reason: string;
  }[];
};

export type NewFamilyInput = {
  widow_name?: string;
  soldier_name?: string;
  rank?: string;
  unit?: string;
  service_number?: string;
  date_of_death?: string;
  cause_of_death?: string;
  district?: string;
  state?: string;
  phone?: string;
};

export type VoiceConfirmResult = {
  voice_id: number;
  interaction_id: number;
  family_id: number;
  family_code: string;
  created_family: boolean;
  is_draft: boolean;
  missing_for_completion: string[];
  possible_duplicate_of: string | null;
  warnings: string[];
  fields_updated: string[];
};

export async function uploadVoiceNote(file: File): Promise<VoiceUploadResult> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE}/api/voice/upload`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.json();
}

export async function searchFamilies(query: string): Promise<FamilySearchItem[]> {
  const response = await fetch(
    `${API_BASE}/api/families/search?q=${encodeURIComponent(query)}`,
  );
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.json();
}

export async function confirmVoiceNote(
  voiceId: number,
  body: {
    family_id?: number;
    new_family?: NewFamilyInput;
    transcript?: string;
    apply_field_changes?: string[];
  },
): Promise<VoiceConfirmResult> {
  const response = await fetch(`${API_BASE}/api/voice/${voiceId}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.json();
}

export async function confirmMapping(
  importId: number,
  mapping: Record<string, string>,
): Promise<MappingResult> {
  const response = await fetch(`${API_BASE}/api/imports/${importId}/mapping`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mapping }),
  });
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.json();
}

// --- dashboard ----------------------------------------------------------

export type Stat = {
  key: string;
  label: string;
  value: number;
  hint: string | null;
  tone: "normal" | "attention";
  href: string | null;
};

export async function getDashboard(): Promise<{ stats: Stat[] }> {
  const response = await fetch(`${API_BASE}/api/dashboard`, { cache: "no-store" });
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.json();
}

// --- adding a family by hand ---------------------------------------------

export type NewChild = {
  name: string;
  sex: "" | "M" | "F";
  date_of_birth: string;
  current_class: string;
  school_name: string;
  school_place: string;
  is_hostel: boolean;
  has_disability: boolean;
};

export type DuplicateMatch = {
  family_id: number;
  family_code: string;
  score: number;
  reasons: string[];
  primary_contact_name: string;
  soldier_name: string | null;
  district: string | null;
};

/** What can come back from saving a form, besides success. */
export class FormRejected extends Error {
  constructor(
    message: string,
    public fieldErrors: Record<string, string> = {},
    public matches: DuplicateMatch[] = [],
  ) {
    super(message);
  }
}

async function rejection(response: Response): Promise<Error> {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (typeof detail === "string") return new FormRejected(detail);
    if (detail && typeof detail === "object") {
      return new FormRejected(
        detail.message ?? "Please check the form.",
        detail.errors ?? detail.problems ?? {},
        detail.matches ?? [],
      );
    }
  } catch {
    // fall through
  }
  return new Error(`Something went wrong (${response.status}).`);
}

export async function createFamily(body: {
  values: Record<string, string>;
  children: NewChild[];
  confirm_not_duplicate?: boolean;
}): Promise<{
  family_id: number;
  family_code: string;
  primary_contact_name: string;
  warnings: string[];
}> {
  const response = await fetch(`${API_BASE}/api/families`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await rejection(response);
  return response.json();
}

// --- CEA claims -----------------------------------------------------------

export type CeaStatus = "eligible" | "needs_data" | "eligible_later" | "not_eligible";

export type CeaChildVerdict = {
  member_id: number | null;
  name: string;
  status: CeaStatus;
  status_label: string;
  reasons: string[];
  to_confirm: string[];
  age: number | null;
  amount: number;
};

export type CeaFamily = {
  family_id: number;
  family_code: string;
  nok_name: string;
  soldier_name: string | null;
  soldier_rank: string | null;
  district: string | null;
  state: string | null;
  status: CeaStatus;
  status_label: string;
  reasons: string[];
  amount: number;
  children: CeaChildVerdict[];
};

export type CeaEligibility = {
  academic_year: string;
  years: { label: string; is_default: boolean }[];
  counts: Record<CeaStatus, number>;
  total_amount: number;
  families: CeaFamily[];
  rules_summary: string[];
};

export type CeaChildForm = {
  member_id: number | null;
  name: string;
  relation: string;
  date_of_birth: string;
  current_class: string;
  section: string;
  roll_number: string;
  admission_number: string;
  school_name: string;
  school_place: string;
  school_board: string;
  school_affiliation_code: string;
  is_hostel: boolean;
  has_disability: boolean;
  period_from: string;
  period_to: string;
  cea_amount: number;
  hostel_amount: number;
};

export type CeaForm = {
  family_id: number;
  academic_year: string;
  dated: string;
  nok_name: string;
  soldier_name: string;
  soldier_rank: string;
  service_number: string;
  unit: string;
  record_office: string;
  record_office_pincode: string;
  home_address: string;
  permanent_pincode: string;
  correspondence_address: string;
  correspondence_pincode: string;
  mobile: string;
  bank_account_holder: string;
  bank_name: string;
  bank_branch: string;
  bank_address: string;
  bank_account_number: string;
  bank_ifsc: string;
  school_state: string;
  nok_is_govt_servant: boolean | null;
  children: CeaChildForm[];
};

export async function getCeaEligibility(year?: string): Promise<CeaEligibility> {
  const query = year ? `?year=${encodeURIComponent(year)}` : "";
  const response = await fetch(`${API_BASE}/api/cea/eligibility${query}`, {
    cache: "no-store",
  });
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.json();
}

export async function getCeaForm(
  familyId: number,
  year?: string,
): Promise<{ form: CeaForm; family: CeaFamily; missing: string[] }> {
  const query = year ? `?year=${encodeURIComponent(year)}` : "";
  const response = await fetch(`${API_BASE}/api/cea/families/${familyId}/form${query}`, {
    cache: "no-store",
  });
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.json();
}

export async function saveCeaForm(
  form: CeaForm,
): Promise<{ changed: string[]; form: CeaForm; missing: string[] }> {
  const response = await fetch(`${API_BASE}/api/cea/families/${form.family_id}/form`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ form }),
  });
  if (!response.ok) throw await rejection(response);
  return response.json();
}

export async function downloadCeaPdf(form: CeaForm): Promise<Blob> {
  const response = await fetch(`${API_BASE}/api/cea/pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ form }),
  });
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.blob();
}

/** Indian grouping: 101250 -> "1,01,250". */
export function rupees(amount: number): string {
  return `₹${amount.toLocaleString("en-IN")}`;
}

/** One earlier question in this chat, kept so a follow-up like "list them" can
 *  be understood. Never carries the rows that came back — only what was
 *  typed and what the AI itself wrote (a title, a search, a reply). */
export type AskTurn = {
  question: string;
  title?: string | null;
  sql?: string | null;
  reply?: string | null;
  /** Which of our own tools answered (CEA, a family), and for whom. */
  tool?: string | null;
};

export type AskAnswer = {
  /** "table" (rows), "message" (a plain reply), "clarify" (a question back,
   *  with clickable options) or "error" (something went wrong). */
  kind: "table" | "message" | "clarify" | "error";
  title: string;
  columns: string[];
  rows: (string | number | boolean | null)[][];
  count: number;
  /** More rows matched than were sent; `count` is then the number shown. */
  truncated: boolean;
  /** The search that was run, kept to send back as history; not shown. */
  sql: string | null;
  /** The reply text, for kind "message" or "clarify". */
  message: string | null;
  /** Clickable choices, for kind "clarify". */
  options: string[];
  /** Set for kind "error". */
  error: string | null;
  /** Which of our own tools answered (CEA, a family); kept as history. */
  tool?: string | null;
};

export async function askQuestion(question: string, history: AskTurn[] = []): Promise<AskAnswer> {
  const response = await fetch(`${API_BASE}/api/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, history }),
  });
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.json();
}

export type SuggestionCard = {
  key: string;
  group: "general" | "specific";
  text: string;
  count: number | null;
};

/** Today's suggested questions, built from the data. */
export async function getSuggestions(): Promise<SuggestionCard[]> {
  const response = await fetch(`${API_BASE}/api/ask/suggestions`);
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.json();
}

/** The answer to a suggested question (our own search, not the AI). */
export async function answerSuggestion(key: string): Promise<AskAnswer> {
  const response = await fetch(`${API_BASE}/api/ask/suggestions/${encodeURIComponent(key)}`, {
    method: "POST",
  });
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.json();
}

/** The table already on screen, as an Excel file (no search is re-run). */
export async function exportAnswerExcel(answer: {
  title: string;
  columns: string[];
  rows: AskAnswer["rows"];
}): Promise<Blob> {
  const response = await fetch(`${API_BASE}/api/ask/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(answer),
  });
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.blob();
}

// --- saved Assistant chats ---------------------------------------------------

export type ChatSummary = { id: number; title: string; updated_at: string };
export type SavedChat = {
  id: number;
  title: string;
  messages: { question: string; answer: AskAnswer }[];
};

export async function listChats(): Promise<ChatSummary[]> {
  const response = await fetch(`${API_BASE}/api/chats`);
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.json();
}

/** Starts a new saved chat with its first question and answer. */
export async function startChat(question: string, answer: AskAnswer): Promise<ChatSummary> {
  const response = await fetch(`${API_BASE}/api/chats`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, answer }),
  });
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.json();
}

export async function addChatMessage(
  chatId: number,
  question: string,
  answer: AskAnswer,
): Promise<ChatSummary> {
  const response = await fetch(`${API_BASE}/api/chats/${chatId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, answer }),
  });
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.json();
}

export async function openChat(chatId: number): Promise<SavedChat> {
  const response = await fetch(`${API_BASE}/api/chats/${chatId}`);
  if (!response.ok) throw new Error(await failureMessage(response));
  return response.json();
}

export async function deleteChat(chatId: number): Promise<void> {
  const response = await fetch(`${API_BASE}/api/chats/${chatId}`, { method: "DELETE" });
  if (!response.ok) throw new Error(await failureMessage(response));
}

"use client";

import { useEffect, useState } from "react";
import FamilyPicker from "@/components/FamilyPicker";
import {
  documentFileUrl,
  listDocumentTypes,
  listFamilyDocuments,
  listFamilyMembers,
  uploadDocument,
  type DocumentItem,
  type DocumentTypeItem,
  type FamilyMemberItem,
  type FamilySearchItem,
} from "@/lib/api";

type Props = { file: File };

type Stage = "pick-family" | "details" | "done";

const RELATION_LABELS: Record<string, string> = {
  widow: "NOK",
  son: "son",
  daughter: "daughter",
  father: "father",
  mother: "mother",
  other_dependent: "dependant",
};

/** Attach a PDF or photo to a family, or to one person in it. */
export default function DocumentUpload({ file }: Props) {
  const [stage, setStage] = useState<Stage>("pick-family");
  const [family, setFamily] = useState<FamilySearchItem | null>(null);
  const [members, setMembers] = useState<FamilyMemberItem[]>([]);
  const [types, setTypes] = useState<DocumentTypeItem[]>([]);
  // null means "the whole family".
  const [memberId, setMemberId] = useState<number | null>(null);
  const [docType, setDocType] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<DocumentItem | null>(null);
  const [existing, setExisting] = useState<DocumentItem[]>([]);

  useEffect(() => {
    listDocumentTypes()
      .then(setTypes)
      .catch(() => setError("Could not load the document types."));
  }, []);

  async function pickFamily(picked: FamilySearchItem) {
    setFamily(picked);
    setError(null);
    try {
      setMembers(await listFamilyMembers(picked.family_id));
      setStage("details");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the family.");
    }
  }

  async function save() {
    if (!family || !docType) return;
    setSaving(true);
    setError(null);
    try {
      setSaved(await uploadDocument(family.family_id, file, docType, memberId));
      setExisting(await listFamilyDocuments(family.family_id));
      setStage("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not upload the document.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-2xl border border-border bg-surface p-5">
      <h2 className="text-[17px] font-semibold">Attach a document</h2>
      <p className="mt-1 text-[15px] text-muted">
        {file.name}
        {family && (
          <>
            {" "}
            → <span className="font-medium text-text">{family.primary_contact_name}</span> (
            {family.family_code})
          </>
        )}
      </p>

      {error && <p className="mt-3 text-[15px] text-danger">{error}</p>}

      {stage === "pick-family" && (
        <div className="mt-4">
          <FamilyPicker title="Which family is this for?" onPick={pickFamily} />
        </div>
      )}

      {stage === "details" && (
        <div className="mt-4 space-y-4">
          <div>
            <h3 className="text-[15px] font-semibold">Who does it belong to?</h3>
            <div className="mt-2 space-y-1.5">
              <label className="flex items-center gap-2 text-[15px]">
                <input
                  type="radio"
                  name="belongs"
                  checked={memberId === null}
                  onChange={() => setMemberId(null)}
                />
                The whole family
                <span className="text-xs text-muted">
                  (e.g. service booklet, PPO, cancelled cheque)
                </span>
              </label>
              {members.map((member) => (
                <label key={member.member_id} className="flex items-center gap-2 text-[15px]">
                  <input
                    type="radio"
                    name="belongs"
                    checked={memberId === member.member_id}
                    onChange={() => setMemberId(member.member_id)}
                  />
                  {member.full_name}
                  <span className="text-xs text-muted">
                    {RELATION_LABELS[member.relation] ?? member.relation}
                    {member.date_of_birth && `, born ${member.date_of_birth}`}
                  </span>
                </label>
              ))}
            </div>
          </div>

          <div>
            <h3 className="text-[15px] font-semibold">What is it?</h3>
            <select
              value={docType}
              onChange={(e) => setDocType(e.target.value)}
              className="mt-2 w-full rounded-lg border border-border bg-bg px-3 py-2.5 text-[15px]"
            >
              <option value="">Choose the document type...</option>
              {types.map((type) => (
                <option key={type.key} value={type.key}>
                  {type.label}
                </option>
              ))}
            </select>
          </div>

          <div className="flex gap-3">
            <button
              onClick={save}
              disabled={!docType || saving}
              className="rounded-full bg-accent px-5 py-2.5 text-[15px] font-medium
                text-accent-fg disabled:bg-surface-2 disabled:text-muted"
            >
              {saving ? "Uploading..." : "Save document"}
            </button>
            <button
              onClick={() => {
                setStage("pick-family");
                setFamily(null);
                setMemberId(null);
              }}
              disabled={saving}
              className="text-[15px] text-muted underline"
            >
              Different family
            </button>
          </div>
        </div>
      )}

      {stage === "done" && saved && (
        <div className="mt-4">
          <p className="text-[17px] font-medium text-accent">
            Saved — {saved.doc_type_label}, {saved.belongs_to.toLowerCase() === "whole family" ? "for the whole family" : `for ${saved.belongs_to}`}
          </p>

          {existing.length > 0 && (
            <div className="mt-3">
              <p className="text-[14px] font-medium">Documents on record for this family</p>
              <ul className="mt-1">
                {existing.map((doc) => (
                  <li
                    key={doc.document_id}
                    className="flex items-center justify-between gap-3 border-t border-border py-1.5 text-[14px]"
                  >
                    <span className="min-w-0 truncate">
                      {doc.doc_type_label}
                      <span className="text-muted"> · {doc.belongs_to}</span>
                    </span>
                    {doc.has_file ? (
                      <a
                        href={documentFileUrl(doc.document_id)}
                        target="_blank"
                        rel="noreferrer"
                        className="shrink-0 text-accent underline"
                      >
                        open
                      </a>
                    ) : (
                      <span className="shrink-0 text-xs text-muted">record only</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {stage !== "done" && (
        <p className="mt-3 text-xs text-muted">Nothing has been saved yet.</p>
      )}
    </div>
  );
}

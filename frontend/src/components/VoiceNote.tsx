"use client";

import { useEffect, useState } from "react";
import FamilyPicker from "@/components/FamilyPicker";
import NewFamilyForm from "@/components/NewFamilyForm";
import {
  confirmVoiceNote,
  uploadVoiceNote,
  type NewFamilyInput,
  type VoiceConfirmResult,
  type VoiceUploadResult,
} from "@/lib/api";

type Props = { file: File };

type Stage = "transcribing" | "pick" | "new-family" | "done" | "failed";

export default function VoiceNote({ file }: Props) {
  const [stage, setStage] = useState<Stage>("transcribing");
  const [heardResult, setHeardResult] = useState<VoiceUploadResult | null>(null);
  const [transcript, setTranscript] = useState("");
  const [editing, setEditing] = useState(false);
  const [result, setResult] = useState<VoiceConfirmResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // Field changes the AI proposed from the call that he has agreed to.
  // Nothing here is applied until he picks a family and saves.
  const [acceptedChanges, setAcceptedChanges] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    uploadVoiceNote(file)
      .then((data) => {
        if (cancelled) return;
        setHeardResult(data);
        setTranscript(data.transcript);
        // If it sounds like a casualty we have not heard of, go straight to
        // the new-family form with what was heard already filled in.
        setStage(data.looks_like_new_family ? "new-family" : "pick");
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(
          e instanceof Error
            ? e.message
            : "I could not reach the server. Is the backend running?",
        );
        setStage("failed");
      });
    return () => {
      cancelled = true;
    };
  }, [file]);

  async function save(body: { family_id?: number; new_family?: NewFamilyInput }) {
    if (!heardResult) return;
    setSaving(true);
    setError(null);
    try {
      const saved = await confirmVoiceNote(heardResult.voice_id, {
        ...body,
        transcript,
        apply_field_changes: [...acceptedChanges],
      });
      setResult(saved);
      setStage("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the voice note.");
    } finally {
      setSaving(false);
    }
  }

  if (stage === "transcribing") {
    return <p className="text-[17px] text-muted">Listening to the recording...</p>;
  }
  if (stage === "failed") {
    return (
      <div>
        <p className="text-[17px] font-medium text-danger">
          I could not use that recording
        </p>
        <p className="mt-1 text-[17px] leading-relaxed text-muted">{error}</p>
      </div>
    );
  }
  if (!heardResult) return null;

  return (
    <div className="rounded-2xl border border-border bg-surface p-5">
      <h2 className="text-[17px] font-semibold">This is what I heard</h2>

      {editing ? (
        <textarea
          value={transcript}
          onChange={(e) => setTranscript(e.target.value)}
          rows={5}
          className="mt-2 w-full rounded-lg border border-border bg-bg px-3 py-2.5
            text-[16px] leading-relaxed outline-none focus:border-accent"
        />
      ) : (
        <p className="mt-2 whitespace-pre-wrap text-[16px] leading-relaxed">
          {transcript}
        </p>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-muted">
        <span>{heardResult.language}</span>
        {heardResult.confidence != null && <span>{heardResult.confidence}% sure</span>}
        {heardResult.duration_seconds != null && (
          <span>{heardResult.duration_seconds}s</span>
        )}
        <span className="rounded bg-surface-2 px-1.5 py-0.5">mock transcription</span>
        {stage !== "done" && (
          <button
            onClick={() => setEditing((v) => !v)}
            className="text-accent underline"
          >
            {editing ? "done editing" : "correct this"}
          </button>
        )}
      </div>

      {heardResult.summary && (
        <p className="mt-3 rounded-lg bg-surface-2 px-3 py-2 text-[15px] leading-relaxed">
          <span className="font-medium">In short: </span>
          {heardResult.summary}
        </p>
      )}

      {heardResult.follow_up_note && (
        <p className="mt-2 text-[15px] text-warning">
          Follow up: {heardResult.follow_up_note}
        </p>
      )}

      <div className="mt-5 border-t border-border pt-4">
        {error && <p className="mb-3 text-[15px] text-danger">{error}</p>}

        {stage === "pick" && (
          <>
            {heardResult.suggested_family_id &&
              heardResult.suggested_family_code && (
                <div className="mb-4 rounded-lg border border-accent bg-accent-soft px-3 py-2.5">
                  <p className="text-[15px]">
                    This sounds like{" "}
                    <span className="font-medium">
                      {heardResult.suggested_family_code}
                    </span>
                    {heardResult.suggested_family_reason &&
                      ` — ${heardResult.suggested_family_reason}`}
                    {" "}
                    ({heardResult.suggested_family_confidence}% sure)
                  </p>
                  <button
                    onClick={() =>
                      save({ family_id: heardResult.suggested_family_id as number })
                    }
                    disabled={saving}
                    className="mt-2 rounded-full bg-accent px-4 py-1.5 text-[14px]
                      font-medium text-accent-fg disabled:bg-surface-2 disabled:text-muted"
                  >
                    {saving ? "Saving..." : "Yes, that's her"}
                  </button>
                  <span className="ml-3 text-[14px] text-muted">
                    or search below if that is wrong
                  </span>
                </div>
              )}

            {heardResult.suggested_field_changes.length > 0 && (
              <div className="mb-4 rounded-lg border border-border px-3 py-2.5">
                <p className="text-[15px] font-medium">
                  This call suggests some changes
                </p>
                <ul className="mt-1.5 space-y-1.5">
                  {heardResult.suggested_field_changes.map((change) => (
                    <li key={change.field_key} className="flex items-start gap-2">
                      <input
                        type="checkbox"
                        id={`change-${change.field_key}`}
                        checked={acceptedChanges.has(change.field_key)}
                        onChange={(e) =>
                          setAcceptedChanges((prev) => {
                            const next = new Set(prev);
                            if (e.target.checked) next.add(change.field_key);
                            else next.delete(change.field_key);
                            return next;
                          })
                        }
                        className="mt-1"
                      />
                      <label
                        htmlFor={`change-${change.field_key}`}
                        className="text-[14px] leading-snug"
                      >
                        <span className="font-medium">{change.label}</span> →{" "}
                        {change.new_value}
                        {change.reason && (
                          <span className="block text-muted">{change.reason}</span>
                        )}
                      </label>
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-xs text-muted">
                  Ticked changes are applied only once you pick the family below and save.
                </p>
              </div>
            )}

            <FamilyPicker
              onPick={(family) => save({ family_id: family.family_id })}
              onNewFamily={() => setStage("new-family")}
            />
          </>
        )}

        {stage === "new-family" && (
          <NewFamilyForm
            heard={heardResult.suggested_new_family}
            saving={saving}
            onSave={(details) => save({ new_family: details })}
            onCancel={() => setStage("pick")}
          />
        )}

        {stage === "done" && result && (
          <div>
            <p className="text-[17px] font-medium text-accent">
              {result.created_family
                ? `Family added — ${result.family_code}`
                : `Saved against ${result.family_code}`}
            </p>

            {result.created_family && result.missing_for_completion.length > 0 && (
              <p className="mt-2 text-[15px] leading-relaxed text-muted">
                Added to the needs-attention list — still missing:{" "}
                {result.missing_for_completion.join(", ")}.
              </p>
            )}

            {result.fields_updated.length > 0 && (
              <p className="mt-2 text-[15px] text-muted">
                Updated from the call: {result.fields_updated.join(", ")}.
              </p>
            )}

            {result.warnings.map((warning) => (
              <p key={warning} className="mt-2 text-[15px] text-warning">
                {warning}
              </p>
            ))}
          </div>
        )}
      </div>

      {stage !== "done" && (
        <p className="mt-3 text-xs text-muted">Nothing has been saved yet.</p>
      )}
    </div>
  );
}

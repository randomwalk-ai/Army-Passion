"use client";

/** Add one family by hand. Only the two names are needed; the rest can wait. */

import Link from "next/link";
import { useRef, useState } from "react";
import AppShell from "@/components/AppShell";
import { DocumentPicker, MIN_DOCUMENTS, type PickedDocument } from "@/components/SupportingDocuments";
import {
  Card,
  Checkbox,
  Choice,
  Field,
  Notice,
  PageHeader,
  SectionTitle,
  buttonPrimary,
  buttonSecondary,
  errorText,
} from "@/components/ui";
import {
  FormRejected,
  addSupportingDocument,
  createFamily,
  type DuplicateMatch,
  type NewChild,
} from "@/lib/api";

const STATES = [
  "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat",
  "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh",
  "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan",
  "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
  "Andaman and Nicobar Islands", "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu",
  "Delhi", "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
];

const emptyChild = (): NewChild => ({
  name: "",
  sex: "",
  date_of_birth: "",
  current_class: "",
  school_name: "",
  school_place: "",
  is_hostel: false,
  has_disability: false,
});

type Saved = {
  family_id: number;
  family_code: string;
  primary_contact_name: string;
  warnings: string[];
  /** Documents that did not upload, in words. */
  uploadFailures: string[];
};

export default function NewFamilyPage() {
  const [values, setValues] = useState<Record<string, string>>({ nok_relationship: "Wife" });
  const [children, setChildren] = useState<NewChild[]>([emptyChild()]);
  const [showBank, setShowBank] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [matches, setMatches] = useState<DuplicateMatch[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<Saved | null>(null);
  const [documents, setDocuments] = useState<PickedDocument[]>([]);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [progress, setProgress] = useState<string | null>(null);
  const top = useRef<HTMLDivElement>(null);
  const documentsCard = useRef<HTMLDivElement>(null);

  const field = (key: string) => ({
    value: values[key] ?? "",
    onChange: (v: string) => {
      setValues((prev) => ({ ...prev, [key]: v }));
      if (errors[key]) setErrors(({ [key]: _, ...rest }) => rest);
    },
    error: errors[key],
  });

  const setChild = (index: number, change: Partial<NewChild>) =>
    setChildren((prev) => prev.map((c, i) => (i === index ? { ...c, ...change } : c)));

  async function save(confirmNotDuplicate = false) {
    if (documents.length < MIN_DOCUMENTS) {
      setDocumentsError("Please add at least one document, for example the death certificate or PPO.");
      documentsCard.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    setSaving(true);
    setMessage(null);
    setMatches([]);
    try {
      const result = await createFamily({
        values,
        children,
        confirm_not_duplicate: confirmNotDuplicate,
      });
      // The family is saved; now its documents, one at a time.
      const uploadFailures: string[] = [];
      for (const [index, d] of documents.entries()) {
        setProgress(`Uploading document ${index + 1} of ${documents.length}…`);
        try {
          await addSupportingDocument(result.family_id, d.file, d.docType);
        } catch (e) {
          uploadFailures.push(`${d.file.name}: ${errorText(e)}`);
        }
      }
      setSaved({ ...result, uploadFailures });
      top.current?.scrollIntoView({ behavior: "smooth" });
    } catch (e) {
      if (e instanceof FormRejected) {
        setErrors(e.fieldErrors);
        setMatches(e.matches);
        setMessage(e.message);
        if (e.fieldErrors.bank_ifsc || e.fieldErrors.bank_account_number) setShowBank(true);
      } else {
        setMessage(errorText(e));
      }
      top.current?.scrollIntoView({ behavior: "smooth" });
    } finally {
      setSaving(false);
      setProgress(null);
    }
  }

  function startAgain() {
    setValues({ nok_relationship: "Wife" });
    setChildren([emptyChild()]);
    setErrors({});
    setMessage(null);
    setMatches([]);
    setSaved(null);
    setShowBank(false);
    setDocuments([]);
    setDocumentsError(null);
  }

  // ---------- after saving ----------
  if (saved) {
    return (
      <AppShell>
        <div ref={top} />
        <div className="mx-auto max-w-2xl py-6 text-center">
          <span className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-accent-soft text-accent" aria-hidden="true">
            <svg width="34" height="34" viewBox="0 0 24 24" fill="none">
              <path d="M5 12.5l4.5 4.5L19 7" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          <h1 className="mt-5 text-3xl font-semibold tracking-tight">Family saved</h1>
          <p className="mt-3 text-lg text-muted">
            {saved.primary_contact_name}&rsquo;s family is now in the system as{" "}
            <span className="font-semibold text-text">{saved.family_code}</span>.
          </p>
          {saved.uploadFailures.length > 0 && (
            <div className="mt-6 text-left">
              <Notice tone="danger" title="Some documents did not upload">
                {saved.uploadFailures.join(" ")}{" "}
                <Link href={`/families?family=${saved.family_id}`} className="font-medium text-accent underline">
                  Add them again
                </Link>
              </Notice>
            </div>
          )}
          {saved.warnings.length > 0 && (
            <div className="mt-6 text-left">
              <Notice tone="warning" title="Still to find out">
                {saved.warnings.join(". ")}. This is on the list of families with missing details.
              </Notice>
            </div>
          )}
          <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
            <button onClick={startAgain} className={buttonPrimary}>
              Add another family
            </button>
            <Link href={`/families?family=${saved.family_id}`} className={buttonSecondary}>
              See this family
            </Link>
            <Link href={`/cea/${saved.family_id}`} className={buttonSecondary}>
              Check CEA for this family
            </Link>
            <Link href="/" className={buttonSecondary}>
              Go to Home
            </Link>
          </div>
        </div>
      </AppShell>
    );
  }

  // ---------- the form ----------
  return (
    <AppShell>
      <div ref={top} />
      <PageHeader
        title="Add a family"
        intro="Fill in what you know. Only the soldier's name, the next of kin's name and one document are needed — everything else can be added later."
      />

      {message && matches.length === 0 && (
        <div className="mb-6">
          <Notice tone="danger" title={message}>
            {Object.keys(errors).length > 0 && (
              <ul className="mt-1 list-disc pl-5">
                {Object.values(errors).map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            )}
          </Notice>
        </div>
      )}

      {matches.length > 0 && (
        <div className="mb-6 rounded-2xl border border-warning/60 bg-surface p-4 sm:p-5">
          <p className="text-[18px] font-semibold text-warning">Is this a family you already have?</p>
          <p className="mt-1 text-[16px] text-muted">
            This looks very like a family that is already in the system. Please check before saving.
          </p>
          <ul className="mt-4 space-y-2">
            {matches.map((m) => (
              <li key={m.family_id} className="rounded-xl bg-bg px-4 py-3">
                <p className="text-[17px] font-medium">
                  {m.primary_contact_name}
                  {m.soldier_name && <span className="text-muted"> · w/o {m.soldier_name}</span>}
                </p>
                <p className="text-[15px] text-muted">
                  {m.family_code}
                  {m.district && ` · ${m.district}`} · {m.reasons.join(", ")}
                </p>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex flex-col gap-3 sm:flex-row">
            <button onClick={() => setMatches([])} className={buttonSecondary}>
              Go back and check
            </button>
            <button onClick={() => save(true)} disabled={saving} className={buttonPrimary}>
              It&rsquo;s a different family — save it
            </button>
          </div>
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          save();
        }}
        className="space-y-6"
        noValidate
      >
        <Card>
          <SectionTitle step={1} title="The soldier" />
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Soldier's name" required autoCapitalize="words" placeholder="e.g. Rajesh Kumar" className="sm:col-span-2" {...field("soldier_name")} />
            <Field label="Rank" placeholder="e.g. Havildar" {...field("rank")} />
            <Field label="Army number" placeholder="e.g. 15123456K" {...field("service_number")} />
            <Field label="Unit" placeholder="e.g. 14 Jat" {...field("unit")} />
            <Field label="Date of death" date {...field("date_of_death")} />
            <Field
              label="How did he die?"
              placeholder="e.g. Road accident, illness, in action"
              className="sm:col-span-2"
              {...field("cause_of_death")}
            />
          </div>
        </Card>

        <Card>
          <SectionTitle step={2} title="Next of kin" hint="Usually the widow — the person you will speak to." />
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Name" required autoCapitalize="words" placeholder="e.g. Sunita Devi" className="sm:col-span-2" {...field("widow_name")} />
            <div className="sm:col-span-2">
              <Choice
                label="Relationship to the soldier"
                value={values.nok_relationship ?? ""}
                options={["Wife", "Mother", "Father", "Other"].map((v) => ({ value: v, label: v }))}
                onChange={(v) => setValues((prev) => ({ ...prev, nok_relationship: v }))}
              />
            </div>
            <Field label="Mobile number" inputMode="tel" placeholder="e.g. 98765 43210" hint="10 digits. +91 is added for you." {...field("phone")} />
            <Field label="Another number" inputMode="tel" placeholder="If there is one" {...field("alternate_phone")} />
          </div>
        </Card>

        <Card>
          <SectionTitle step={3} title="Where the family lives" />
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Village" {...field("village_or_town")} />
            <Field label="Town" {...field("town")} />
            <Field label="Post office" {...field("post_office")} />
            <Field label="Tehsil" {...field("tehsil")} />
            <Field label="District" {...field("district")} />
            <div>
              <Field label="State" placeholder="Start typing…" list="states" {...field("state")} />
              {/* The browser suggests states as he types; any text is still accepted. */}
              <datalist id="states">
                {STATES.map((s) => (
                  <option key={s} value={s} />
                ))}
              </datalist>
            </div>
            <Field label="PIN code" inputMode="numeric" placeholder="6 digits" {...field("pincode")} />
          </div>
        </Card>

        <Card>
          <SectionTitle
            step={4}
            title="Children"
            hint="School details help with education grants like CEA. Leave a box empty if you don't know."
          />
          <div className="space-y-4">
            {children.map((child, index) => (
              <div key={index} className="rounded-2xl border border-border bg-bg p-4 sm:p-5">
                <div className="mb-4 flex items-center justify-between gap-2">
                  <p className="min-w-0 truncate text-[17px] font-semibold">
                    {child.name.trim() || `Child ${index + 1}`}
                  </p>
                  <button
                    type="button"
                    onClick={() => setChildren((prev) => prev.filter((_, i) => i !== index))}
                    className="-mr-2 min-h-11 shrink-0 rounded-full px-3 text-[15px] text-muted hover:bg-surface-2 hover:text-danger"
                  >
                    Remove
                  </button>
                </div>
                <div className="grid gap-5 sm:grid-cols-2">
                  <Field
                    label="Name"
                    autoCapitalize="words"
                    value={child.name}
                    onChange={(v) => setChild(index, { name: v })}
                    error={errors[`children.${index}.name`]}
                  />
                  <Field
                    label="Date of birth"
                    date
                    value={child.date_of_birth}
                    onChange={(v) => setChild(index, { date_of_birth: v })}
                    error={errors[`children.${index}.date_of_birth`]}
                  />
                  <div className="sm:col-span-2">
                    <Choice
                      label="Boy or girl"
                      value={child.sex}
                      options={[
                        { value: "M", label: "Boy" },
                        { value: "F", label: "Girl" },
                      ]}
                      onChange={(v) => setChild(index, { sex: v })}
                      error={errors[`children.${index}.sex`]}
                    />
                  </div>
                  <Field
                    label="Class"
                    placeholder="e.g. Class 8, UKG, B.A. 1st year"
                    value={child.current_class}
                    onChange={(v) => setChild(index, { current_class: v })}
                  />
                  <Field
                    label="School or college"
                    value={child.school_name}
                    onChange={(v) => setChild(index, { school_name: v })}
                  />
                  <Field
                    label="Where is the school?"
                    placeholder="Town or city"
                    value={child.school_place}
                    onChange={(v) => setChild(index, { school_place: v })}
                  />
                  <div className="space-y-2 sm:col-span-2 sm:grid sm:grid-cols-2 sm:gap-3 sm:space-y-0">
                    <Checkbox
                      label="Stays in a hostel"
                      checked={child.is_hostel}
                      onChange={(v) => setChild(index, { is_hostel: v })}
                    />
                    <Checkbox
                      label="Has a disability (divyang)"
                      checked={child.has_disability}
                      onChange={(v) => setChild(index, { has_disability: v })}
                    />
                  </div>
                </div>
              </div>
            ))}
            <button
              type="button"
              onClick={() => setChildren((prev) => [...prev, emptyChild()])}
              className={`${buttonSecondary} w-full sm:w-auto`}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
              {children.length === 0 ? "Add a child" : "Add another child"}
            </button>
          </div>
        </Card>

        <div ref={documentsCard}>
          <Card className={documentsError ? "border-danger/60" : ""}>
            <SectionTitle
              step={5}
              title="Documents"
              hint="At least 1, up to 4. For example the death certificate, PPO, Aadhaar or bank passbook."
            />
            <DocumentPicker
              value={documents}
              onChange={(next) => {
                setDocuments(next);
                if (next.length >= MIN_DOCUMENTS) setDocumentsError(null);
              }}
              error={documentsError ?? undefined}
            />
          </Card>
        </div>

        <Card>
          <button
            type="button"
            onClick={() => setShowBank((v) => !v)}
            aria-expanded={showBank}
            className="flex min-h-12 w-full items-center justify-between gap-3 text-left"
          >
            <span className="flex items-start gap-3">
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-soft text-[15px] font-semibold text-accent">
                6
              </span>
              <span>
                <span className="block text-xl font-semibold">Pension and bank</span>
                <span className="block text-[15px] text-muted">Optional — needed later to send money.</span>
              </span>
            </span>
            <span className="shrink-0 text-[16px] text-accent underline">{showBank ? "Hide" : "Add"}</span>
          </button>
          {showBank && (
            <div className="mt-5 grid gap-5 sm:grid-cols-2">
              <Field label="PPO number" {...field("ppo_number")} />
              <Field label="Account holder's name" autoCapitalize="words" {...field("bank_account_holder")} />
              <Field label="Bank name" placeholder="e.g. State Bank of India" {...field("bank_name")} />
              <Field label="Branch" {...field("bank_branch")} />
              <Field label="Account number" inputMode="numeric" {...field("bank_account_number")} />
              <Field label="IFSC code" autoCapitalize="characters" placeholder="e.g. SBIN0001234" {...field("bank_ifsc")} />
            </div>
          )}
        </Card>

        <div className="pb-safe sticky bottom-0 z-10 -mx-4 flex flex-col gap-2 border-t border-border bg-bg/95 px-4 pt-3 backdrop-blur sm:mx-0 sm:flex-row sm:items-center sm:gap-3 sm:rounded-2xl sm:border sm:py-4">
          <button type="submit" disabled={saving} className={`${buttonPrimary} w-full sm:w-auto`}>
            {saving ? progress ?? "Saving…" : "Save family"}
          </button>
          <p className="hidden text-[15px] text-muted sm:block">You can change any of this later. Old values are always kept.</p>
        </div>
      </form>
    </AppShell>
  );
}

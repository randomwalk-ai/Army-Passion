"use client";

/** One family's CEA claim: pre-filled, checked by him, saved, downloaded. */

import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import AppShell from "@/components/AppShell";
import CeaStatusBadge from "@/components/CeaStatusBadge";
import {
  Card,
  Checkbox,
  Choice,
  Field,
  Notice,
  PageHeader,
  SectionTitle,
  Spinner,
  buttonPrimary,
  buttonSecondary,
  errorText,
} from "@/components/ui";
import {
  FormRejected,
  downloadCeaPdf,
  getCeaForm,
  rupees,
  saveCeaForm,
  type CeaChildForm,
  type CeaFamily,
  type CeaForm,
} from "@/lib/api";

/** The same checks the server makes, so the list updates as he types. */
function stillEmpty(form: CeaForm): string[] {
  const missing: string[] = [];
  const need: [string, string][] = [
    ["Name of next of kin", form.nok_name],
    ["Soldier's rank", form.soldier_rank],
    ["Army number", form.service_number],
    ["Unit", form.unit],
    ["Record office", form.record_office],
    ["PIN code (permanent address)", form.permanent_pincode],
    ["Mobile number", form.mobile],
    ["Bank name", form.bank_name],
    ["Account number", form.bank_account_number],
    ["IFSC code", form.bank_ifsc],
  ];
  for (const [label, value] of need) if (!value?.trim()) missing.push(label);
  if (form.children.length === 0) missing.push("A child to claim for");
  for (const child of form.children) {
    const first = child.name.split(" ")[0] || "Child";
    if (!child.current_class.trim()) missing.push(`${first}: class`);
    if (!child.school_name.trim()) missing.push(`${first}: school name`);
    if (!child.school_place.trim()) missing.push(`${first}: school place`);
  }
  return missing;
}

function Amount({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <Field
      label={label}
      inputMode="numeric"
      value={value ? value.toLocaleString("en-IN") : ""}
      onChange={(v) => onChange(Number(v.replace(/\D/g, "")) || 0)}
      placeholder="0"
    />
  );
}

function ClaimForm() {
  const params = useParams<{ familyId: string }>();
  const year = useSearchParams().get("year") ?? undefined;
  const familyId = Number(params.familyId);

  const [form, setForm] = useState<CeaForm | null>(null);
  const [saved, setSaved] = useState<string>(""); // the form as last loaded or saved
  const [family, setFamily] = useState<CeaFamily | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<"saving" | "downloading" | null>(null);
  const [message, setMessage] = useState<{ tone: "success" | "danger"; title: string; body?: string } | null>(null);

  useEffect(() => {
    getCeaForm(familyId, year)
      .then((d) => {
        setForm(d.form);
        setSaved(JSON.stringify(d.form));
        setFamily(d.family);
      })
      .catch((e) => setLoadError(errorText(e)));
  }, [familyId, year]);

  const missing = useMemo(() => (form ? stillEmpty(form) : []), [form]);
  const dirty = form !== null && JSON.stringify(form) !== saved;
  const total = form?.children.reduce((sum, c) => sum + (c.cea_amount || 0) + (c.hostel_amount || 0), 0) ?? 0;

  const set = (change: Partial<CeaForm>) => setForm((f) => (f ? { ...f, ...change } : f));
  const text = (key: keyof CeaForm) => ({
    value: (form?.[key] as string) ?? "",
    onChange: (v: string) => set({ [key]: v } as Partial<CeaForm>),
    error: errors[key as string],
  });
  const setChild = (index: number, change: Partial<CeaChildForm>) =>
    setForm((f) =>
      f ? { ...f, children: f.children.map((c, i) => (i === index ? { ...c, ...change } : c)) } : f,
    );

  /** Save his edits into the family's record. Returns the saved form, or null. */
  async function save(): Promise<CeaForm | null> {
    if (!form) return null;
    setErrors({});
    try {
      const before = JSON.parse(saved) as CeaForm;
      const result = await saveCeaForm(form);
      let next = result.form;
      // Ticking "hostel" changes what can be claimed: fetch the new amounts.
      const hostelChanged = form.children.some(
        (c, i) => before.children[i] && before.children[i].is_hostel !== c.is_hostel,
      );
      if (hostelChanged) {
        const fresh = await getCeaForm(familyId, form.academic_year);
        next = {
          ...next,
          children: next.children.map((c, i) =>
            before.children[i]?.is_hostel !== c.is_hostel && fresh.form.children[i]
              ? { ...c, cea_amount: fresh.form.children[i].cea_amount, hostel_amount: fresh.form.children[i].hostel_amount }
              : c,
          ),
        };
      }
      setForm(next);
      setSaved(JSON.stringify(next));
      return next;
    } catch (e) {
      if (e instanceof FormRejected) {
        setErrors(e.fieldErrors);
        setMessage({ tone: "danger", title: "Please check the form", body: Object.values(e.fieldErrors).join(" ") || e.message });
      } else {
        setMessage({ tone: "danger", title: "Could not save", body: errorText(e) });
      }
      return null;
    }
  }

  async function onSave() {
    setBusy("saving");
    setMessage(null);
    const before = saved;
    const next = await save();
    if (next) {
      setMessage({
        tone: "success",
        title: before === JSON.stringify(next) ? "Nothing new to save" : "Saved to the family's record",
        body: "Old values are kept in the history.",
      });
    }
    setBusy(null);
  }

  async function onDownload() {
    if (!form) return;
    setBusy("downloading");
    setMessage(null);
    const ready = dirty ? await save() : form;
    if (ready) {
      try {
        const blob = await downloadCeaPdf(ready);
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `CEA ${ready.academic_year} - ${ready.nok_name || "claim"}.pdf`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 10_000);
        setMessage({
          tone: "success",
          title: "The claim form has been downloaded",
          body: "Print it, get it signed by the next of kin and the school principal, and attach the cancelled cheque.",
        });
      } catch (e) {
        setMessage({ tone: "danger", title: "Could not make the PDF", body: errorText(e) });
      }
    }
    setBusy(null);
  }

  if (loadError) {
    return (
      <>
        <PageHeader title="CEA claim" back={{ href: "/cea", label: "All CEA claims" }} />
        <Notice tone="danger" title="This claim could not be opened">
          {loadError}
        </Notice>
      </>
    );
  }
  if (!form || !family) return <Spinner label="Filling in the form from the records…" />;

  return (
    <>
      <PageHeader
        title={`CEA claim for ${form.nok_name}`}
        back={{ href: "/cea", label: "All CEA claims" }}
        intro={
          <>
            Academic year <span className="font-semibold text-text">{form.academic_year}</span>. Everything below is
            filled in from the records. Check it, fill any gaps, then download the form.
          </>
        }
      />

      {/* ---------- the verdict ---------- */}
      <Card className="mb-6">
        <div className="flex flex-wrap items-center gap-3">
          <CeaStatusBadge status={family.status} label={family.status_label} />
          <p className="text-[16px] text-muted">{family.reasons.join(" ")}</p>
        </div>
        {family.children.length > 0 && (
          <ul className="mt-4 space-y-2">
            {family.children.map((c, i) => (
              <li key={`${c.member_id}-${i}`} className="rounded-xl bg-bg px-4 py-3">
                <p className="text-[16px]">
                  <span className="font-semibold">{c.name}</span>
                  <span className="text-muted"> — {c.status_label.toLowerCase()}. {c.reasons.join(" ")}</span>
                </p>
                {c.to_confirm.length > 0 && (
                  <p className="mt-0.5 text-[15px] text-warning">{c.to_confirm.join(" ")}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      {missing.length > 0 && (
        <div className="mb-6">
          <Notice tone="warning" title={`${missing.length} box${missing.length === 1 ? " is" : "es are"} still empty`}>
            {missing.join(" · ")}. You can still download the form and fill these by hand.
          </Notice>
        </div>
      )}

      <div className="space-y-6">
        <Card>
          <SectionTitle step={1} title="The soldier and next of kin" />
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Name of next of kin" prefilled {...text("nok_name")} />
            <Field label="Soldier's name" prefilled {...text("soldier_name")} />
            <Field label="Rank" prefilled {...text("soldier_rank")} />
            <Field label="Army number" prefilled {...text("service_number")} />
            <Field label="Unit" prefilled className="sm:col-span-2" {...text("unit")} />
          </div>
        </Card>

        <Card>
          <SectionTitle
            step={2}
            title="Children claimed for"
            hint="Only the two eldest children can claim. The amounts are worked out from the rules — change them only if the school's figures differ."
          />
          {form.children.length === 0 ? (
            <p className="text-[16px] text-muted">No child on record can claim for this year.</p>
          ) : (
            <div className="space-y-4">
              {form.children.map((child, index) => (
                <div key={child.member_id ?? index} className="rounded-2xl border border-border bg-bg p-4 sm:p-5">
                  <p className="mb-4 text-[18px] font-semibold">
                    {index === 0 ? "1st child" : "2nd child"}: {child.name}
                  </p>
                  <div className="grid gap-5 sm:grid-cols-2">
                    <Field label="Name" prefilled value={child.name} onChange={(v) => setChild(index, { name: v })} />
                    <Field
                      label="Date of birth"
                      date
                      prefilled
                      value={child.date_of_birth}
                      onChange={(v) => setChild(index, { date_of_birth: v })}
                      error={errors[`children.${index}.date_of_birth`]}
                    />
                    <Field label="Class" placeholder="e.g. Class 8" prefilled value={child.current_class} onChange={(v) => setChild(index, { current_class: v })} />
                    <Field label="Section" placeholder="e.g. B" value={child.section} onChange={(v) => setChild(index, { section: v })} />
                    <Field label="School name" prefilled value={child.school_name} onChange={(v) => setChild(index, { school_name: v })} />
                    <Field label="School's town or city" prefilled value={child.school_place} onChange={(v) => setChild(index, { school_place: v })} />
                    <Field label="Board" placeholder="e.g. CBSE, State Board" value={child.school_board} onChange={(v) => setChild(index, { school_board: v })} />
                    <Field label="School affiliation code" value={child.school_affiliation_code} onChange={(v) => setChild(index, { school_affiliation_code: v })} />
                    <Field label="Admission number" value={child.admission_number} onChange={(v) => setChild(index, { admission_number: v })} />
                    <Field label="Roll number" value={child.roll_number} onChange={(v) => setChild(index, { roll_number: v })} />
                    <div className="sm:col-span-2">
                      <Checkbox
                        label="Stays in the school hostel"
                        hint="Adds the hostel subsidy. Press Save to update the amount."
                        checked={child.is_hostel}
                        onChange={(v) => setChild(index, { is_hostel: v })}
                      />
                    </div>
                    <Field label="Claim from" date value={child.period_from} onChange={(v) => setChild(index, { period_from: v })} />
                    <Field label="Claim to" date value={child.period_to} onChange={(v) => setChild(index, { period_to: v })} />
                    <Amount label="CEA amount (₹)" value={child.cea_amount} onChange={(v) => setChild(index, { cea_amount: v })} />
                    <Amount label="Hostel amount (₹)" value={child.hostel_amount} onChange={(v) => setChild(index, { hostel_amount: v })} />
                  </div>
                  <p className="mt-4 text-right text-[17px]">
                    Total for {child.name.split(" ")[0]}:{" "}
                    <span className="font-semibold tabular-nums">{rupees(child.cea_amount + child.hostel_amount)}</span>
                  </p>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <SectionTitle step={3} title="Record office" hint="Where the claim is sent. For JCOs and ORs, the soldier's own Record Office." />
          <div className="grid gap-5 sm:grid-cols-3">
            <Field label="Name and address" multiline placeholder="e.g. The Records, The Jat Regiment, Bareilly Cantt" className="sm:col-span-2" {...text("record_office")} />
            <Field label="PIN code" inputMode="numeric" {...text("record_office_pincode")} />
          </div>
        </Card>

        <Card>
          <SectionTitle step={4} title="Address and phone" />
          <div className="grid gap-5 sm:grid-cols-3">
            <Field label="Permanent address" multiline prefilled className="sm:col-span-2" {...text("home_address")} />
            <Field label="PIN code" inputMode="numeric" prefilled {...text("permanent_pincode")} />
            <Field label="Address for letters" multiline prefilled hint="Change only if letters should go somewhere else." className="sm:col-span-2" {...text("correspondence_address")} />
            <Field label="PIN code" inputMode="numeric" prefilled {...text("correspondence_pincode")} />
            <Field label="Mobile number" inputMode="tel" prefilled {...text("mobile")} />
          </div>
        </Card>

        <Card>
          <SectionTitle step={5} title="Bank details" hint="The money is paid here. A cancelled cheque of this account goes with the claim." />
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Account holder's name" prefilled {...text("bank_account_holder")} />
            <Field label="Bank name" prefilled {...text("bank_name")} />
            <Field label="Branch" prefilled {...text("bank_branch")} />
            <Field label="Bank address" {...text("bank_address")} />
            <Field label="Account number" inputMode="numeric" prefilled {...text("bank_account_number")} />
            <Field label="IFSC code" prefilled {...text("bank_ifsc")} />
          </div>
        </Card>

        <Card>
          <SectionTitle step={6} title="Declaration" />
          <div className="grid gap-5 sm:grid-cols-2">
            <Choice
              label="Is the next of kin a government servant?"
              value={form.nok_is_govt_servant === null ? "" : form.nok_is_govt_servant ? "yes" : "no"}
              options={[
                { value: "yes", label: "Yes" },
                { value: "no", label: "No" },
              ]}
              onChange={(v) => set({ nok_is_govt_servant: v === "" ? null : v === "yes" })}
            />
            <Field label="Date on the form" date {...text("dated")} />
          </div>
        </Card>
      </div>

      {/* ---------- always in reach ---------- */}
      <div className="sticky bottom-0 -mx-4 mt-8 border-t border-border bg-bg/95 px-4 py-4 backdrop-blur sm:mx-0 sm:rounded-2xl sm:border">
        {message && (
          <div className="mb-3">
            <Notice tone={message.tone} title={message.title}>
              {message.body}
            </Notice>
          </div>
        )}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <p className="text-[17px] sm:mr-auto">
            Total claim: <span className="text-2xl font-semibold tabular-nums">{rupees(total)}</span>
          </p>
          <button onClick={onSave} disabled={busy !== null || !dirty} className={buttonSecondary}>
            {busy === "saving" ? "Saving…" : dirty ? "Save changes" : "Saved"}
          </button>
          <button onClick={onDownload} disabled={busy !== null} className={buttonPrimary}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M12 4v12m0 0l-5-5m5 5l5-5M5 20h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            {busy === "downloading" ? "Preparing the PDF…" : "Download PDF"}
          </button>
        </div>
      </div>
    </>
  );
}

export default function ClaimPage() {
  return (
    <AppShell>
      {/* The year comes from the address bar, which is only known in the browser. */}
      <Suspense fallback={<Spinner label="Opening the claim…" />}>
        <ClaimForm />
      </Suspense>
    </AppShell>
  );
}

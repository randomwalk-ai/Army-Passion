"use client";

/** Small pieces shared by every page, so they all look and behave alike. */

import Link from "next/link";
import { useId } from "react";

export const buttonPrimary =
  "inline-flex items-center justify-center gap-2 rounded-full bg-accent px-6 py-3 text-[17px] font-semibold " +
  "text-accent-fg shadow-sm transition hover:opacity-90 disabled:cursor-not-allowed disabled:bg-surface-2 " +
  "disabled:text-muted disabled:shadow-none";

export const buttonSecondary =
  "inline-flex items-center justify-center gap-2 rounded-full border border-border bg-bg px-6 py-3 " +
  "text-[17px] font-medium transition hover:bg-surface-2 disabled:cursor-not-allowed disabled:text-muted";

export function PageHeader({
  title,
  intro,
  back,
}: {
  title: string;
  intro?: React.ReactNode;
  back?: { href: string; label: string };
}) {
  return (
    <div className="mb-8">
      {back && (
        <Link
          href={back.href}
          className="mb-4 inline-flex items-center gap-1.5 text-[16px] text-muted hover:text-text"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M15 6l-6 6 6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          {back.label}
        </Link>
      )}
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{title}</h1>
      {intro && <p className="mt-3 max-w-2xl text-lg leading-relaxed text-muted">{intro}</p>}
    </div>
  );
}

export function Card({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-2xl border border-border bg-surface p-5 sm:p-6 ${className}`}>
      {children}
    </section>
  );
}

export function SectionTitle({ step, title, hint }: { step?: number; title: string; hint?: string }) {
  return (
    <div className="mb-5 flex items-start gap-3">
      {step !== undefined && (
        <span
          className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-soft
            text-[15px] font-semibold text-accent"
          aria-hidden="true"
        >
          {step}
        </span>
      )}
      <div>
        <h2 className="text-xl font-semibold">{title}</h2>
        {hint && <p className="mt-0.5 text-[15px] text-muted">{hint}</p>}
      </div>
    </div>
  );
}

type FieldProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  error?: string;
  placeholder?: string;
  required?: boolean;
  multiline?: boolean;
  inputMode?: React.HTMLAttributes<HTMLInputElement>["inputMode"];
  /** For dates: adds the dashes while he types, DD-MM-YYYY. */
  date?: boolean;
  autoComplete?: string;
  className?: string;
  /** Marks a box the system filled in, so he knows to check it. */
  prefilled?: boolean;
  /** id of a <datalist> to suggest values from. */
  list?: string;
};

/** "05062013" -> "05-06-2013". Lets him type a date with digits only. */
export function formatDateTyping(raw: string): string {
  const digits = raw.replace(/\D/g, "").slice(0, 8);
  if (digits.length <= 2) return digits;
  if (digits.length <= 4) return `${digits.slice(0, 2)}-${digits.slice(2)}`;
  return `${digits.slice(0, 2)}-${digits.slice(2, 4)}-${digits.slice(4)}`;
}

export function Field({
  label,
  value,
  onChange,
  hint,
  error,
  placeholder,
  required,
  multiline,
  inputMode,
  date,
  autoComplete = "off",
  className = "",
  prefilled,
  list,
}: FieldProps) {
  const id = useId();
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  const base =
    "w-full rounded-xl border bg-bg px-4 py-3 text-[17px] outline-none transition " +
    "placeholder:text-muted/70 focus:border-accent focus:ring-4 focus:ring-accent/15 " +
    (error ? "border-danger" : "border-border");

  return (
    <div className={className}>
      <label htmlFor={id} className="mb-1.5 flex items-baseline gap-2 text-[16px] font-medium">
        {label}
        {required && <span className="text-sm font-normal text-muted">(needed)</span>}
        {prefilled && value && (
          <span className="ml-auto text-xs font-normal text-accent">from records</span>
        )}
      </label>
      {multiline ? (
        <textarea
          id={id}
          value={value}
          rows={3}
          placeholder={placeholder}
          aria-invalid={Boolean(error)}
          aria-describedby={describedBy}
          onChange={(e) => onChange(e.target.value)}
          className={`${base} resize-y leading-relaxed`}
        />
      ) : (
        <input
          id={id}
          value={value}
          placeholder={placeholder ?? (date ? "DD-MM-YYYY" : undefined)}
          inputMode={date ? "numeric" : inputMode}
          autoComplete={autoComplete}
          list={list}
          aria-invalid={Boolean(error)}
          aria-describedby={describedBy}
          onChange={(e) => onChange(date ? formatDateTyping(e.target.value) : e.target.value)}
          className={base}
        />
      )}
      {error ? (
        <p id={`${id}-error`} className="mt-1.5 text-[15px] text-danger">
          {error}
        </p>
      ) : (
        hint && (
          <p id={`${id}-hint`} className="mt-1.5 text-[14px] text-muted">
            {hint}
          </p>
        )
      )}
    </div>
  );
}

/** Two or three big buttons instead of a dropdown, for short choices. */
export function Choice<T extends string>({
  label,
  value,
  options,
  onChange,
  error,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  error?: string;
}) {
  return (
    <fieldset>
      <legend className="mb-1.5 text-[16px] font-medium">{label}</legend>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => {
          const selected = option.value === value;
          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={selected}
              onClick={() => onChange(selected ? ("" as T) : option.value)}
              className={`min-w-[5.5rem] rounded-xl border px-4 py-3 text-[17px] transition
                ${
                  selected
                    ? "border-accent bg-accent-soft font-semibold text-text"
                    : "border-border bg-bg text-muted hover:bg-surface-2 hover:text-text"
                }`}
            >
              {option.label}
            </button>
          );
        })}
      </div>
      {error && <p className="mt-1.5 text-[15px] text-danger">{error}</p>}
    </fieldset>
  );
}

export function Checkbox({
  label,
  checked,
  onChange,
  hint,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  hint?: string;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-border bg-bg px-4 py-3 hover:bg-surface-2">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-1 h-5 w-5 shrink-0 accent-[var(--accent)]"
      />
      <span>
        <span className="text-[17px]">{label}</span>
        {hint && <span className="block text-[14px] text-muted">{hint}</span>}
      </span>
    </label>
  );
}

export function Notice({
  tone = "info",
  title,
  children,
}: {
  tone?: "info" | "success" | "warning" | "danger";
  title: string;
  children?: React.ReactNode;
}) {
  const styles = {
    info: "border-border bg-surface",
    success: "border-accent bg-accent-soft",
    warning: "border-warning/60 bg-surface",
    danger: "border-danger/60 bg-surface",
  }[tone];
  const titleColor = {
    info: "text-text",
    success: "text-text",
    warning: "text-warning",
    danger: "text-danger",
  }[tone];
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={`rounded-2xl border px-5 py-4 ${styles}`}>
      <p className={`text-[17px] font-semibold ${titleColor}`}>{title}</p>
      {children && <div className="mt-1 text-[16px] leading-relaxed text-muted">{children}</div>}
    </div>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 py-10 text-[17px] text-muted" role="status">
      <svg className="h-6 w-6 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" opacity="0.25" />
        <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      </svg>
      {label}
    </div>
  );
}

export const OFFLINE_MESSAGE =
  "I could not reach the server. Please check that the backend is running, then try again.";

export function errorText(error: unknown): string {
  if (error instanceof TypeError) return OFFLINE_MESSAGE; // fetch failed outright
  return error instanceof Error ? error.message : OFFLINE_MESSAGE;
}

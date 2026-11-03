"use client";

/** All families as one table, like his Excel sheet: view it, or switch on Editing to correct it. */

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import AppShell from "@/components/AppShell";
import FamilyTable from "@/components/FamilyTable";
import { PageHeader, Spinner, buttonPrimary } from "@/components/ui";

function Table() {
  const params = useSearchParams();
  const family = Number(params.get("family")) || undefined;
  return <FamilyTable initialFilter={params.get("filter") ?? "all"} openFamilyId={family} />;
}

export default function FamiliesPage() {
  return (
    <AppShell wide>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <PageHeader
          title="All families"
          intro="Everything in the database, like your Excel sheet. Switch on Editing to correct a value. The old value is always kept."
        />
        <Link href="/families/new" className={`${buttonPrimary} -mt-2 mb-6 w-full shrink-0 sm:mt-1 sm:w-auto`}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          Add a family
        </Link>
      </div>
      {/* The filter and family come from the address bar, which is only known in the browser. */}
      <Suspense fallback={<Spinner label="Loading the families…" />}>
        <Table />
      </Suspense>
    </AppShell>
  );
}

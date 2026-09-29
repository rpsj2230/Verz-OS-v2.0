/**
 * The departments the staff source names that this install has not created, and the one confirmed
 * act that creates them.
 *
 * Found on the owner's install on 2026-09-29: Lark named eleven departments, the staff sync placed
 * people in them, and this screen showed none, because nothing created a department from a source.
 * The API offers each name with the short name it would get, only to a reader who may create
 * departments and only for names no department here already answers to
 * (`brain.govern_people_routes.source_departments`); pressing asks first, lists every name, and sends
 * the short names that were listed. Each department is created with its scope by the same write the
 * New department drawer uses and recorded in the audit ledger under the reader. Nothing else changes:
 * nobody is moved and no grant is written here; the next staff sync places people in them.
 *
 * Names and never a count, for the page's own reason.
 *
 * Task ids: M27.7.4, M27.11.1
 */

import { useCallback, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, FailureState, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  readFounded,
  readSourceDepartments,
  SOURCE_DEPARTMENTS_API_PATH,
  type SourceDepartment,
} from "./departmentsQuery";

export const SOURCE_DEPARTMENTS_HEADING = "Departments your staff source names";
export const SOURCE_DEPARTMENTS_LEDE =
  "Your staff list places people in these departments, and no department here has these names yet. Create them so the staff sync can place people in them.";
export const CREATE_FROM_SOURCE = "Create the departments your staff source names";
export const CREATE_FROM_SOURCE_QUESTION = "Create these departments?";
export const CREATE_FROM_SOURCE_CONSEQUENCE =
  "Each is created with the scope it is defined by and recorded in the audit ledger under your name. Nobody is moved and no access is given now: the next staff sync places people in them.";
export const KEEP_AS_IS = "Not now";

function named(one: SourceDepartment): string {
  return `${one.name} (short name ${one.slug})`;
}

export function SourceDepartments({ version, onWritten }: { readonly version: number; readonly onWritten: () => void }) {
  const answer = useResource<unknown>(SOURCE_DEPARTMENTS_API_PATH, version);
  const offered = readSourceDepartments(answer.data);
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [told, setTold] = useState("");

  const go = useCallback(() => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(SOURCE_DEPARTMENTS_API_PATH, {
        method: "POST",
        body: { slugs: offered.to_found.map((one) => one.slug) },
      });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setAsking(false);
      const { created, missed } = readFounded(result.data);
      setTold(
        [
          created.length === 0 ? "" : `Created ${created.map((one) => one.name).join(", ")}.`,
          missed.length === 0 ? "" : `Not created, because a department took the name first: ${missed.join(", ")}.`,
        ]
          .filter((one) => one !== "")
          .join(" "),
      );
      onWritten();
    })();
  }, [offered.to_found, onWritten]);

  if (offered.to_found.length === 0) {
    return told === "" ? null : (
      <div role="status">
        <Note kind="done">{told}</Note>
      </div>
    );
  }
  return (
    <SectionCard
      title={SOURCE_DEPARTMENTS_HEADING}
      lede={SOURCE_DEPARTMENTS_LEDE}
      action={
        <Button
          type="button"
          size="sm"
          className="min-h-11 sm:min-h-8"
          onClick={() => {
            setAsking(true);
          }}
        >
          {CREATE_FROM_SOURCE}
        </Button>
      }
    >
      <ul aria-label={SOURCE_DEPARTMENTS_HEADING} className="m-0 flex list-none flex-wrap gap-x-4 gap-y-1 p-0 text-[13px] text-ink">
        {offered.to_found.map((one) => (
          <li key={one.slug}>{one.name}</li>
        ))}
      </ul>
      <ConfirmDialog
        open={asking}
        question={CREATE_FROM_SOURCE_QUESTION}
        consequence={CREATE_FROM_SOURCE_CONSEQUENCE}
        details={
          <div className="flex min-w-0 flex-col gap-2">
            <ul aria-label="Departments to create" className="m-0 list-disc pl-5 text-[13px] text-ink">
              {offered.to_found.map((one) => (
                <li key={one.slug}>{named(one)}</li>
              ))}
            </ul>
            {failure === null ? null : <FailureState failure={failure} />}
          </div>
        }
        confirmLabel={CREATE_FROM_SOURCE}
        cancelLabel={KEEP_AS_IS}
        busy={busy}
        onConfirm={go}
        onCancel={() => {
          setFailure(null);
          setAsking(false);
        }}
      />
    </SectionCard>
  );
}

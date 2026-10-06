/**
 * Several people moved to one department, on an install whose departments are managed on People
 * (needs-rupash 115, M1.6.20). Offered only when the directory says `may_move`; the route asks again
 * about every person and the department, and moves all of them or nobody.
 *
 * **The departments offered are the Departments route's answer to this reader**, the same list the
 * Placements view draws teams from, so a department the reader may not see is not offered, and one
 * they see but may not organise is refused by the route in its one refusal.
 *
 * Task ids: M1.6.20
 */

import { useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, Drawer, FailureState } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Field, FormProblem, NativeSelect } from "../access/formParts";
import { DEPARTMENTS_API_PATH, PLACEMENT_CHANGES_NO_ACCESS } from "./PersonPlacements";
import type { PersonRow } from "./peopleQuery";

export const MOVING_API_PATH = "/govern/directory/department";
export const MOVE_SELECTED = "Move to a department";
export const MOVE_TITLE = "Move people to a department";
export const CHOOSE_A_DEPARTMENT = "Choose the department they go to.";
export const NOBODY_CHOSEN = "Choose the people to move first, on the list.";

export function moveQuestion(count: number, department: string): string {
  return `Move ${count === 1 ? "this person" : `these ${count} people`} to ${department}?`;
}

/** The live departments this reader is shown, as the Departments route sends them. */
export function readDepartments(payload: unknown): readonly { readonly slug: string; readonly name: string }[] {
  if (typeof payload !== "object" || payload === null) {
    return [];
  }
  const items = (payload as { items?: unknown }).items;
  if (!Array.isArray(items)) {
    return [];
  }
  return (items as readonly unknown[]).flatMap((one) => {
    const row = one as { slug?: unknown; name?: unknown };
    return typeof row.slug === "string" && typeof row.name === "string" ? [{ slug: row.slug, name: row.name }] : [];
  });
}

export function MoveDrawer({
  open,
  onOpenChange,
  chosen,
  onWritten,
}: {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly chosen: readonly PersonRow[];
  readonly onWritten: (told: string) => void;
}) {
  const departments = readDepartments(useResource<unknown>(open ? DEPARTMENTS_API_PATH : null).data);
  const [department, setDepartment] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const name = departments.find((one) => one.slug === department)?.name ?? department;

  const review = (event: FormEvent) => {
    event.preventDefault();
    const found = chosen.length === 0 ? NOBODY_CHOSEN : department === "" ? CHOOSE_A_DEPARTMENT : null;
    setProblem(found);
    if (found === null) {
      setFailure(null);
      setPending(true);
    }
  };

  const send = () => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(MOVING_API_PATH, {
        method: "POST",
        body: { principal_ids: chosen.map((one) => one.principalId), department },
      });
      setBusy(false);
      setPending(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      const told = (result.data as { told?: unknown } | null)?.told;
      setDepartment("");
      onOpenChange(false);
      onWritten(typeof told === "string" ? told : "");
    })();
  };

  return (
    <>
      <Drawer
        open={open}
        onOpenChange={onOpenChange}
        title={MOVE_TITLE}
        description={`Everybody selected, moved together or not at all. ${PLACEMENT_CHANGES_NO_ACCESS}`}
        footer={
          <>
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => {
                onOpenChange(false);
              }}
            >
              Cancel
            </Button>
            <Button type="submit" form="move-people" disabled={busy || pending}>
              Review the move
            </Button>
          </>
        }
      >
        <form id="move-people" noValidate className="flex flex-col gap-4" onSubmit={review}>
          <p className="m-0 text-[13px] text-body">
            {chosen.length === 0 ? "Nobody is selected." : chosen.map((one) => one.displayName).join(", ")}
          </p>
          <Field label="Department" hint="The departments you may see." problem={problem} apiProblems={failure?.problems ?? []} names={["department"]}>
            {({ id, describedBy, invalid }) => (
              <NativeSelect id={id} describedBy={describedBy} invalid={invalid} value={department} onChange={setDepartment}>
                <option value="">Choose a department</option>
                {departments.map((one) => (
                  <option key={one.slug} value={one.slug}>
                    {one.name}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          {problem === null ? null : <FormProblem>{problem}</FormProblem>}
          {failure === null ? null : <FailureState failure={failure} />}
        </form>
      </Drawer>
      <ConfirmDialog
        open={pending}
        question={moveQuestion(chosen.length, name)}
        consequence={PLACEMENT_CHANGES_NO_ACCESS}
        details={
          <ul className="m-0 flex list-none flex-col gap-1 p-0">
            {chosen.map((one) => (
              <li key={one.principalId}>{one.displayName}</li>
            ))}
          </ul>
        }
        confirmLabel="Move them"
        cancelLabel="Leave it"
        busy={busy}
        onConfirm={send}
        onCancel={() => {
          setPending(false);
        }}
      />
    </>
  );
}

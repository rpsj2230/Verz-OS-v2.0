/**
 * A person's Placements: the department they sit in, the teams they are in and the departments they
 * lead, with the acts that change them.
 *
 * **A placement changes nobody's access**, and every confirmation here says so in the API's terms: a
 * team is where somebody sits, and a lead is who leads a department, appointed by somebody else and
 * conferring nothing. What a person may see is still only what their grants say.
 *
 * **Every act is the Departments and teams screen's own route**, pressed from here:
 * `/govern/departments/membership` to place somebody in a team of their department or take them out,
 * and `/govern/departments/lead` to appoint or stand down. The routes ask
 * `brain.console.organisation.may_place`, `may_organise` and `may_appoint` about the rows as they
 * stand, whatever this drew; the controls are drawn only for a reader the API says may organise.
 * The teams offered are the department's own teams as the Departments route answers this reader.
 *
 * **The department a person sits in is the staff source's**, so it is not changed here; on an install
 * whose departments are managed on People it is changed on the list, several people at a time
 * (`MoveDrawer`), and the footer says so (M1.6.19).
 *
 * Task ids: M27.11.2, M27.16.1
 */

import { useCallback, useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, Drawer, FailureState, NotOffered, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { listPath, NO_QUESTION } from "../../components/listing";
import { Field, FormProblem, NativeSelect } from "../access/formParts";
import { DEPARTMENT_SET_ON_PEOPLE, EDITED_AT_THE_SOURCE } from "./peopleActions";
import type { PersonDetail } from "./peopleQuery";

export const DEPARTMENTS_API_PATH = "/govern/departments";
export const MEMBERSHIP_API_PATH = "/govern/departments/membership";
export const LEAD_API_PATH = "/govern/departments/lead";

export const PLACEMENT_CHANGES_NO_ACCESS =
  "Nobody's access changes: a team is where somebody sits and a lead confers nothing. What they may see is still only what their grants say.";

/** The department's own row on the Departments route, asked by its short name. */
export function departmentApiPath(slug: string): string {
  return listPath(DEPARTMENTS_API_PATH, { ...NO_QUESTION, filters: { slug } }, null, 1);
}

/** The teams of one department, out of the Departments route's answer. */
export function teamsIn(payload: unknown, slug: string): readonly { readonly slug: string; readonly name: string }[] {
  if (typeof payload !== "object" || payload === null) {
    return [];
  }
  const items = (payload as { items?: unknown }).items;
  if (!Array.isArray(items)) {
    return [];
  }
  for (const item of items as readonly unknown[]) {
    const row = item as { slug?: unknown; teams?: unknown };
    if (row.slug === slug && Array.isArray(row.teams)) {
      return (row.teams as readonly unknown[]).flatMap((one) => {
        const team = one as { slug?: unknown; name?: unknown };
        return typeof team.slug === "string" && typeof team.name === "string" ? [{ slug: team.slug, name: team.name }] : [];
      });
    }
  }
  return [];
}

type Act =
  | { readonly kind: "leave"; readonly department: string; readonly team: string; readonly teamName: string }
  | { readonly kind: "appoint"; readonly department: string; readonly departmentName: string }
  | { readonly kind: "stand_down"; readonly department: string; readonly departmentName: string };

function questionFor(act: Act, person: string): string {
  switch (act.kind) {
    case "leave":
      return `Take ${person} out of ${act.teamName}?`;
    case "appoint":
      return `Appoint ${person} as the lead of ${act.departmentName}?`;
    case "stand_down":
      return `Stand ${person} down as the lead of ${act.departmentName}?`;
  }
}

function labelFor(act: Act): string {
  switch (act.kind) {
    case "leave":
      return "Take out";
    case "appoint":
      return "Make lead";
    case "stand_down":
      return "Stand down";
  }
}

/** One placement act, pressed, confirmed in a dialog, and only then sent. */
function PlacementAct({
  act,
  person,
  principalId,
  onDone,
}: {
  readonly act: Act;
  readonly person: string;
  readonly principalId: string;
  readonly onDone: () => void;
}) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const go = useCallback(() => {
    setBusy(true);
    void (async () => {
      const result =
        act.kind === "leave"
          ? await request<unknown>(MEMBERSHIP_API_PATH, {
              method: "POST",
              body: { department: act.department, team: act.team, principal_id: principalId, change: "leave" },
            })
          : await request<unknown>(LEAD_API_PATH, {
              method: "POST",
              body:
                act.kind === "appoint"
                  ? { department: act.department, change: "appoint", principal_id: principalId }
                  : { department: act.department, change: "stand_down" },
            });
      setBusy(false);
      setAsking(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      onDone();
    })();
  }, [act, principalId, onDone]);
  const label = labelFor(act);
  return (
    <span className="flex flex-col items-end gap-1">
      <Button
        size="sm"
        variant="outline"
        onClick={() => {
          setFailure(null);
          setAsking(true);
        }}
      >
        {label}
      </Button>
      {failure === null ? null : <FailureState failure={failure} />}
      <ConfirmDialog
        open={asking}
        question={questionFor(act, person)}
        consequence={
          act.kind === "appoint"
            ? `${PLACEMENT_CHANGES_NO_ACCESS} Any current lead is stood down in the same change.`
            : PLACEMENT_CHANGES_NO_ACCESS
        }
        confirmLabel={label}
        cancelLabel="Leave it"
        busy={busy}
        onConfirm={go}
        onCancel={() => {
          setAsking(false);
        }}
      />
    </span>
  );
}

/** Placing the person in a team of their own department, chosen in a drawer. */
function AddToTeam({
  department,
  departmentName,
  already,
  principalId,
  person,
  onDone,
}: {
  readonly department: string;
  readonly departmentName: string;
  readonly already: ReadonlySet<string>;
  readonly principalId: string;
  readonly person: string;
  readonly onDone: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [team, setTeam] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);
  const answer = useResource<unknown>(open ? departmentApiPath(department) : null);
  const teams = useMemo(() => teamsIn(answer.data, department).filter((one) => !already.has(one.slug)), [answer.data, department, already]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (team === "") {
      setProblem("Choose the team to place them in; nothing has been sent.");
      return;
    }
    setProblem(null);
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(MEMBERSHIP_API_PATH, {
        method: "POST",
        body: { department, team, principal_id: principalId, change: "join" },
      });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setTeam("");
      setOpen(false);
      onDone();
    })();
  };

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        onClick={() => {
          setOpen(true);
        }}
      >
        Add to a team
      </Button>
      <Drawer
        open={open}
        onOpenChange={setOpen}
        title={`Add ${person} to a team`}
        description={`A team of ${departmentName}. ${PLACEMENT_CHANGES_NO_ACCESS}`}
        footer={
          <>
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => {
                setOpen(false);
              }}
            >
              Cancel
            </Button>
            <Button type="submit" form="add-to-team" disabled={busy}>
              Add to the team
            </Button>
          </>
        }
      >
        <form id="add-to-team" noValidate className="flex flex-col gap-4" onSubmit={submit}>
          <Field label="Team" hint="The teams of their department you may see." problem={problem} apiProblems={failure?.problems ?? []} names={["team"]}>
            {({ id, describedBy, invalid }) => (
              <NativeSelect id={id} describedBy={describedBy} invalid={invalid} value={team} onChange={setTeam}>
                <option value="">Choose a team</option>
                {teams.map((one) => (
                  <option key={one.slug} value={one.slug}>
                    {one.name}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          {answer.failure === null ? null : <FailureState failure={answer.failure} />}
          {problem === null ? null : <FormProblem>{problem}</FormProblem>}
          {failure === null ? null : <FailureState failure={failure} />}
        </form>
      </Drawer>
    </>
  );
}

export function PersonPlacements({ detail, onWritten }: { readonly detail: PersonDetail; readonly onWritten: () => void }) {
  const { person, placements, mayOrganise } = detail;
  const department = placements.department;
  const inTeams = new Set(placements.teams.filter((one) => one.department === department?.slug).map((one) => one.slug));
  const leads = new Set(placements.leads.map((one) => one.slug));

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <SectionCard
        title="Department"
        lede="Where they sit, as the staff source records it."
        footer={<NotOffered>{detail.departmentSetOnPeople ? DEPARTMENT_SET_ON_PEOPLE : EDITED_AT_THE_SOURCE}</NotOffered>}
        action={
          department !== undefined && mayOrganise && !leads.has(department.slug) ? (
            <PlacementAct
              act={{ kind: "appoint", department: department.slug, departmentName: department.name }}
              person={person.displayName}
              principalId={person.principalId}
              onDone={onWritten}
            />
          ) : undefined
        }
      >
        {department === undefined ? (
          <p className="m-0 text-[13px] text-dim">Not placed in a department you may see.</p>
        ) : (
          <Link to={`/departments/${encodeURIComponent(department.slug)}`} className="text-[13px] font-medium text-ink underline-offset-4 hover:underline">
            {department.name}
          </Link>
        )}
      </SectionCard>
      <SectionCard
        title="Teams"
        lede="A team is where somebody sits. It changes nobody's access."
        action={
          department !== undefined && mayOrganise ? (
            <AddToTeam
              department={department.slug}
              departmentName={department.name}
              already={inTeams}
              principalId={person.principalId}
              person={person.displayName}
              onDone={onWritten}
            />
          ) : undefined
        }
      >
        {placements.teams.length === 0 ? (
          <p className="m-0 text-[13px] text-dim">In no team you may see.</p>
        ) : (
          <ul className="m-0 flex list-none flex-col divide-y divide-line p-0">
            {placements.teams.map((one) => (
              <li key={`${one.department}.${one.slug}`} className="flex flex-wrap items-center justify-between gap-2 py-2 text-[13px]">
                <span className="text-ink">{one.name}</span>
                {mayOrganise ? (
                  <PlacementAct
                    act={{ kind: "leave", department: one.department, team: one.slug, teamName: one.name }}
                    person={person.displayName}
                    principalId={person.principalId}
                    onDone={onWritten}
                  />
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
      <SectionCard title="Leads" lede="A lead is appointed by somebody else and confers nothing.">
        {placements.leads.length === 0 ? (
          <p className="m-0 text-[13px] text-dim">Leads no department you may see.</p>
        ) : (
          <ul className="m-0 flex list-none flex-col divide-y divide-line p-0">
            {placements.leads.map((one) => (
              <li key={one.slug} className="flex flex-wrap items-center justify-between gap-2 py-2 text-[13px]">
                <span className="text-ink">{one.name}</span>
                {mayOrganise ? (
                  <PlacementAct
                    act={{ kind: "stand_down", department: one.slug, departmentName: one.name }}
                    person={person.displayName}
                    principalId={person.principalId}
                    onDone={onWritten}
                  />
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}

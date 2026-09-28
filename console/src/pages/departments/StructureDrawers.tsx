/**
 * The writes that shape the organisation, shared by the Departments and teams pages and the Scopes
 * tab: create a department, a team or a scope; rename one; retire one; place somebody in a team or
 * take them out; appoint a lead or stand one down.
 *
 * **Every short name says its form before submit.** A department's, a team's and a scope's short
 * name is `brain.core.department.SLUG_PATTERN`, and the field says so under its label
 * (`access/formParts.SHORT_NAME_HINT`) and judges it before anything is sent, with a sentence saying
 * what to change. `acceptance-test` is told to use an underscore; the API's own sentence for a
 * pattern it refused names nothing a person can act on. The short name is suggested from the name as
 * it is typed, and can be changed until it is sent; it cannot be changed after.
 *
 * **A rename and a retirement ask first, in the API's words.** A rename replaces a name and a
 * retirement ends something, so each opens a confirmation, and only the confirmation sends. A rename
 * sends the name the page showed with the new one, and the route refuses it in a sentence if somebody
 * changed it since; it never sends a short name, for `governPeopleQuery.A_SHORT_NAME_IS_NEVER_CHANGED`'s
 * reason. A retirement's refusal while live grants are bounded by the department's scope is the API's
 * one sentence, naming no grant and no figure (M27.15.22).
 *
 * **Creating and placing end nothing**, so they are not confirmed: they are a drawer's submit.
 *
 * Task ids: M27.11.1, M27.15.22, M27.16.1
 */

import { useCallback, useMemo, useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, Drawer, FailureState } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Checkbox } from "../../components/ui/checkbox";
import { Input } from "../../components/ui/input";
import { Field, FormProblem, NativeSelect, SHORT_NAME_HINT, shortNameProblem, suggestedShortName } from "../access/formParts";
import {
  ADD_TEAM_API_PATH,
  DRAW_SCOPE_API_PATH,
  FOUND_API_PATH,
  LEAD_API_PATH,
  MEMBERSHIP_API_PATH,
  RENAME_DEPARTMENT_API_PATH,
  RENAME_SCOPE_API_PATH,
  RENAME_TEAM_API_PATH,
  RETIRE_DEPARTMENT_API_PATH,
  RETIRE_SCOPE_API_PATH,
  RETIRE_TEAM_API_PATH,
  departmentChoicesApiPath,
  readOrganisation,
} from "./departmentsQuery";

export const CREATING_A_DEPARTMENT_DOES =
  "The department is created with a scope of its own under the same short name, so a grant can be written over it straight away.";
export const CREATING_A_TEAM_DOES =
  "The team is created with nobody in it. Placing somebody in it changes nobody's access.";
export const CREATING_A_SCOPE_DOES =
  "The scope reaches the rows of the departments chosen, or of the one team chosen, and nothing else. A grant can then be bounded by it.";
export const RENAMING_DOES =
  "Only the name people read changes. The short name stays, so every grant written over it stays exactly as it is.";

/** What each thing the structure holds is, for its words. */
export type Target =
  | { readonly kind: "department"; readonly slug: string; readonly name: string }
  | { readonly kind: "team"; readonly department: string; readonly slug: string; readonly name: string }
  | { readonly kind: "scope"; readonly slug: string; readonly name: string; readonly scope: unknown };

function Footer({ formId, verb, busy, onCancel }: { readonly formId: string; readonly verb: string; readonly busy: boolean; readonly onCancel: () => void }) {
  return (
    <>
      <Button type="button" variant="outline" disabled={busy} onClick={onCancel}>
        Cancel
      </Button>
      <Button type="submit" form={formId} disabled={busy}>
        {verb}
      </Button>
    </>
  );
}

/** A name and the short name drawn from it, each saying what it accepts. */
function NameAndShortName({
  name,
  slug,
  onName,
  onSlug,
  problems,
  apiProblems,
  nameLabel = "Name",
  nameField = "name",
}: {
  readonly name: string;
  readonly slug: string;
  readonly onName: (value: string) => void;
  readonly onSlug: (value: string) => void;
  readonly problems: { readonly name?: string | undefined; readonly slug?: string | undefined };
  readonly apiProblems: ApiFailure["problems"];
  readonly nameLabel?: string | undefined;
  readonly nameField?: string | undefined;
}) {
  return (
    <>
      <Field label={nameLabel} hint="What people read, up to 120 characters." problem={problems.name} apiProblems={apiProblems} names={[nameField]}>
        {({ id, describedBy, invalid }) => (
          <Input
            id={id}
            aria-describedby={describedBy}
            aria-invalid={invalid ? true : undefined}
            className="h-11 sm:h-9"
            maxLength={120}
            value={name}
            onChange={(event) => {
              onName(event.target.value);
            }}
          />
        )}
      </Field>
      <Field label="Short name" hint={`${SHORT_NAME_HINT} It cannot be changed later.`} problem={problems.slug} apiProblems={apiProblems} names={["slug"]}>
        {({ id, describedBy, invalid }) => (
          <Input
            id={id}
            aria-describedby={describedBy}
            aria-invalid={invalid ? true : undefined}
            autoComplete="off"
            spellCheck={false}
            className="h-11 font-mono sm:h-9"
            maxLength={60}
            value={slug}
            onChange={(event) => {
              onSlug(event.target.value);
            }}
          />
        )}
      </Field>
    </>
  );
}

/** A department created, with the scope that defines it. */
export function NewDepartmentDrawer({
  open,
  onOpenChange,
  onWritten,
}: {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly onWritten: (slug: string) => void;
}) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [edited, setEdited] = useState(false);
  const [problems, setProblems] = useState<{ name?: string; slug?: string }>({});
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const found: { name?: string; slug?: string } = {};
    if (name.trim() === "") {
      found.name = "Give the department a name people will read.";
    }
    const shape = shortNameProblem(slug);
    if (shape !== null) {
      found.slug = shape;
    }
    setProblems(found);
    if (Object.keys(found).length > 0) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(FOUND_API_PATH, { method: "POST", body: { slug: slug.trim(), name: name.trim() } });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      const created = slug.trim();
      setName("");
      setSlug("");
      setEdited(false);
      onOpenChange(false);
      onWritten(created);
    })();
  };

  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title="New department"
      description={CREATING_A_DEPARTMENT_DOES}
      footer={<Footer formId="new-department" verb="Create the department" busy={busy} onCancel={() => { onOpenChange(false); }} />}
    >
      <form id="new-department" noValidate className="flex flex-col gap-4" onSubmit={submit}>
        <NameAndShortName
          name={name}
          slug={slug}
          onName={(value) => {
            setName(value);
            if (!edited) {
              setSlug(suggestedShortName(value));
            }
          }}
          onSlug={(value) => {
            setEdited(true);
            setSlug(value);
          }}
          problems={problems}
          apiProblems={failure?.problems ?? []}
        />
        {Object.keys(problems).length > 0 ? <FormProblem>Nothing has been sent: correct the fields marked above.</FormProblem> : null}
        {failure === null ? null : <FailureState failure={failure} />}
      </form>
    </Drawer>
  );
}

/** A team created in a department. */
export function NewTeamDrawer({
  open,
  onOpenChange,
  department,
  departmentName,
  onWritten,
}: {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly department: string;
  readonly departmentName: string;
  readonly onWritten: () => void;
}) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [edited, setEdited] = useState(false);
  const [problems, setProblems] = useState<{ name?: string; slug?: string }>({});
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const found: { name?: string; slug?: string } = {};
    if (name.trim() === "") {
      found.name = "Give the team a name people will read.";
    }
    const shape = shortNameProblem(slug);
    if (shape !== null) {
      found.slug = shape;
    }
    setProblems(found);
    if (Object.keys(found).length > 0) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(ADD_TEAM_API_PATH, {
        method: "POST",
        body: { department, slug: slug.trim(), name: name.trim() },
      });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setName("");
      setSlug("");
      setEdited(false);
      onOpenChange(false);
      onWritten();
    })();
  };

  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title={`New team in ${departmentName}`}
      description={CREATING_A_TEAM_DOES}
      footer={<Footer formId="new-team" verb="Create the team" busy={busy} onCancel={() => { onOpenChange(false); }} />}
    >
      <form id="new-team" noValidate className="flex flex-col gap-4" onSubmit={submit}>
        <NameAndShortName
          name={name}
          slug={slug}
          onName={(value) => {
            setName(value);
            if (!edited) {
              setSlug(suggestedShortName(value));
            }
          }}
          onSlug={(value) => {
            setEdited(true);
            setSlug(value);
          }}
          problems={problems}
          apiProblems={failure?.problems ?? []}
        />
        {Object.keys(problems).length > 0 ? <FormProblem>Nothing has been sent: correct the fields marked above.</FormProblem> : null}
        {failure === null ? null : <FailureState failure={failure} />}
      </form>
    </Drawer>
  );
}

/** A scope drawn over one department or a named set of them, or one team of a single department. */
export function NewScopeDrawer({
  open,
  onOpenChange,
  onWritten,
  fixedDepartment,
}: {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly onWritten: () => void;
  /** A department the scope starts over, when drawn from that department's page. */
  readonly fixedDepartment?: string | undefined;
}) {
  const [label, setLabel] = useState("");
  const [slug, setSlug] = useState("");
  const [edited, setEdited] = useState(false);
  const [chosen, setChosen] = useState<readonly string[]>(fixedDepartment === undefined ? [] : [fixedDepartment]);
  const [team, setTeam] = useState("");
  const [problems, setProblems] = useState<{ name?: string; slug?: string; departments?: string }>({});
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);
  const answer = useResource<unknown>(open ? departmentChoicesApiPath() : null);
  const departments = useMemo(() => readOrganisation(answer.data).departments, [answer.data]);
  const single = chosen.length === 1 ? departments.find((one) => one.slug === chosen[0]) : undefined;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const found: { name?: string; slug?: string; departments?: string } = {};
    if (label.trim() === "") {
      found.name = "Give the scope a name people will read.";
    }
    const shape = shortNameProblem(slug);
    if (shape !== null) {
      found.slug = shape;
    }
    if (chosen.length === 0) {
      found.departments = "Choose at least one department for the scope to reach.";
    }
    setProblems(found);
    if (Object.keys(found).length > 0) {
      return;
    }
    const body = {
      slug: slug.trim(),
      label: label.trim(),
      departments: [...chosen],
      ...(chosen.length === 1 && team !== "" ? { team } : {}),
    };
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(DRAW_SCOPE_API_PATH, { method: "POST", body });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setLabel("");
      setSlug("");
      setEdited(false);
      setChosen(fixedDepartment === undefined ? [] : [fixedDepartment]);
      setTeam("");
      onOpenChange(false);
      onWritten();
    })();
  };

  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title="New scope"
      description={CREATING_A_SCOPE_DOES}
      footer={<Footer formId="new-scope" verb="Create the scope" busy={busy} onCancel={() => { onOpenChange(false); }} />}
    >
      <form id="new-scope" noValidate className="flex flex-col gap-4" onSubmit={submit}>
        <NameAndShortName
          name={label}
          slug={slug}
          nameField="label"
          onName={(value) => {
            setLabel(value);
            if (!edited) {
              setSlug(suggestedShortName(value));
            }
          }}
          onSlug={(value) => {
            setEdited(true);
            setSlug(value);
          }}
          problems={problems}
          apiProblems={failure?.problems ?? []}
        />
        <fieldset className="m-0 flex min-w-0 flex-col gap-1.5 border-0 p-0">
          <legend className="mb-1.5 p-0 text-[13px] font-medium text-ink">Departments it reaches</legend>
          <p className="m-0 text-[12px] text-dim">One or more of the departments you may see.</p>
          {departments.map((one) => {
            const ticked = chosen.includes(one.slug);
            return (
              <label key={one.slug} className="flex min-h-9 items-center gap-2 text-[13px] text-ink">
                <Checkbox
                  checked={ticked}
                  onCheckedChange={(on) => {
                    setTeam("");
                    setChosen(on === true ? [...chosen, one.slug] : chosen.filter((value) => value !== one.slug));
                  }}
                />
                {one.name}
              </label>
            );
          })}
          {problems.departments === undefined ? null : <FormProblem>{problems.departments}</FormProblem>}
        </fieldset>
        {single === undefined || single.teams.length === 0 ? null : (
          <Field label="Only one team" hint="Optional: narrow the scope to one team of that department." apiProblems={failure?.problems ?? []} names={["team"]}>
            {({ id, describedBy, invalid }) => (
              <NativeSelect id={id} describedBy={describedBy} invalid={invalid} value={team} onChange={setTeam}>
                <option value="">The whole department</option>
                {single.teams.map((one) => (
                  <option key={one.slug} value={one.slug}>
                    {one.name}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
        )}
        {Object.keys(problems).length > 0 ? <FormProblem>Nothing has been sent: correct the fields marked above.</FormProblem> : null}
        {failure === null ? null : <FailureState failure={failure} />}
      </form>
    </Drawer>
  );
}

function kindWord(target: Target): string {
  return target.kind;
}

/** A department, a team or a scope renamed, asked first and sent only from the confirmation. */
export function RenameDrawer({
  target,
  onOpenChange,
  onWritten,
}: {
  /** What is being renamed, or null when the drawer is closed. */
  readonly target: Target | null;
  readonly onOpenChange: (open: boolean) => void;
  readonly onWritten: () => void;
}) {
  const [name, setName] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const review = (event: FormEvent) => {
    event.preventDefault();
    if (target === null) {
      return;
    }
    const typed = name.trim();
    if (typed === "") {
      setProblem("Type the new name first; nothing has been sent.");
      return;
    }
    if (typed === target.name) {
      setProblem("That is the name it already has; nothing has been sent.");
      return;
    }
    setProblem(null);
    setFailure(null);
    setPending(typed);
  };

  const send = useCallback(() => {
    if (target === null || pending === null) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result =
        target.kind === "department"
          ? await request<unknown>(RENAME_DEPARTMENT_API_PATH, {
              method: "POST",
              body: { slug: target.slug, expected_name: target.name, name: pending },
            })
          : target.kind === "team"
            ? await request<unknown>(RENAME_TEAM_API_PATH, {
                method: "POST",
                body: { department: target.department, slug: target.slug, expected_name: target.name, name: pending },
              })
            : await request<unknown>(RENAME_SCOPE_API_PATH, {
                method: "POST",
                body: { slug: target.slug, expected_label: target.name, label: pending },
              });
      setBusy(false);
      setPending(null);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setName("");
      onOpenChange(false);
      onWritten();
    })();
  }, [target, pending, onOpenChange, onWritten]);

  return (
    <>
      <Drawer
        open={target !== null}
        onOpenChange={onOpenChange}
        title={target === null ? "Rename" : `Rename the ${kindWord(target)} ${target.name}`}
        description={RENAMING_DOES}
        footer={<Footer formId="rename" verb="Review the rename" busy={busy || pending !== null} onCancel={() => { onOpenChange(false); }} />}
      >
        <form id="rename" noValidate className="flex flex-col gap-4" onSubmit={review}>
          <Field
            label="New name"
            hint="What people read, up to 120 characters. The short name does not change."
            problem={problem}
            apiProblems={failure?.problems ?? []}
            names={["name", "label"]}
          >
            {({ id, describedBy, invalid }) => (
              <Input
                id={id}
                aria-describedby={describedBy}
                aria-invalid={invalid ? true : undefined}
                className="h-11 sm:h-9"
                maxLength={120}
                value={name}
                onChange={(event) => {
                  setName(event.target.value);
                }}
              />
            )}
          </Field>
          {failure === null ? null : <FailureState failure={failure} />}
        </form>
      </Drawer>
      <ConfirmDialog
        open={pending !== null && target !== null}
        question={target === null || pending === null ? "" : `Rename the ${kindWord(target)} ${target.name} to ${pending}?`}
        consequence={RENAMING_DOES}
        confirmLabel="Rename"
        cancelLabel="Leave it"
        busy={busy}
        onConfirm={send}
        onCancel={() => {
          setPending(null);
        }}
      />
    </>
  );
}

/**
 * A department, a team or a scope retired, confirmed, in the API's words. Controlled, so a menu item
 * can open it after the menu has closed.
 */
export function RetireDialog({
  target,
  consequence,
  onClose,
  onWritten,
}: {
  /** What is being retired, or null when nothing is being asked. */
  readonly target: Target | null;
  /** What retiring it does and does not do, in the API's words where it has them. */
  readonly consequence: string;
  readonly onClose: () => void;
  readonly onWritten: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const go = useCallback(() => {
    if (target === null) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result =
        target.kind === "department"
          ? await request<unknown>(RETIRE_DEPARTMENT_API_PATH, {
              method: "POST",
              body: { slug: target.slug, expected_name: target.name },
            })
          : target.kind === "team"
            ? await request<unknown>(RETIRE_TEAM_API_PATH, {
                method: "POST",
                body: { department: target.department, slug: target.slug, expected_name: target.name },
              })
            : await request<unknown>(RETIRE_SCOPE_API_PATH, {
                method: "POST",
                body: { slug: target.slug, expected_scope: target.scope },
              });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      onClose();
      onWritten();
    })();
  }, [target, onClose, onWritten]);
  return (
    <ConfirmDialog
      open={target !== null}
      question={target === null ? "" : `Retire the ${kindWord(target)} ${target.name}?`}
      consequence={consequence}
      details={failure === null ? undefined : <FailureState failure={failure} />}
      confirmLabel={target === null ? "Retire" : `Retire the ${kindWord(target)}`}
      cancelLabel="Keep it"
      busy={busy}
      onConfirm={go}
      onCancel={() => {
        setFailure(null);
        onClose();
      }}
    />
  );
}

/** A button that opens `RetireDialog` for one thing. */
export function RetireControl({
  target,
  consequence,
  onWritten,
  label = "Retire",
}: {
  readonly target: Target;
  readonly consequence: string;
  readonly onWritten: () => void;
  readonly label?: string | undefined;
}) {
  const [asking, setAsking] = useState(false);
  return (
    <>
      <Button
        size="sm"
        variant="outline"
        aria-label={`${label} the ${kindWord(target)} ${target.name}`}
        onClick={() => {
          setAsking(true);
        }}
      >
        {label}
      </Button>
      <RetireDialog
        target={asking ? target : null}
        consequence={consequence}
        onClose={() => {
          setAsking(false);
        }}
        onWritten={onWritten}
      />
    </>
  );
}

/** One placement act on a department page: take somebody out of a team, or change the lead. */
export type PlacementAct =
  | { readonly kind: "leave"; readonly department: string; readonly team: string; readonly teamName: string; readonly principalId: string; readonly person: string }
  | { readonly kind: "appoint"; readonly department: string; readonly departmentName: string; readonly principalId: string; readonly person: string }
  | { readonly kind: "stand_down"; readonly department: string; readonly departmentName: string; readonly person: string };

export const A_PLACEMENT_CHANGES_NO_ACCESS =
  "Nobody's access changes: a team is where somebody sits and a lead confers nothing. What they may see is still only what their grants say.";

function placementQuestion(act: PlacementAct): string {
  switch (act.kind) {
    case "leave":
      return `Take ${act.person} out of ${act.teamName}?`;
    case "appoint":
      return `Appoint ${act.person} to lead ${act.departmentName}?`;
    case "stand_down":
      return `Stand ${act.person} down as lead of ${act.departmentName}?`;
  }
}

/** A placement act, pressed, confirmed and only then sent. */
export function PlacementControl({ act, label, onWritten }: { readonly act: PlacementAct; readonly label: string; readonly onWritten: () => void }) {
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
              body: { department: act.department, team: act.team, principal_id: act.principalId, change: "leave" },
            })
          : await request<unknown>(LEAD_API_PATH, {
              method: "POST",
              body:
                act.kind === "appoint"
                  ? { department: act.department, change: "appoint", principal_id: act.principalId }
                  : { department: act.department, change: "stand_down" },
            });
      setBusy(false);
      setAsking(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      onWritten();
    })();
  }, [act, onWritten]);
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
        question={placementQuestion(act)}
        consequence={act.kind === "appoint" ? `${A_PLACEMENT_CHANGES_NO_ACCESS} Any current lead is stood down in the same change.` : A_PLACEMENT_CHANGES_NO_ACCESS}
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

/** Somebody from the department placed in one of its teams, chosen in a drawer. */
export function AddMemberDrawer({
  open,
  onOpenChange,
  department,
  team,
  teamName,
  candidates,
  onWritten,
}: {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly department: string;
  readonly team: string;
  readonly teamName: string;
  /** The department's people not already in the team, as this reader was shown them. */
  readonly candidates: readonly { readonly principal_id: string; readonly display_name: string }[];
  readonly onWritten: () => void;
}) {
  const [person, setPerson] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (person === "") {
      setProblem("Choose who to place in the team; nothing has been sent.");
      return;
    }
    setProblem(null);
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(MEMBERSHIP_API_PATH, {
        method: "POST",
        body: { department, team, principal_id: person, change: "join" },
      });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setPerson("");
      onOpenChange(false);
      onWritten();
    })();
  };

  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title={`Add to ${teamName}`}
      description={A_PLACEMENT_CHANGES_NO_ACCESS}
      footer={<Footer formId="add-member" verb="Add to the team" busy={busy} onCancel={() => { onOpenChange(false); }} />}
    >
      <form id="add-member" noValidate className="flex flex-col gap-4" onSubmit={submit}>
        <Field label="Person" hint="People of this department you may see who are not in the team." problem={problem} apiProblems={failure?.problems ?? []} names={["principal_id"]}>
          {({ id, describedBy, invalid }) => (
            <NativeSelect id={id} describedBy={describedBy} invalid={invalid} value={person} onChange={setPerson}>
              <option value="">Choose a person</option>
              {candidates.map((one) => (
                <option key={one.principal_id} value={one.principal_id}>
                  {one.display_name}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        {problem === null ? null : <FormProblem>{problem}</FormProblem>}
        {failure === null ? null : <FailureState failure={failure} />}
      </form>
    </Drawer>
  );
}

/**
 * The four writes a person is given something through, each in a drawer over the page it opened
 * from: one grant, a pack, one grant to several people at once, and a person added by hand.
 *
 * **Each form says what it accepts before submit, and judges a blank or malformed value before
 * sending.** A capability is in the grammar `brain.core.entitlement.CAPABILITY_RE` spells, a scope
 * is chosen from what the Scopes screen answered this reader (never typed, for
 * `governQuery.A_SCOPE_IS_CHOSEN_BY_NAME_AND_NEVER_TYPED`'s reason), a reason is required, and an
 * expiry already past on this device's clock is said. Each of those is the API's rule and the API
 * judges it again; its refusal is drawn in its own words under the form.
 *
 * **A grant to several people is all or nothing and asks first.** The form opens a confirmation
 * naming everybody chosen; only the confirmation sends; the route writes every grant or none, and
 * its refusal names nobody, which is `brain.govern_routes.
 * A_GRANT_TO_SEVERAL_IS_ALL_OR_NOTHING_AND_ITS_REFUSAL_NAMES_NOBODY`.
 *
 * **Adding a grant or a pack ends nothing**, so it is not confirmed: a confirmation in front of every
 * write is one people learn to click through (`tests/destructive-confirmed.test.ts`).
 *
 * **What a write answers is discarded and the page asks again**, for `People.tsx`' old reason: the
 * grant's id and instant are the database's, and what the person now reaches is the resolver's.
 *
 * Task ids: M27.11.2, M27.11.3, M27.15.19
 */

import { useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, Drawer, FailureState } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import {
  CAPABILITY_HINT,
  EXPIRY_HINT,
  Field,
  FormProblem,
  NativeSelect,
  REASON_HINT,
  REASON_MAX,
  SHORT_NAME_HINT,
  alreadyPast,
  capabilityProblem,
  instantFrom,
  shortNameProblem,
} from "../access/formParts";
import {
  CAPABILITIES_API_PATH,
  DIRECTORY_API_PATH,
  EMPLOYMENTS,
  GRANTS_API_PATH,
  MOST_GRANTED_AT_ONCE,
  PACK_ASSIGNMENT_API_PATH,
  PACKS_API_PATH,
  SEVERAL_GRANTS_API_PATH,
  readPackChoices,
  readScopeChoices,
  readVocabulary,
  scopeChoicesApiPath,
  type GrantBody,
  type PackAssignmentBody,
  type PersonAddingBody,
  type PersonRow,
  type SeveralBody,
} from "./peopleQuery";
import { departmentChoicesApiPath, readOrganisation } from "../departments/departmentsQuery";

export const GRANT_TITLE = "Grant a capability";
export const PACK_TITLE = "Assign a pack";
export const SEVERAL_TITLE = "Grant to the people selected";
export const ADD_TITLE = "Add a person";

export const WRITE_GRANT = "Grant it";
export const ASSIGN_PACK = "Assign the pack";
export const REVIEW_SEVERAL = "Review the grant";
export const ADD_PERSON = "Add the person";
export const CANCEL = "Cancel";

/** What is said when nothing is ticked, or too many, before anything is sent. */
export const CHOOSE_PEOPLE_FIRST = "Select the people to grant it to on the list first; nothing has been sent.";
export const TOO_MANY_CHOSEN = `One grant to several may name up to ${String(MOST_GRANTED_AT_ONCE)} people. Clear some and grant the rest after.`;

export const EXPIRY_PAST = "Choose an expiry that is still to come, or leave it empty; nothing has been sent.";

export function severalQuestion(capability: string, scope: string): string {
  return `Grant ${capability} over ${scope} to each of these people?`;
}

export const SEVERAL_CONSEQUENCE =
  "Each person listed is granted it, or nobody is: if any one of them is refused, nothing is written, and the refusal does not say who it was about.";

/** The grant, scope, reason and expiry a form holds. */
interface Proposal {
  readonly capability: string;
  readonly scope: string;
  readonly reason: string;
  readonly expiry: string;
}

const BLANK: Proposal = Object.freeze({ capability: "", scope: "", reason: "", expiry: "" });

type Problems = Partial<Record<keyof Proposal, string>>;

function proposalProblems(proposal: Proposal, needsCapability: boolean): Problems {
  const problems: Problems = {};
  if (needsCapability) {
    const capability = capabilityProblem(proposal.capability);
    if (capability !== null) {
      problems.capability = capability;
    }
  }
  if (proposal.scope === "") {
    problems.scope = "Choose the scope it is bounded by.";
  }
  if (proposal.reason.trim() === "") {
    problems.reason = "Say why it is given; the reason is kept with the grant.";
  }
  if (alreadyPast(proposal.expiry)) {
    problems.expiry = EXPIRY_PAST;
  }
  return problems;
}

function ScopeField({
  value,
  problem,
  apiProblems,
  onChange,
  open,
}: {
  readonly value: string;
  readonly problem: string | undefined;
  readonly apiProblems: ApiFailure["problems"];
  readonly onChange: (value: string) => void;
  readonly open: boolean;
}) {
  const scopes = useResource<unknown>(open ? scopeChoicesApiPath() : null);
  const choices = readScopeChoices(scopes.data);
  return (
    <Field
      label="Scope"
      hint="Which rows it reaches: a department, a named set of departments, or the whole company."
      problem={problem}
      apiProblems={apiProblems}
      names={["scope_slug"]}
    >
      {({ id, describedBy, invalid }) => (
        <NativeSelect id={id} describedBy={describedBy} invalid={invalid} value={value} onChange={onChange}>
          <option value="">Choose a scope</option>
          {choices.map((one) => (
            <option key={one.slug} value={one.slug}>
              {one.label}
            </option>
          ))}
        </NativeSelect>
      )}
    </Field>
  );
}

function ReasonAndExpiry({
  proposal,
  problems,
  apiProblems,
  set,
}: {
  readonly proposal: Proposal;
  readonly problems: Problems;
  readonly apiProblems: ApiFailure["problems"];
  readonly set: (next: Partial<Proposal>) => void;
}) {
  return (
    <>
      <Field label="Reason" hint={REASON_HINT} problem={problems.reason} apiProblems={apiProblems} names={["reason"]}>
        {({ id, describedBy, invalid }) => (
          <Textarea
            id={id}
            aria-describedby={describedBy}
            aria-invalid={invalid ? true : undefined}
            maxLength={REASON_MAX}
            value={proposal.reason}
            onChange={(event) => {
              set({ reason: event.target.value });
            }}
          />
        )}
      </Field>
      <Field label="Lapses" hint={EXPIRY_HINT} problem={problems.expiry} apiProblems={apiProblems} names={["not_after"]}>
        {({ id, describedBy, invalid }) => (
          <Input
            id={id}
            type="datetime-local"
            aria-describedby={describedBy}
            aria-invalid={invalid ? true : undefined}
            className="h-11 sm:h-9"
            value={proposal.expiry}
            onChange={(event) => {
              set({ expiry: event.target.value });
            }}
          />
        )}
      </Field>
    </>
  );
}

function CapabilityField({
  value,
  problem,
  apiProblems,
  onChange,
  open,
}: {
  readonly value: string;
  readonly problem: string | undefined;
  readonly apiProblems: ApiFailure["problems"];
  readonly onChange: (value: string) => void;
  readonly open: boolean;
}) {
  // Suggestions only: the vocabulary this reader may be shown, or nothing. What is granted is what
  // is typed, and the API refuses a capability nobody declared.
  const vocabulary = useResource<unknown>(open ? CAPABILITIES_API_PATH : null);
  const known = readVocabulary(vocabulary.data);
  return (
    <Field label="Capability" hint={CAPABILITY_HINT} problem={problem} apiProblems={apiProblems} names={["capability"]}>
      {({ id, describedBy, invalid }) => (
        <>
          <Input
            id={id}
            list={`${id}-known`}
            autoComplete="off"
            spellCheck={false}
            aria-describedby={describedBy}
            aria-invalid={invalid ? true : undefined}
            className="h-11 font-mono sm:h-9"
            value={value}
            onChange={(event) => {
              onChange(event.target.value);
            }}
          />
          <datalist id={`${id}-known`}>
            {known.map((one) => (
              <option key={one} value={one} />
            ))}
          </datalist>
        </>
      )}
    </Field>
  );
}

function Footer({ formId, verb, busy, onCancel }: { readonly formId: string; readonly verb: string; readonly busy: boolean; readonly onCancel: () => void }) {
  return (
    <>
      <Button type="button" variant="outline" onClick={onCancel} disabled={busy}>
        {CANCEL}
      </Button>
      <Button type="submit" form={formId} disabled={busy}>
        {verb}
      </Button>
    </>
  );
}

/** One capability granted to one person. */
export function GrantDrawer({
  open,
  onOpenChange,
  principalId,
  personName,
  onWritten,
}: {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly principalId: string;
  readonly personName: string;
  readonly onWritten: () => void;
}) {
  const [proposal, setProposal] = useState<Proposal>(BLANK);
  const [problems, setProblems] = useState<Problems>({});
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (next: Partial<Proposal>) => {
    setProposal({ ...proposal, ...next });
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const found = proposalProblems(proposal, true);
    setProblems(found);
    if (Object.keys(found).length > 0) {
      return;
    }
    const expiry = instantFrom(proposal.expiry);
    const body: GrantBody = {
      principal_id: principalId,
      capability: proposal.capability.trim(),
      scope_slug: proposal.scope,
      reason: proposal.reason.trim(),
      ...(expiry === undefined ? {} : { not_after: expiry }),
    };
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(GRANTS_API_PATH, { method: "POST", body });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setProposal(BLANK);
      onOpenChange(false);
      onWritten();
    })();
  };

  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title={GRANT_TITLE}
      description={`Give ${personName} one capability over a scope. It adds to what they hold and takes nothing away.`}
      footer={<Footer formId="grant-one" verb={WRITE_GRANT} busy={busy} onCancel={() => { onOpenChange(false); }} />}
    >
      <form id="grant-one" noValidate className="flex flex-col gap-4" onSubmit={submit}>
        <CapabilityField
          value={proposal.capability}
          problem={problems.capability}
          apiProblems={failure?.problems ?? []}
          onChange={(capability) => {
            set({ capability });
          }}
          open={open}
        />
        <ScopeField
          value={proposal.scope}
          problem={problems.scope}
          apiProblems={failure?.problems ?? []}
          onChange={(scope) => {
            set({ scope });
          }}
          open={open}
        />
        <ReasonAndExpiry proposal={proposal} problems={problems} apiProblems={failure?.problems ?? []} set={set} />
        {Object.keys(problems).length > 0 ? <FormProblem>Nothing has been sent: correct the fields marked above.</FormProblem> : null}
        {failure === null ? null : <FailureState failure={failure} />}
      </form>
    </Drawer>
  );
}

/** One pack assigned to one person over a scope. */
export function PackDrawer({
  open,
  onOpenChange,
  principalId,
  personName,
  onWritten,
}: {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly principalId: string;
  readonly personName: string;
  readonly onWritten: () => void;
}) {
  const [pack, setPack] = useState("");
  const [proposal, setProposal] = useState<Proposal>(BLANK);
  const [problems, setProblems] = useState<Problems & { pack?: string }>({});
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);
  const packs = useResource<unknown>(open ? PACKS_API_PATH : null);
  const choices = readPackChoices(packs.data);
  const chosen = choices.find((one) => one.slug === pack);
  const set = (next: Partial<Proposal>) => {
    setProposal({ ...proposal, ...next });
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const found: Problems & { pack?: string } = proposalProblems(proposal, false);
    if (pack === "") {
      found.pack = "Choose the pack to assign.";
    }
    setProblems(found);
    if (Object.keys(found).length > 0) {
      return;
    }
    const expiry = instantFrom(proposal.expiry);
    const body: PackAssignmentBody = {
      principal_id: principalId,
      pack_slug: pack,
      scope_slug: proposal.scope,
      reason: proposal.reason.trim(),
      ...(expiry === undefined ? {} : { not_after: expiry }),
    };
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(PACK_ASSIGNMENT_API_PATH, { method: "POST", body });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setPack("");
      setProposal(BLANK);
      onOpenChange(false);
      onWritten();
    })();
  };

  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title={PACK_TITLE}
      description={`Give ${personName} every capability in a pack, over one scope. A pack is assigned only if you could grant each of its capabilities yourself.`}
      footer={<Footer formId="grant-pack" verb={ASSIGN_PACK} busy={busy} onCancel={() => { onOpenChange(false); }} />}
    >
      <form id="grant-pack" noValidate className="flex flex-col gap-4" onSubmit={submit}>
        <Field label="Pack" hint="The packs you may assign." problem={problems.pack} apiProblems={failure?.problems ?? []} names={["pack_slug"]}>
          {({ id, describedBy, invalid }) => (
            <NativeSelect id={id} describedBy={describedBy} invalid={invalid} value={pack} onChange={setPack}>
              <option value="">Choose a pack</option>
              {choices.map((one) => (
                <option key={one.slug} value={one.slug}>
                  {one.label}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        {chosen === undefined ? null : (
          <p className="m-0 font-mono text-[11.5px] leading-relaxed text-dim [overflow-wrap:anywhere]">{chosen.capabilities.join(", ")}</p>
        )}
        <ScopeField
          value={proposal.scope}
          problem={problems.scope}
          apiProblems={failure?.problems ?? []}
          onChange={(scope) => {
            set({ scope });
          }}
          open={open}
        />
        <ReasonAndExpiry proposal={proposal} problems={problems} apiProblems={failure?.problems ?? []} set={set} />
        {Object.keys(problems).length > 0 ? <FormProblem>Nothing has been sent: correct the fields marked above.</FormProblem> : null}
        {failure === null ? null : <FailureState failure={failure} />}
      </form>
    </Drawer>
  );
}

/** One grant written for each of the people selected on the list, or for none of them. */
export function SeveralDrawer({
  open,
  onOpenChange,
  chosen,
  onWritten,
}: {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  /** The people ticked on the list, in the list's order. */
  readonly chosen: readonly PersonRow[];
  readonly onWritten: () => void;
}) {
  const [proposal, setProposal] = useState<Proposal>(BLANK);
  const [problems, setProblems] = useState<Problems>({});
  const [whole, setWhole] = useState<string | null>(null);
  const [pending, setPending] = useState<SeveralBody | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (next: Partial<Proposal>) => {
    setProposal({ ...proposal, ...next });
  };

  const review = (event: FormEvent) => {
    event.preventDefault();
    const found = proposalProblems(proposal, true);
    setProblems(found);
    const problem = chosen.length === 0 ? CHOOSE_PEOPLE_FIRST : chosen.length > MOST_GRANTED_AT_ONCE ? TOO_MANY_CHOSEN : null;
    setWhole(problem);
    if (Object.keys(found).length > 0 || problem !== null) {
      return;
    }
    const expiry = instantFrom(proposal.expiry);
    setFailure(null);
    setPending({
      principal_ids: chosen.map((one) => one.principalId),
      capability: proposal.capability.trim(),
      scope_slug: proposal.scope,
      reason: proposal.reason.trim(),
      ...(expiry === undefined ? {} : { not_after: expiry }),
    });
  };

  const send = (body: SeveralBody) => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(SEVERAL_GRANTS_API_PATH, { method: "POST", body });
      setBusy(false);
      setPending(null);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setProposal(BLANK);
      onOpenChange(false);
      onWritten();
    })();
  };

  return (
    <>
      <Drawer
        open={open}
        onOpenChange={onOpenChange}
        title={SEVERAL_TITLE}
        description="One grant for each person selected, written for all of them or for none."
        footer={<Footer formId="grant-several" verb={REVIEW_SEVERAL} busy={busy || pending !== null} onCancel={() => { onOpenChange(false); }} />}
      >
        <form id="grant-several" noValidate className="flex flex-col gap-4" onSubmit={review}>
          <p className="m-0 text-[13px] text-body">
            {chosen.length === 0 ? "Nobody is selected." : chosen.map((one) => one.displayName).join(", ")}
          </p>
          <CapabilityField
            value={proposal.capability}
            problem={problems.capability}
            apiProblems={failure?.problems ?? []}
            onChange={(capability) => {
              set({ capability });
            }}
            open={open}
          />
          <ScopeField
            value={proposal.scope}
            problem={problems.scope}
            apiProblems={failure?.problems ?? []}
            onChange={(scope) => {
              set({ scope });
            }}
            open={open}
          />
          <ReasonAndExpiry proposal={proposal} problems={problems} apiProblems={failure?.problems ?? []} set={set} />
          {whole === null ? null : <FormProblem>{whole}</FormProblem>}
          {Object.keys(problems).length > 0 ? <FormProblem>Nothing has been sent: correct the fields marked above.</FormProblem> : null}
          {failure === null ? null : <FailureState failure={failure} />}
        </form>
      </Drawer>
      <ConfirmDialog
        open={pending !== null}
        question={pending === null ? "" : severalQuestion(pending.capability, pending.scope_slug)}
        consequence={SEVERAL_CONSEQUENCE}
        details={
          <ul className="m-0 flex list-none flex-col gap-1 p-0">
            {chosen.map((one) => (
              <li key={one.principalId}>{one.displayName}</li>
            ))}
          </ul>
        }
        confirmLabel="Write these grants"
        cancelLabel="Leave it"
        busy={busy}
        onConfirm={() => {
          if (pending !== null) {
            send(pending);
          }
        }}
        onCancel={() => {
          setPending(null);
        }}
      />
    </>
  );
}

/** A person added by hand, on an install with no staff source. */
export function AddPersonDrawer({
  open,
  onOpenChange,
  onWritten,
  adding,
}: {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly onWritten: (principalId: string | null) => void;
  /** The API's sentence about what adding a person does. */
  readonly adding: string | undefined;
}) {
  // The departments offered are the Departments screen's answer to this reader, asked when the
  // drawer opens; with none answered, the short name is typed and judged by its form.
  const answer = useResource<unknown>(open ? departmentChoicesApiPath() : null);
  const departments = readOrganisation(answer.data).departments.map((one) => ({ slug: one.slug, name: one.name }));
  const [name, setName] = useState("");
  const [department, setDepartment] = useState("");
  const [employment, setEmployment] = useState("staff");
  const [expiry, setExpiry] = useState("");
  const [problems, setProblems] = useState<Partial<Record<"name" | "department" | "expiry", string>>>({});
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);
  const bounded = EMPLOYMENTS.find((one) => one.value === employment)?.bounded ?? false;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const found: Partial<Record<"name" | "department" | "expiry", string>> = {};
    if (name.trim() === "") {
      found.name = "Give the person's full name as colleagues know it.";
    }
    if (department !== "") {
      const shape = shortNameProblem(department);
      if (shape !== null) {
        found.department = shape;
      }
    }
    if (bounded && expiry.trim() === "") {
      found.expiry = "A contractor or partner needs the date their engagement ends.";
    } else if (alreadyPast(expiry)) {
      found.expiry = EXPIRY_PAST;
    }
    setProblems(found);
    if (Object.keys(found).length > 0) {
      return;
    }
    const until = instantFrom(expiry);
    const body: PersonAddingBody = {
      display_name: name.trim(),
      employment,
      ...(department === "" ? {} : { department }),
      ...(until === undefined ? {} : { not_after: until }),
    };
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(DIRECTORY_API_PATH, { method: "POST", body });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setName("");
      setExpiry("");
      onOpenChange(false);
      const data = result.data as { principal_id?: unknown } | null;
      onWritten(typeof data?.principal_id === "string" ? data.principal_id : null);
    })();
  };

  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title={ADD_TITLE}
      description={adding ?? "Adds a person to this install's directory. They hold nothing until somebody grants it, and sign in once a sign-in is linked to them."}
      footer={<Footer formId="add-person" verb={ADD_PERSON} busy={busy} onCancel={() => { onOpenChange(false); }} />}
    >
      <form id="add-person" noValidate className="flex flex-col gap-4" onSubmit={submit}>
        <Field label="Full name" hint="As colleagues know them, up to 200 characters." problem={problems.name} apiProblems={failure?.problems ?? []} names={["display_name"]}>
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              aria-describedby={describedBy}
              aria-invalid={invalid ? true : undefined}
              className="h-11 sm:h-9"
              maxLength={200}
              value={name}
              onChange={(event) => {
                setName(event.target.value);
              }}
            />
          )}
        </Field>
        <Field
          label="Department"
          hint={departments.length > 0 ? "Where they sit. Leave it empty to place them later." : SHORT_NAME_HINT}
          problem={problems.department}
          apiProblems={failure?.problems ?? []}
          names={["department"]}
        >
          {({ id, describedBy, invalid }) =>
            departments.length > 0 ? (
              <NativeSelect id={id} describedBy={describedBy} invalid={invalid} value={department} onChange={setDepartment}>
                <option value="">Not placed yet</option>
                {departments.map((one) => (
                  <option key={one.slug} value={one.slug}>
                    {one.name}
                  </option>
                ))}
              </NativeSelect>
            ) : (
              <Input
                id={id}
                aria-describedby={describedBy}
                aria-invalid={invalid ? true : undefined}
                className="h-11 font-mono sm:h-9"
                value={department}
                onChange={(event) => {
                  setDepartment(event.target.value);
                }}
              />
            )
          }
        </Field>
        <Field label="Employment" hint="A contractor or partner needs an end date." apiProblems={failure?.problems ?? []} names={["employment"]}>
          {({ id, describedBy, invalid }) => (
            <NativeSelect id={id} describedBy={describedBy} invalid={invalid} value={employment} onChange={setEmployment}>
              {EMPLOYMENTS.map((one) => (
                <option key={one.value} value={one.value}>
                  {one.label}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        <Field label="Engagement ends" hint={bounded ? "Required for a contractor or partner." : "Optional for staff."} problem={problems.expiry} apiProblems={failure?.problems ?? []} names={["not_after"]}>
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              type="datetime-local"
              aria-describedby={describedBy}
              aria-invalid={invalid ? true : undefined}
              className="h-11 sm:h-9"
              value={expiry}
              onChange={(event) => {
                setExpiry(event.target.value);
              }}
            />
          )}
        </Field>
        {Object.keys(problems).length > 0 ? <FormProblem>Nothing has been sent: correct the fields marked above.</FormProblem> : null}
        {failure === null ? null : <FailureState failure={failure} />}
      </form>
    </Drawer>
  );
}

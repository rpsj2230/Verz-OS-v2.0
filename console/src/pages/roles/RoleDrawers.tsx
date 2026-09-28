/**
 * The writes on the Roles tab: appoint somebody to a role over a scope, appoint a deputy for up to
 * thirty days, remove a role, map a directory group to a role, and retire a mapping.
 *
 * **A person is chosen by name** (`access/PersonPicker`), never by typing a principal id, which is
 * what the old forms asked for. A scope is chosen from the Scopes screen's answer to this reader.
 *
 * **Appointing and mapping end nothing**, so they are a drawer's submit; removing a role and retiring
 * a mapping end something, so each asks first and only the confirmation sends. Every refusal is the
 * API's own sentence, the separation of duties warning and the two Super Admin floor included; the
 * warning asks for an acknowledgement, which the form carries, and the API keeps it on the row and its
 * digest on the ledger (M1.8.7).
 *
 * Task ids: M27.11.3, M1.3.2, M1.3.3, M1.3.4, M1.1.5, M27.16.1
 */

import { useCallback, useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, Drawer, FailureState } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import {
  APPOINTMENT_API_PATH,
  DEPUTY_API_PATH,
  DEPUTY_DAYS,
  GROUP_RULES_API_PATH,
  GROUP_RULE_RETIREMENT_API_PATH,
  ROLE_REMOVAL_API_PATH,
  ROLE_VALUES,
} from "../governQuery";
import { Field, FormProblem, NativeSelect, REASON_HINT, REASON_MAX } from "../access/formParts";
import { PersonPicker } from "../access/PersonPicker";
import { roleWords } from "../access/PersonName";
import { readScopeChoices, scopeChoicesApiPath, type PersonRow } from "../people/peopleQuery";

/** The roles whose appointment needs a scope: `brain.identity.roles.ROLE_SPECS[...].scope_required`. */
export const SCOPED_ROLES: ReadonlySet<string> = new Set(["department_admin", "approver"]);

export const SEPARATION_NOTE =
  "Appointing one person as both Super Admin and Connector admin needs an acknowledgement. Give the reason in the acknowledgement field; it is kept in the audit trail.";

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

function ScopeChoice({
  value,
  onChange,
  problem,
  apiProblems,
  open,
  hint,
}: {
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly problem: string | undefined;
  readonly apiProblems: ApiFailure["problems"];
  readonly open: boolean;
  readonly hint: string;
}) {
  const scopes = useResource<unknown>(open ? scopeChoicesApiPath() : null);
  const choices = readScopeChoices(scopes.data);
  return (
    <Field label="Scope" hint={hint} problem={problem} apiProblems={apiProblems} names={["scope_slug"]}>
      {({ id, describedBy, invalid }) => (
        <NativeSelect id={id} describedBy={describedBy} invalid={invalid} value={value} onChange={onChange}>
          <option value="">No scope</option>
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

function ReasonField({
  value,
  onChange,
  problem,
  apiProblems,
}: {
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly problem: string | undefined;
  readonly apiProblems: ApiFailure["problems"];
}) {
  return (
    <Field label="Reason" hint={REASON_HINT} problem={problem} apiProblems={apiProblems} names={["reason"]}>
      {({ id, describedBy, invalid }) => (
        <Textarea
          id={id}
          aria-describedby={describedBy}
          aria-invalid={invalid ? true : undefined}
          maxLength={REASON_MAX}
          value={value}
          onChange={(event) => {
            onChange(event.target.value);
          }}
        />
      )}
    </Field>
  );
}

/** Somebody appointed to a role, over a scope where the role needs one. */
export function AppointDrawer({
  open,
  onOpenChange,
  onWritten,
}: {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly onWritten: () => void;
}) {
  const [person, setPerson] = useState<PersonRow | null>(null);
  const [role, setRole] = useState("");
  const [scope, setScope] = useState("");
  const [reason, setReason] = useState("");
  const [acknowledgement, setAcknowledgement] = useState("");
  const [problems, setProblems] = useState<Partial<Record<"person" | "role" | "scope" | "reason", string>>>({});
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const found: Partial<Record<"person" | "role" | "scope" | "reason", string>> = {};
    if (person === null) {
      found.person = "Choose who to appoint.";
    }
    if (role === "") {
      found.role = "Choose the role.";
    } else if (SCOPED_ROLES.has(role) && scope === "") {
      found.scope = `${roleWords(role)} is appointed over a scope; choose one.`;
    }
    if (reason.trim() === "") {
      found.reason = "Say why they are appointed; the reason is kept with the appointment.";
    }
    setProblems(found);
    if (Object.keys(found).length > 0 || person === null) {
      return;
    }
    const body = {
      principal_id: person.principalId,
      role,
      reason: reason.trim(),
      ...(scope === "" ? {} : { scope_slug: scope }),
      ...(acknowledgement.trim() === "" ? {} : { acknowledgement: acknowledgement.trim() }),
    };
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(APPOINTMENT_API_PATH, { method: "POST", body });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setPerson(null);
      setRole("");
      setScope("");
      setReason("");
      setAcknowledgement("");
      onOpenChange(false);
      onWritten();
    })();
  };

  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title="Appoint to a role"
      description="A role says what somebody is appointed to do on this platform. It grants nothing."
      footer={<Footer formId="appoint" verb="Appoint" busy={busy} onCancel={() => { onOpenChange(false); }} />}
    >
      <form id="appoint" noValidate className="flex flex-col gap-4" onSubmit={submit}>
        <PersonPicker label="Person" chosen={person} onChoose={setPerson} problem={problems.person} />
        <Field label="Role" hint="Department admin and Approver are appointed over a scope." problem={problems.role} apiProblems={failure?.problems ?? []} names={["role"]}>
          {({ id, describedBy, invalid }) => (
            <NativeSelect id={id} describedBy={describedBy} invalid={invalid} value={role} onChange={setRole}>
              <option value="">Choose a role</option>
              {ROLE_VALUES.map((one) => (
                <option key={one} value={one}>
                  {roleWords(one)}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        {SCOPED_ROLES.has(role) ? (
          <ScopeChoice
            value={scope}
            onChange={setScope}
            problem={problems.scope}
            apiProblems={failure?.problems ?? []}
            open={open}
            hint="Where they hold the role: a department or a named set of them."
          />
        ) : null}
        <ReasonField value={reason} onChange={setReason} problem={problems.reason} apiProblems={failure?.problems ?? []} />
        <Field label="Acknowledgement" hint={`Optional. ${SEPARATION_NOTE}`} apiProblems={failure?.problems ?? []} names={["acknowledgement"]}>
          {({ id, describedBy, invalid }) => (
            <Textarea
              id={id}
              aria-describedby={describedBy}
              aria-invalid={invalid ? true : undefined}
              maxLength={REASON_MAX}
              value={acknowledgement}
              onChange={(event) => {
                setAcknowledgement(event.target.value);
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

/** A deputy appointed to cover a standing appointment, for up to thirty days. */
export function DeputyDrawer({
  open,
  onOpenChange,
  standing,
  onWritten,
}: {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  /** The standing appointments a deputy may cover, with the name each is shown by. */
  readonly standing: readonly { readonly id: string; readonly label: string }[];
  readonly onWritten: () => void;
}) {
  const [covering, setCovering] = useState("");
  const [person, setPerson] = useState<PersonRow | null>(null);
  const [days, setDays] = useState("");
  const [reason, setReason] = useState("");
  const [problems, setProblems] = useState<Partial<Record<"covering" | "person" | "days" | "reason", string>>>({});
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const found: Partial<Record<"covering" | "person" | "days" | "reason", string>> = {};
    const count = Number(days);
    if (covering === "") {
      found.covering = "Choose the appointment the deputy covers.";
    }
    if (person === null) {
      found.person = "Choose the deputy.";
    }
    if (!Number.isInteger(count) || count < 1 || count > DEPUTY_DAYS) {
      found.days = `Give a whole number of days from 1 to ${String(DEPUTY_DAYS)}.`;
    }
    if (reason.trim() === "") {
      found.reason = "Say why a deputy is needed; the reason is kept with the appointment.";
    }
    setProblems(found);
    if (Object.keys(found).length > 0 || person === null) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(DEPUTY_API_PATH, {
        method: "POST",
        body: { grant_id: covering, principal_id: person.principalId, days: count, reason: reason.trim() },
      });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setCovering("");
      setPerson(null);
      setDays("");
      setReason("");
      onOpenChange(false);
      onWritten();
    })();
  };

  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title="Appoint a deputy"
      description={`A deputy holds the role for up to ${String(DEPUTY_DAYS)} days, lapses on its own, and cannot appoint another.`}
      footer={<Footer formId="deputy" verb="Appoint the deputy" busy={busy} onCancel={() => { onOpenChange(false); }} />}
    >
      <form id="deputy" noValidate className="flex flex-col gap-4" onSubmit={submit}>
        <Field label="Covering" hint="The standing appointment the deputy stands in for." problem={problems.covering} apiProblems={failure?.problems ?? []} names={["grant_id"]}>
          {({ id, describedBy, invalid }) => (
            <NativeSelect id={id} describedBy={describedBy} invalid={invalid} value={covering} onChange={setCovering}>
              <option value="">Choose an appointment</option>
              {standing.map((one) => (
                <option key={one.id} value={one.id}>
                  {one.label}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        <PersonPicker label="Deputy" chosen={person} onChoose={setPerson} problem={problems.person} />
        <Field label="Days" hint={`A whole number from 1 to ${String(DEPUTY_DAYS)}.`} problem={problems.days} apiProblems={failure?.problems ?? []} names={["days"]}>
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              type="number"
              min={1}
              max={DEPUTY_DAYS}
              aria-describedby={describedBy}
              aria-invalid={invalid ? true : undefined}
              className="h-11 sm:h-9"
              value={days}
              onChange={(event) => {
                setDays(event.target.value);
              }}
            />
          )}
        </Field>
        <ReasonField value={reason} onChange={setReason} problem={problems.reason} apiProblems={failure?.problems ?? []} />
        {Object.keys(problems).length > 0 ? <FormProblem>Nothing has been sent: correct the fields marked above.</FormProblem> : null}
        {failure === null ? null : <FailureState failure={failure} />}
      </form>
    </Drawer>
  );
}

/** A directory group mapped to one role. */
export function GroupRuleDrawer({
  open,
  onOpenChange,
  onWritten,
}: {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly onWritten: () => void;
}) {
  const [group, setGroup] = useState("");
  const [role, setRole] = useState("");
  const [scope, setScope] = useState("");
  const [reason, setReason] = useState("");
  const [problems, setProblems] = useState<Partial<Record<"group" | "role" | "scope" | "reason", string>>>({});
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const found: Partial<Record<"group" | "role" | "scope" | "reason", string>> = {};
    if (group.trim() === "") {
      found.group = "Type the group exactly as the identity provider spells it.";
    }
    if (role === "") {
      found.role = "Choose the role the group maps to.";
    } else if (SCOPED_ROLES.has(role) && scope === "") {
      found.scope = `${roleWords(role)} is mapped over a scope; choose one.`;
    }
    if (reason.trim() === "") {
      found.reason = "Say why the group maps to this role; the reason is kept with the rule.";
    }
    setProblems(found);
    if (Object.keys(found).length > 0) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(GROUP_RULES_API_PATH, {
        method: "POST",
        body: { idp_group: group.trim(), role, reason: reason.trim(), ...(scope === "" ? {} : { scope_slug: scope }) },
      });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setGroup("");
      setRole("");
      setScope("");
      setReason("");
      onOpenChange(false);
      onWritten();
    })();
  };

  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title="Map a directory group"
      description="Somebody in the group holds the role from their next sign-in and loses it when they leave the group. A group never grants a permission."
      footer={<Footer formId="group-rule" verb="Map the group" busy={busy} onCancel={() => { onOpenChange(false); }} />}
    >
      <form id="group-rule" noValidate className="flex flex-col gap-4" onSubmit={submit}>
        <Field label="Group" hint="The group's name exactly as the identity provider spells it, capitals included." problem={problems.group} apiProblems={failure?.problems ?? []} names={["idp_group"]}>
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              aria-describedby={describedBy}
              aria-invalid={invalid ? true : undefined}
              className="h-11 font-mono sm:h-9"
              value={group}
              onChange={(event) => {
                setGroup(event.target.value);
              }}
            />
          )}
        </Field>
        <Field label="Role" hint="Department admin and Approver are mapped over a scope." problem={problems.role} apiProblems={failure?.problems ?? []} names={["role"]}>
          {({ id, describedBy, invalid }) => (
            <NativeSelect id={id} describedBy={describedBy} invalid={invalid} value={role} onChange={setRole}>
              <option value="">Choose a role</option>
              {ROLE_VALUES.map((one) => (
                <option key={one} value={one}>
                  {roleWords(one)}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        {SCOPED_ROLES.has(role) ? (
          <ScopeChoice
            value={scope}
            onChange={setScope}
            problem={problems.scope}
            apiProblems={failure?.problems ?? []}
            open={open}
            hint="Where members of the group hold the role."
          />
        ) : null}
        <ReasonField value={reason} onChange={setReason} problem={problems.reason} apiProblems={failure?.problems ?? []} />
        {Object.keys(problems).length > 0 ? <FormProblem>Nothing has been sent: correct the fields marked above.</FormProblem> : null}
        {failure === null ? null : <FailureState failure={failure} />}
      </form>
    </Drawer>
  );
}

/** What is being ended from the Roles tab: an appointment, or a group's mapping. */
export type Ending =
  | { readonly kind: "role"; readonly grantId: string; readonly question: string }
  | { readonly kind: "rule"; readonly ruleId: string; readonly question: string };

export const REMOVING_A_ROLE_DOES =
  "They stop holding the role at once. The appointment is retired, not deleted, and the audit trail records who removed it.";
export const RETIRING_A_RULE_DOES =
  "Every role the mapping gave is removed at once, and nobody gains the role from the group again. The rule is kept on record.";

/** An appointment removed or a mapping retired, confirmed, and sent only from the confirmation. */
export function EndDialog({ ending, onClose, onWritten }: { readonly ending: Ending | null; readonly onClose: () => void; readonly onWritten: () => void }) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const go = useCallback(() => {
    if (ending === null) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result =
        ending.kind === "role"
          ? await request<unknown>(ROLE_REMOVAL_API_PATH, { method: "POST", body: { grant_id: ending.grantId } })
          : await request<unknown>(GROUP_RULE_RETIREMENT_API_PATH, { method: "POST", body: { rule_id: ending.ruleId } });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      onClose();
      onWritten();
    })();
  }, [ending, onClose, onWritten]);
  return (
    <ConfirmDialog
      open={ending !== null}
      question={ending?.question ?? ""}
      consequence={ending?.kind === "rule" ? RETIRING_A_RULE_DOES : REMOVING_A_ROLE_DOES}
      details={failure === null ? undefined : <FailureState failure={failure} />}
      confirmLabel={ending?.kind === "rule" ? "Retire the mapping" : "Remove the role"}
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

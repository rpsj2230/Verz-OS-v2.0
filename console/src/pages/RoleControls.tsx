/**
 * Who holds each role, and the three controls that change it: appoint, deputise and remove.
 *
 * Plain labelled controls rather than the schema form library, because the Roles screen is in the
 * entry chunk and that library is not; see `tests/bundle-split.test.ts`.
 *
 * **Nothing here decides who may do what.** The holders are what `GET /govern/roles/holders`
 * answered for this reader; the controls are drawn when it said `editable`; every refusal,
 * including the separation-of-duties warning and the Super Admin floor, is the API's own
 * sentence, rendered as it came. The warning asks for a reason, and the form's acknowledgement
 * field is where it goes; the API keeps it on the row and its digest on the ledger (M1.8.7).
 *
 * Task ids: M1.3.2, M1.3.3, M1.3.4, M1.8.7
 */

import { useCallback, useState } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ConfirmAction } from "../components/ConfirmAction";
import { FailureNotice } from "../ui/FailureNotice";
import {
  APPOINTMENT_API_PATH,
  DEPUTY_API_PATH,
  DEPUTY_DAYS,
  HOLDERS_API_PATH,
  ROLE_REMOVAL_API_PATH,
  ROLE_VALUES,
  readHolders,
  submittedAppointment,
  submittedDeputy,
  type HolderRow,
} from "./governQuery";

export const HOLDERS_HEADING = "Who holds each role";
export const NO_HOLDERS = "Nobody you may see holds a role yet.";
export const HOLDERS_LIST_LABEL = "Role holders";
export const SEPARATION_NOTE =
  "Appointing one person as both Super Admin and Connector Admin needs an acknowledgement: give " +
  "the reason in the acknowledgement field. It is recorded in the audit trail.";
export const REMOVE_ROLE = "Remove the role";
export const KEEP_ROLE = "Keep it";
export const REMOVAL_CONSEQUENCE =
  "They stop holding the role at once. The grant is retired, not deleted, and the audit trail " +
  "records who removed it.";

export function removeRoleLabel(holder: HolderRow): string {
  return `Remove ${holder.role} from ${holder.principal_id}`;
}

function describe(holder: HolderRow): string {
  const deputy = holder.deputy_of === null ? "" : `, deputy for ${holder.deputy_of}`;
  const until = holder.not_after === null ? "" : `, until ${holder.not_after.slice(0, 10)}`;
  return `${holder.role}${deputy}${until}`;
}

/** One write from a form, and the failure it came back with. */
function useWrite(path: string, onWritten: () => void) {
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);
  const send = useCallback(
    (body: unknown) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(path, { method: "POST", body });
        setBusy(false);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        onWritten();
      })();
    },
    [path, onWritten],
  );
  return { failure, busy, send };
}

/** One field of a plain form: its name, its label, and whether a blank is refused before sending. */
interface Field {
  readonly name: string;
  readonly label: string;
  readonly required: boolean;
  readonly choices?: readonly string[];
  readonly number?: boolean;
}

export const APPOINT_FIELDS: readonly Field[] = [
  { name: "principal_id", label: "Person (principal id)", required: true },
  { name: "role", label: "Role", required: true, choices: ROLE_VALUES },
  { name: "scope_slug", label: "Scope, for Department Admin and Approver", required: false },
  { name: "reason", label: "Reason", required: true },
  { name: "acknowledgement", label: "Acknowledgement, when asked", required: false },
];

export function deputyFields(standing: readonly HolderRow[]): readonly Field[] {
  return [
    {
      name: "grant_id",
      label: "Standing grant to cover",
      required: true,
      choices: standing.map((one) => one.id),
    },
    { name: "principal_id", label: "Deputy (principal id)", required: true },
    { name: "days", label: `Days, 1 to ${String(DEPUTY_DAYS)}`, required: true, number: true },
    { name: "reason", label: "Reason", required: true },
  ];
}

/** What is said when a form is sent with a required field blank. Names the fields, sends nothing. */
export function blankSentence(missing: readonly Field[]): string {
  return `Fill in ${missing.map((one) => one.label.toLowerCase()).join(", ")} before sending.`;
}

/**
 * A small form of labelled controls. Blank required fields are said before anything is sent; every
 * other judgement is the API's, and its refusal is drawn in its own words.
 */
function PlainForm({
  caption,
  fields,
  submitLabel,
  path,
  shape,
  onWritten,
  labelFor,
}: {
  readonly caption: string;
  readonly fields: readonly Field[];
  readonly submitLabel: string;
  readonly path: string;
  readonly shape: (values: Record<string, string>) => unknown;
  readonly onWritten: () => void;
  readonly labelFor?: (choice: string) => string;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [blank, setBlank] = useState<string | null>(null);
  const { failure, busy, send } = useWrite(path, onWritten);
  return (
    <form
      className="card"
      aria-label={caption}
      onSubmit={(event) => {
        event.preventDefault();
        const missing = fields.filter((one) => one.required && (values[one.name] ?? "") === "");
        if (missing.length > 0) {
          setBlank(blankSentence(missing));
          return;
        }
        setBlank(null);
        send(shape(values));
      }}
    >
      <h3>{caption}</h3>
      {fields.map((one) => (
        <label key={one.name} className="control-label">
          <span>{one.label}</span>
          {one.choices === undefined ? (
            <input
              className="form-control"
              name={one.name}
              type={one.number === true ? "number" : "text"}
              value={values[one.name] ?? ""}
              disabled={busy}
              onChange={(event) => setValues({ ...values, [one.name]: event.target.value })}
            />
          ) : (
            <select
              className="form-control"
              name={one.name}
              value={values[one.name] ?? ""}
              disabled={busy}
              onChange={(event) => setValues({ ...values, [one.name]: event.target.value })}
            >
              <option value="">Choose one</option>
              {one.choices.map((choice) => (
                <option key={choice} value={choice}>
                  {labelFor === undefined ? choice : labelFor(choice)}
                </option>
              ))}
            </select>
          )}
        </label>
      ))}
      {blank === null ? null : <p className="note">{blank}</p>}
      {failure === null ? null : <FailureNotice failure={failure} />}
      <button type="submit" className="button" disabled={busy}>
        {submitLabel}
      </button>
    </form>
  );
}

function Controls({
  holders,
  onWritten,
}: {
  readonly holders: readonly HolderRow[];
  readonly onWritten: () => void;
}) {
  const standing = holders.filter((one) => one.deputy_of === null);
  const named = new Map(standing.map((one) => [one.id, `${one.principal_id}, ${one.role}`]));
  return (
    <>
      <p className="note">{SEPARATION_NOTE}</p>
      <PlainForm
        caption="Appoint somebody to a role"
        fields={APPOINT_FIELDS}
        submitLabel="Appoint"
        path={APPOINTMENT_API_PATH}
        shape={(values) => submittedAppointment(values)}
        onWritten={onWritten}
      />
      <PlainForm
        caption="Appoint a deputy for up to thirty days"
        fields={deputyFields(standing)}
        submitLabel="Appoint a deputy"
        path={DEPUTY_API_PATH}
        shape={(values) => submittedDeputy({ ...values, days: Number(values["days"]) })}
        onWritten={onWritten}
        labelFor={(choice) => named.get(choice) ?? choice}
      />
    </>
  );
}

function Holders({ onWritten }: { readonly onWritten: () => void }) {
  const answer = useResource<unknown>(HOLDERS_API_PATH);
  const [asking, setAsking] = useState<HolderRow | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const remove = useCallback(
    (holder: HolderRow) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(ROLE_REMOVAL_API_PATH, {
          method: "POST",
          body: { grant_id: holder.id },
        });
        setBusy(false);
        setAsking(null);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        onWritten();
      })();
    },
    [onWritten],
  );

  if (answer.failure) {
    return <FailureNotice failure={answer.failure} />;
  }
  if (answer.busy) {
    return (
      <p className="note" role="status">
        Loading.
      </p>
    );
  }
  const page = readHolders(answer.data);
  return (
    <>
      <section className="card">
        <h2>{HOLDERS_HEADING}</h2>
        {failure === null ? null : <FailureNotice failure={failure} />}
        {asking === null ? null : (
          <ConfirmAction
            question={`${removeRoleLabel(asking)}?`}
            consequence={REMOVAL_CONSEQUENCE}
            confirmLabel={REMOVE_ROLE}
            cancelLabel={KEEP_ROLE}
            busy={busy}
            onConfirm={() => {
              remove(asking);
            }}
            onCancel={() => {
              setAsking(null);
            }}
          />
        )}
        {page.items.length === 0 ? (
          <p className="note">{NO_HOLDERS}</p>
        ) : (
          <ul className="roster" aria-label={HOLDERS_LIST_LABEL}>
            {page.items.map((holder) => (
              <li key={holder.id}>
                <code>{holder.principal_id}</code> {describe(holder)}{" "}
                {page.editable ? (
                  <button
                    type="button"
                    className="button"
                    disabled={busy || asking !== null}
                    onClick={() => {
                      setFailure(null);
                      setAsking(holder);
                    }}
                  >
                    {removeRoleLabel(holder)}
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
      {page.editable ? <Controls holders={page.items} onWritten={onWritten} /> : null}
    </>
  );
}

export function RoleControls() {
  // A counter rather than a boolean, so two writes in a row remount twice. Never rendered as a number.
  const [version, setVersion] = useState(0);
  const onWritten = useCallback(() => {
    setVersion((current) => current + 1);
  }, []);
  return <Holders key={version} onWritten={onWritten} />;
}


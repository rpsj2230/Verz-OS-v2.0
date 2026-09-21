/**
 * Which directory group confers which role, and the roles the sync has written from them.
 *
 * The Roles screen's mapping section (M1.1.5). An administrator maps a group, spelt as the identity
 * provider spells it, to one of the six roles, with a scope by name for Department Admin and
 * Approver. The sync applies the rules each time somebody signs in, adding the role for a group
 * they are in and removing it when they have left; retiring a rule removes every role it gave at
 * once. A group maps to a role and never to a capability, so there is no capability or pack field
 * here to fill in.
 *
 * **Nothing here decides who may do what.** The rules and the synced roles are what
 * `GET /govern/roles/group-rules` answered for this reader; the controls are drawn when it said
 * `editable`; every refusal is the API's own sentence, rendered as it came.
 *
 * Task ids: M1.1.5
 */

import { useCallback, useState } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ConfirmAction } from "../components/ConfirmAction";
import { FailureNotice } from "../ui/FailureNotice";
import {
  GROUP_RULES_API_PATH,
  GROUP_RULE_RETIREMENT_API_PATH,
  ROLE_VALUES,
  readGroupRules,
  submittedGroupRule,
  type GroupRuleRow,
} from "./governQuery";
import { blankSentence } from "./RoleControls";

export const GROUP_RULES_HEADING = "Directory groups";
export const GROUP_RULES_LEDE =
  "Each group maps to one role. Somebody in the group holds the role from their next sign-in, and " +
  "loses it when they leave the group. Retiring a rule removes every role it gave at once. A " +
  "group never grants a permission.";
export const NO_GROUP_RULES = "No directory group maps to a role yet.";
export const GROUP_RULES_LIST_LABEL = "Directory group rules";
export const SYNCED_HEADING = "Roles held through a directory group";
export const NO_SYNCED = "Nobody you may see holds a role through a directory group yet.";
export const SYNCED_LIST_LABEL = "Roles held through a directory group";
export const RETIRE_RULE = "Retire the rule";
export const KEEP_RULE = "Keep it";
export const RETIREMENT_CONSEQUENCE =
  "Everybody who holds the role through this group loses it at once. The rule is retired, not " +
  "deleted, and the audit trail records who retired it.";

export function retireRuleLabel(rule: GroupRuleRow): string {
  return `Retire ${rule.idp_group} as ${rule.role}`;
}

/** One labelled control of the mapping form. */
interface Field {
  readonly name: string;
  readonly label: string;
  readonly required: boolean;
  readonly choices?: readonly string[];
}

export const GROUP_RULE_FIELDS: readonly Field[] = [
  { name: "idp_group", label: "Group, as the identity provider spells it", required: true },
  { name: "role", label: "Role", required: true, choices: ROLE_VALUES },
  { name: "scope_slug", label: "Scope, for Department Admin and Approver", required: false },
  { name: "reason", label: "Reason", required: true },
];

/**
 * The mapping form. Blank required fields are said before anything is sent; every other judgement,
 * including a group already mapped and a role that needs a scope, is the API's, in its own words.
 */
function MappingForm({ onWritten }: { readonly onWritten: () => void }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [blank, setBlank] = useState<string | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="card"
      aria-label="Map a directory group to a role"
      onSubmit={(event) => {
        event.preventDefault();
        const missing = GROUP_RULE_FIELDS.filter(
          (one) => one.required && (values[one.name] ?? "").trim() === "",
        );
        const body = submittedGroupRule(values);
        if (missing.length > 0 || body === null) {
          setBlank(blankSentence(missing));
          return;
        }
        setBlank(null);
        setBusy(true);
        void (async () => {
          const result = await request<unknown>(GROUP_RULES_API_PATH, { method: "POST", body });
          setBusy(false);
          if (!result.ok) {
            setFailure(result.failure);
            return;
          }
          setFailure(null);
          onWritten();
        })();
      }}
    >
      <h3>Map a directory group to a role</h3>
      {GROUP_RULE_FIELDS.map((one) => (
        <label key={one.name} className="control-label">
          <span>{one.label}</span>
          {one.choices === undefined ? (
            <input
              className="form-control"
              name={one.name}
              type="text"
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
                  {choice}
                </option>
              ))}
            </select>
          )}
        </label>
      ))}
      {blank === null ? null : <p className="note">{blank}</p>}
      {failure === null ? null : <FailureNotice failure={failure} />}
      <button type="submit" className="button" disabled={busy}>
        Map the group
      </button>
    </form>
  );
}

function Mapping({ onWritten }: { readonly onWritten: () => void }) {
  const answer = useResource<unknown>(GROUP_RULES_API_PATH);
  const [asking, setAsking] = useState<GroupRuleRow | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const retire = useCallback(
    (rule: GroupRuleRow) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(GROUP_RULE_RETIREMENT_API_PATH, {
          method: "POST",
          body: { rule_id: rule.id },
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
  const page = readGroupRules(answer.data);
  return (
    <>
      {failure === null ? null : <FailureNotice failure={failure} />}
      {asking === null ? null : (
        <ConfirmAction
          question={`${retireRuleLabel(asking)}?`}
          consequence={RETIREMENT_CONSEQUENCE}
          confirmLabel={RETIRE_RULE}
          cancelLabel={KEEP_RULE}
          busy={busy}
          onConfirm={() => {
            retire(asking);
          }}
          onCancel={() => {
            setAsking(null);
          }}
        />
      )}
      {page.rules.length === 0 ? (
        <p className="note">{NO_GROUP_RULES}</p>
      ) : (
        <ul className="roster" aria-label={GROUP_RULES_LIST_LABEL}>
          {page.rules.map((rule) => (
            <li key={rule.id}>
              <code>{rule.idp_group}</code> {rule.role}{" "}
              {page.editable ? (
                <button
                  type="button"
                  className="button"
                  disabled={busy || asking !== null}
                  onClick={() => {
                    setFailure(null);
                    setAsking(rule);
                  }}
                >
                  {retireRuleLabel(rule)}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {page.editable ? <MappingForm onWritten={onWritten} /> : null}
      <h3>{SYNCED_HEADING}</h3>
      {page.synced.length === 0 ? (
        <p className="note">{NO_SYNCED}</p>
      ) : (
        <ul className="roster" aria-label={SYNCED_LIST_LABEL}>
          {page.synced.map((row) => (
            <li key={`${row.principal_id}-${row.role}-${row.source_group}`}>
              <code>{row.principal_id}</code> {row.role} through <code>{row.source_group}</code>,
              last confirmed at sign-in {row.last_seen_at.slice(0, 10)}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export function GroupRules() {
  // A counter rather than a boolean, so two writes in a row remount twice. Never rendered as a number.
  const [version, setVersion] = useState(0);
  const onWritten = useCallback(() => {
    setVersion((current) => current + 1);
  }, []);
  return (
    <section className="card">
      <h2>{GROUP_RULES_HEADING}</h2>
      <p className="note">{GROUP_RULES_LEDE}</p>
      <Mapping key={version} onWritten={onWritten} />
    </section>
  );
}

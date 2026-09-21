/**
 * The six roles, what each one is for, and how many people usually hold it.
 *
 * `brain.console.screens` says what this screen has to make visible: "A role governs the
 * platform and never implies a capability, which this screen has to make visible." So there is
 * no capability anywhere on this page, in any arrangement, and there is no column that could
 * grow one: the row is a role, a sentence about what it exists to do, how many people usually
 * hold it, and whether a grant of it needs a scope. A table with a capability column beside a
 * role would be read as an implication this system does not have, whatever a caption said.
 *
 * **Who holds each role is its own section.** `gate.role_grant` (`0102`) records it, and
 * `RoleControls.tsx` lists the holders this reader may see beside the controls that appoint,
 * deputise and remove.
 *
 * **Nothing here decides who may see it.** The request is identical for every caller; a reader
 * without the grant is refused by the API and the refusal is rendered in the API's own words.
 *
 * Imported statically rather than split: the catalogue mounts neither the table library nor the
 * form library, which is `App.tsx`'s rule for `Overview`, `Agents` and `NotFound`, and the
 * holders' controls are plain labelled inputs for the same reason.
 *
 * Task ids: M27.7.5, M1.8.4, M1.3.2
 */

import { useResource } from "../api/useResource";
import {
  MISCONFIGURATIONS_API_PATH,
  ROLES_API_PATH,
  readMisconfigurations,
  readRoles,
} from "./governQuery";
import { FailureNotice } from "../ui/FailureNotice";
import { RoleControls } from "./RoleControls";

export const ROLES_HEADING = "Roles";

/** Under the heading. Says what a role is and, in the same breath, what it is not. */
export const ROLES_LEDE =
  "The six platform roles and what each one is for. A role governs the platform; it never " +
  "implies a capability, and nothing here grants one.";

/** An empty catalogue. Only reachable from an API that answered something unexpected. */
export const NO_ROLES = "There are no roles to show.";

/** The accessible name of the list. */
export const ROLES_LIST_LABEL = "The platform roles";

/** What the scope flag says, in words, because true and false are not the fact. */
export const SCOPE_REQUIRED = "A grant of this role needs a scope.";
export const SCOPE_NOT_REQUIRED = "A grant of this role carries no scope.";

function RolesAnswerView() {
  const answer = useResource<unknown>(ROLES_API_PATH);

  if (answer.failure) {
    return (
      <FailureNotice failure={answer.failure} />
    );
  }
  if (answer.busy) {
    return (
      <p className="note" role="status">
        Loading.
      </p>
    );
  }

  const roles = readRoles(answer.data);
  if (roles.length === 0) {
    return <p className="note">{NO_ROLES}</p>;
  }

  return (
    <>
      <ul className="roster" aria-label={ROLES_LIST_LABEL}>
        {roles.map((role) => (
          <li key={role.role}>
            <h2>{role.role}</h2>
            <p>{role.exists_to}</p>
            <p className="note">
              {role.typical_count}
              {". "}
              {role.scope_required ? SCOPE_REQUIRED : SCOPE_NOT_REQUIRED}
            </p>
          </li>
        ))}
      </ul>
    </>
  );
}

export const MISCONFIGURED_HEADING = "Approver role and approve permission";

/** What the flag is for, said once above it. */
export const MISCONFIGURED_LEDE =
  "The approve permission alone decides who may approve. These people hold the Approver role " +
  "without it, or hold it without the role, which is a misconfiguration either way.";

/** Nobody this reader may see is misconfigured. */
export const NONE_MISCONFIGURED = "Nobody you may see holds one without the other.";

export const MISCONFIGURED_LIST_LABEL = "Approver misconfigurations";

/**
 * The Approver flag (M1.8.4). Its own request, so a reader who may open this screen and not the
 * People screen is refused this section in the API's words and still sees the catalogue.
 */
function Misconfigured() {
  const answer = useResource<unknown>(MISCONFIGURATIONS_API_PATH);
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
  const rows = readMisconfigurations(answer.data);
  if (rows.length === 0) {
    return <p className="note">{NONE_MISCONFIGURED}</p>;
  }
  return (
    <ul className="roster" aria-label={MISCONFIGURED_LIST_LABEL}>
      {rows.map((row) => (
        <li key={`${row.principal_id}-${row.kind}`}>
          <code>{row.principal_id}</code> {row.sentence}
        </li>
      ))}
    </ul>
  );
}

export function Roles() {
  return (
    <article className="page">
      <h1>{ROLES_HEADING}</h1>
      <p className="lede">{ROLES_LEDE}</p>
      <RolesAnswerView />
      <RoleControls />
      <section className="card">
        <h2>{MISCONFIGURED_HEADING}</h2>
        <p className="note">{MISCONFIGURED_LEDE}</p>
        <Misconfigured />
      </section>
    </article>
  );
}

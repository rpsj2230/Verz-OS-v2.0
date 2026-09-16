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
 * **It says who holds each role, which is nobody, and says so rather than showing an empty
 * column.** `RoleGrant`'s own docstring says the table is not written; `migrations/versions/
 * 0006` says `role_grant` is M1.3.2 and builds only the directory's assertion, which is a
 * different fact under the same word. So the API answers a flag and this renders a sentence,
 * and the day the table lands the sentence goes and a column arrives.
 *
 * **Nothing here decides who may see it.** The request is identical for every caller; a reader
 * without the grant is refused by the API and the refusal is rendered in the API's own words.
 *
 * Imported statically rather than split. It mounts neither the table library nor the form
 * library and imports no stylesheet of its own, which is `App.tsx`'s rule for `Overview`,
 * `Agents` and `NotFound`: a chunk for it would buy a round trip and save no bytes.
 *
 * Task ids: M27.7.5
 */

import { useResource } from "../api/useResource";
import { ROLES_API_PATH, readRoles } from "./governQuery";
import { FailureNotice } from "../ui/FailureNotice";

export const ROLES_HEADING = "Roles";

/** Under the heading. Says what a role is and, in the same breath, what it is not. */
export const ROLES_LEDE =
  "The six platform roles and what each one is for. A role governs the platform; it never " +
  "implies a capability, and nothing here grants one.";

/**
 * What is said instead of a holders column.
 *
 * A sentence rather than an empty column, because an empty column reads as nobody holding the
 * role, and the truth is that nothing records it yet.
 */
export const HOLDERS_ARE_NOT_RECORDED =
  "Who holds each role is not recorded yet, so this page does not show it. The grant table for " +
  "roles has not been built; what the identity provider asserts about a person is a different " +
  "fact and is on the staff sources screen when that one exists.";

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
      <p className="note">{HOLDERS_ARE_NOT_RECORDED}</p>
    </>
  );
}

export function Roles() {
  return (
    <article className="page">
      <h1>{ROLES_HEADING}</h1>
      <p className="lede">{ROLES_LEDE}</p>
      <RolesAnswerView />
    </article>
  );
}

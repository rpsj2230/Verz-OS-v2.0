/**
 * A person named by their id, drawn as the name the directory shows this reader, and a link to their
 * page when the reader may open it.
 *
 * **An id is never drawn as a name.** Several routes (the audit trail, the Approver flag) carry only a
 * principal id, and the old screens printed it. This asks the directory route, which answers only
 * people the reader may be shown, and draws the name it found; for anybody it did not find, including
 * the system's own account, it draws the fallback, which says nothing the row did not already say.
 *
 * Task ids: M27.16.1
 */

import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import { listPath, NO_QUESTION } from "../../components/listing";
import { DIRECTORY_API_PATH, personAddress, readPeople } from "../people/peopleQuery";

/** What a person the reader may not see, or an account that is nobody, reads as. */
export const ANOTHER_ACCOUNT = "another account";

/** The most people one name lookup reads: the list contract's largest page. */
export const NAMES_PAGE = 200;

/**
 * The names of the people this reader may see, by id, from one request for the directory's largest
 * page. One request for a whole page of rows, rather than one per row; somebody past that page, or
 * not a person, is drawn as the fallback.
 */
export function useNames(wanted: boolean): ReadonlyMap<string, string> {
  const answer = useResource<unknown>(wanted ? listPath(DIRECTORY_API_PATH, NO_QUESTION, null, NAMES_PAGE) : null);
  return useMemo(() => new Map(readPeople(answer.data).map((one) => [one.principalId, one.displayName])), [answer.data]);
}

export function PersonName({
  principalId,
  names,
  known,
  fallback = ANOTHER_ACCOUNT,
  link = true,
}: {
  readonly principalId: string;
  /** The names `useNames` found. */
  readonly names: ReadonlyMap<string, string>;
  /** A name already sent with the row, which is used first. */
  readonly known?: string | null | undefined;
  readonly fallback?: string | undefined;
  readonly link?: boolean | undefined;
}) {
  const name = known === undefined || known === null || known === "" ? names.get(principalId) : known;
  if (name === undefined) {
    return <>{fallback}</>;
  }
  return link ? (
    <Link to={personAddress(principalId)} className="text-ink underline-offset-4 hover:underline">
      {name}
    </Link>
  ) : (
    <>{name}</>
  );
}

/** A role's word as a person reads it, from `brain.identity.roles.Role`. */
export const ROLE_WORDS: Readonly<Record<string, string>> = Object.freeze({
  super_admin: "Super Admin",
  department_admin: "Department admin",
  member: "Member",
  auditor: "Auditor",
  connector_admin: "Connector admin",
  approver: "Approver",
});

export function roleWords(role: string): string {
  return ROLE_WORDS[role] ?? role;
}

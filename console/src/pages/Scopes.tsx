/**
 * Scopes and departments: the row filters a grant can carry, and the departments they are
 * written over.
 *
 * **A scope is shown whole or not at all, predicate included.**
 * `brain.console.govern_surfaces.A_SCOPE_NAME_IS_THE_PREDICATE_SPELLED_IN_WORDS` is the
 * argument, and it is the opposite arrangement from the People screen: there the subject is
 * named and the capabilities are withheld, because a person's name says nothing on its own,
 * and here a scope's name is the predicate in other words, so a row with the predicate blanked
 * would be a row whose name already said it. There is therefore no truncation of a clause list
 * and no "..." on a long one.
 *
 * **The department list is a listing like any other.** It is what
 * `govern_surfaces.departments_offered` answered, which is narrowed to the departments this
 * reader's own scopes admit and carries no count of what it dropped. This page renders it as a
 * list of names and not as a filter, and that is worth saying plainly: the route declares no
 * department parameter, and a filter box whose parameter no route declares is discarded by
 * FastAPI without a word, leaving a person reading unfiltered rows as the matching ones. When
 * the parameter lands, this list is what the control is built from.
 *
 * **Nothing here decides which scopes are shown.** The request is identical for every caller.
 * A department-scoped reader is answered fewer rows and fewer names by the API, computed from
 * grants this browser never receives.
 *
 * Imported statically rather than split, for `Roles`' reason: neither heavy library and no
 * stylesheet of its own. `scopeText.ts` is the rendering of a clause and it imports nothing at
 * all, which is why this page can use the same one the routing matrix does without pulling the
 * table library in behind it.
 *
 * Task ids: M27.7.4
 */

import { useResource } from "../api/useResource";
import { readScopesPage, scopesApiPath } from "./governQuery";
import { scopeLines } from "./scopeText";
import { FailureNotice } from "../ui/FailureNotice";

export const SCOPES_HEADING = "Scopes and departments";

/** Under the heading. Says what a scope is, in the vocabulary the grant tables use. */
export const SCOPES_LEDE =
  "The row filters a grant can carry, and the departments they are usually written against. A " +
  "scope is a predicate over rows; its name is that predicate in words.";

/** An empty listing, whichever of the reasons it is empty. */
export const NO_SCOPES = "There are no scopes to show.";

/** No department names came back. One sentence, for both of the reasons there could be none. */
export const NO_DEPARTMENTS = "There are no departments to show.";

/** A page that came back full. A fact about there being more, and never a figure. */
export const MORE_SCOPES = "This page came back full, so there are more scopes than it shows.";

/** What a scope with no clauses is, in words, because an empty list is not self-explanatory. */
export const RESTRICTS_NOTHING = "This scope restricts nothing; it matches every row.";

/** What the department flag says, in words. */
export const IS_A_DEPARTMENT = "This scope is a department.";

/** The accessible names of the two lists. */
export const SCOPES_LIST_LABEL = "Scopes you can see";
export const DEPARTMENTS_LIST_LABEL = "Departments you can see";

function ScopesAnswerView() {
  const answer = useResource<unknown>(scopesApiPath());

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

  const page = readScopesPage(answer.data);

  return (
    <>
      {page.scopes.length === 0 ? (
        <p className="note">{NO_SCOPES}</p>
      ) : (
        <ul className="roster" aria-label={SCOPES_LIST_LABEL}>
          {page.scopes.map((scope) => {
            const lines = scopeLines(scope.scope);
            return (
              <li key={scope.slug}>
                <h2>
                  <code>{scope.slug}</code>
                </h2>
                {scope.label === "" ? null : <p>{scope.label}</p>}
                {lines.length === 0 ? (
                  <p className="note">{RESTRICTS_NOTHING}</p>
                ) : (
                  <ul>
                    {lines.map((line) => (
                      <li key={line}>
                        <code>{line}</code>
                      </li>
                    ))}
                  </ul>
                )}
                {scope.is_department ? <p className="note">{IS_A_DEPARTMENT}</p> : null}
              </li>
            );
          })}
        </ul>
      )}

      {page.truncated ? <p className="note">{MORE_SCOPES}</p> : null}

      <h2>Departments</h2>
      {page.departments.length === 0 ? (
        <p className="note">{NO_DEPARTMENTS}</p>
      ) : (
        <ul className="roster" aria-label={DEPARTMENTS_LIST_LABEL}>
          {page.departments.map((name) => (
            <li key={name}>
              <code>{name}</code>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export function Scopes() {
  return (
    <article className="page">
      <h1>{SCOPES_HEADING}</h1>
      <p className="lede">{SCOPES_LEDE}</p>
      <ScopesAnswerView />
    </article>
  );
}

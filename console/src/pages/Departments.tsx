/**
 * Departments and teams: the organisation, and who belongs to each part of it.
 *
 * `docs/screens.html` SCREEN 10, People and Grants, draws this as its Organisation card: the
 * company, each department, and the people in it, with a person's row leading to what they hold.
 * This screen is that card at full width. The crumb, the filter bar, one card per department with
 * its teams and its people, and the hint under it are the design's; each person links to their row
 * on People and grants, which is the design's entitlement panel beside the tree.
 *
 * **Adapted where the install records nothing, and said in words where the design draws a value.**
 * The design puts a headcount and a lead's name beside every department and a role and a grant count
 * beside every person. No headcount is drawn, because every list here is narrowed to the reader and
 * a number beside it is a subtraction. No lead and no role are drawn, because no table records
 * either. No team has members, because no table records those either. Each of those is a sentence
 * the API sends and this page shows, so the day one becomes true the sentence changes with it.
 *
 * **Nothing here decides who may see anything.** The API answers from `brain.console.organisation`,
 * and the search narrows the rows already on the page. See
 * `governPeopleQuery.A_FILTER_OVER_A_PAGE_OFFERS_THE_PAGE`.
 *
 * Imported statically: it mounts neither heavy library and no stylesheet of its own.
 *
 * Task ids: M27.7.4
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { Notice } from "../ui/Notice";
import {
  departmentsApiPath,
  personAddress,
  readOrganisation,
  searchedOrganisation,
  type MemberRow,
} from "./governPeopleQuery";
import { SOMETHING_DID_NOT_WORK } from "./Overview";

export const DEPARTMENTS_HEADING = "Departments and teams";
export const DEPARTMENTS_CRUMB = "Govern › Departments and teams";
export const DEPARTMENTS_LEDE =
  "Every department you may see, the teams inside it, and the people who sit in it. Open a person " +
  "to see what they hold.";

/** The four states. */
export const READING_DEPARTMENTS = "Reading the organisation.";
export const NO_DEPARTMENTS_HERE = "There are no departments to show.";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";

/** A department with nobody listed under it. About the page, never a figure. */
export const NOBODY_LISTED = "Nobody is listed in this department.";
export const NO_TEAMS = "This department has no teams.";
export const NONE_MATCH = "No department or person on this page matches that search.";
export const MORE_ROWS = "This list came back full, so there is more than it shows.";
export const DISABLED = "Disabled";

export const SEARCH_LABEL = "Find a department or a person";
export const UNPLACED_HEADING = "Not in a recorded department";

function Failure({ failure }: { readonly failure: ApiFailure }) {
  return (
    <Notice
      title={failure.status === 0 ? THE_BRAIN_COULD_NOT_BE_REACHED : SOMETHING_DID_NOT_WORK}
      traceId={failure.traceId}
    >
      <p>{failure.message}</p>
    </Notice>
  );
}

function Person({ member, department }: { readonly member: MemberRow; readonly department?: string | null }) {
  return (
    <li>
      <Link to={personAddress(member.principal_id)}>{member.display_name}</Link>{" "}
      <code>{member.principal_id}</code>
      {department === undefined || department === null ? null : (
        <>
          {" "}
          <code>{department}</code>
        </>
      )}
      {member.disabled ? <span className="note"> {DISABLED}</span> : null}
    </li>
  );
}

function Organisation() {
  const answer = useResource<unknown>(departmentsApiPath());
  const [search, setSearch] = useState("");

  if (answer.failure) {
    return <Failure failure={answer.failure} />;
  }
  if (answer.busy) {
    return (
      <p className="note" role="status">
        {READING_DEPARTMENTS}
      </p>
    );
  }

  const page = readOrganisation(answer.data);
  const shown = searchedOrganisation(page.departments, search);

  return (
    <>
      {page.departments.length === 0 ? null : (
        <form className="form" role="search" onSubmit={(event) => event.preventDefault()}>
          <label className="control-label">
            {SEARCH_LABEL}{" "}
            <input
              className="form-control"
              type="search"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
              }}
            />
          </label>
        </form>
      )}

      {page.departments.length === 0 ? (
        <p className="note">{NO_DEPARTMENTS_HERE}</p>
      ) : shown.length === 0 ? (
        <p className="note">{NONE_MATCH}</p>
      ) : (
        shown.map((department) => (
          <section className="card" key={department.slug} aria-labelledby={`department-${department.slug}`}>
            <h2 id={`department-${department.slug}`}>
              {department.name} <code>{department.slug}</code>
            </h2>
            <h3>Teams</h3>
            {department.teams.length === 0 ? (
              <p className="note">{NO_TEAMS}</p>
            ) : (
              <ul className="roster" aria-label={`Teams in ${department.name}`}>
                {department.teams.map((team) => (
                  <li key={team.slug}>
                    {team.name} <code>{`${department.slug}.${team.slug}`}</code>
                  </li>
                ))}
              </ul>
            )}
            <h3>People</h3>
            {department.members.length === 0 ? (
              <p className="note">{NOBODY_LISTED}</p>
            ) : (
              <ul className="roster" aria-label={`People in ${department.name}`}>
                {department.members.map((member) => (
                  <Person key={member.principal_id} member={member} />
                ))}
              </ul>
            )}
          </section>
        ))
      )}

      {search.trim() !== "" || page.unplaced.length === 0 ? null : (
        <section className="card" aria-labelledby="department-unplaced">
          <h2 id="department-unplaced">{UNPLACED_HEADING}</h2>
          <ul className="roster" aria-label={UNPLACED_HEADING}>
            {page.unplaced.map((member) => (
              <Person key={member.principal_id} member={member} department={member.department} />
            ))}
          </ul>
        </section>
      )}

      {page.truncated ? <p className="note">{MORE_ROWS}</p> : null}
      {[page.teams, page.leads, page.counted]
        .filter((sentence) => sentence !== "")
        .map((sentence) => (
          <p className="note" key={sentence}>
            {sentence}
          </p>
        ))}
    </>
  );
}

export function Departments() {
  return (
    <article className="page">
      <p className="note">{DEPARTMENTS_CRUMB}</p>
      <h1>{DEPARTMENTS_HEADING}</h1>
      <p className="lede">{DEPARTMENTS_LEDE}</p>
      <Organisation />
    </article>
  );
}

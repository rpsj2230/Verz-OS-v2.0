/**
 * Departments and teams: the organisation, who belongs to each part of it, and who leads each.
 *
 * `docs/screens.html` SCREEN 10, People and Grants, draws this as its Organisation card: the
 * company, each department with its lead beside it, and the people in it, with a person's row
 * leading to what they hold. This screen is that card at full width. The crumb, the filter bar, one
 * card per department with its lead, its teams and their members, and its people, and the hint under
 * it are the design's; each person links to their row on People and grants, which is the design's
 * entitlement panel beside the tree.
 *
 * **Adapted where the design draws a figure, and said in words.** The design puts a headcount beside
 * every department and a role and a grant count beside every person. No figure is drawn, because
 * every list here is narrowed to the reader and a number beside it is a subtraction; no role is
 * drawn, because no table records one. A team whose members this reader may not name reads as a
 * team nobody is in, and the API's sentence says so.
 *
 * **Placing somebody and appointing a lead are confirmed, in the API's words.** An organiser sees an
 * add control under each team, a remove control beside each member, and an appoint and a stand-down
 * control under the lead. Each opens a confirmation naming the person and the team or department and
 * carrying the API's sentence that none of it changes anybody's access. The candidates offered are
 * the department's own people already on this page, never a list from anywhere else, for
 * `governPeopleQuery.A_FILTER_OVER_A_PAGE_OFFERS_THE_PAGE`'s reason. The route asks
 * `brain.console.organisation.may_place` and `may_appoint` whatever this page offered.
 *
 * **Nothing here decides who may see anything.** The API answers from `brain.console.organisation`,
 * the search narrows the rows already on the page, and a write is followed by a fresh request, keyed
 * on a counter, for `People.tsx`' reason: the page shows what the database holds.
 *
 * Imported statically: it mounts neither heavy library and no stylesheet of its own.
 *
 * Task ids: M27.7.4
 */

import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ConfirmAction } from "../components/ConfirmAction";
import { Notice } from "../ui/Notice";
import {
  LEAD_API_PATH,
  MEMBERSHIP_API_PATH,
  appointBody,
  departmentsApiPath,
  leadCandidates,
  leadQuestion,
  membershipBody,
  membershipQuestion,
  personAddress,
  readOrganisation,
  searchedOrganisation,
  standDownBody,
  teamCandidates,
  when,
  type DepartmentRow,
  type LeadBody,
  type MemberRow,
  type MembershipBody,
  type TeamRow,
} from "./governPeopleQuery";
import { SOMETHING_DID_NOT_WORK } from "./Overview";

export const DEPARTMENTS_HEADING = "Departments and teams";
export const DEPARTMENTS_CRUMB = "Govern › Departments and teams";
export const DEPARTMENTS_LEDE =
  "Every department you may see, who leads it, the teams inside it and who is in each, and the " +
  "people who sit in it. Open a person to see what they hold.";

/** The four states. */
export const READING_DEPARTMENTS = "Reading the organisation.";
export const NO_DEPARTMENTS_HERE = "There are no departments to show.";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";

/** A department or a team with nobody listed under it. About the page, never a figure. */
export const NOBODY_LISTED = "Nobody is listed in this department.";
export const NOBODY_IN_TEAM = "Nobody you may see is listed in this team.";
export const NO_LEAD = "No lead you may see is recorded for this department.";
export const NO_TEAMS = "This department has no teams.";
export const NONE_MATCH = "No department or person on this page matches that search.";
export const MORE_ROWS = "This list came back full, so there is more than it shows.";
export const DISABLED = "Disabled";

export const SEARCH_LABEL = "Find a department or a person";
export const UNPLACED_HEADING = "Not in a recorded department";

/** The controls, as verbs. */
export const ADD_LABEL = "Add to team";
export const REMOVE_LABEL = "Take out";
export const APPOINT_LABEL = "Appoint as lead";
export const STAND_DOWN_LABEL = "Stand down";
export const CANCEL_LABEL = "Leave it as it is";
export const CHOOSE_PERSON = "Choose a person";
/** What an add or an appointment sent with nobody chosen says, before anything is sent. */
export const CHOOSE_SOMEBODY_FIRST = "Choose who to place first; nothing has been sent.";

/** What a success says: what changed, for whom, and the instant the database recorded. */
export function changedSentence(question: string, at: string): string {
  return `Done: ${question.replace(/\?$/, "")}, recorded at ${when(at)}.`;
}

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

function readAt(payload: unknown): string {
  if (typeof payload !== "object" || payload === null) {
    return "";
  }
  const at = (payload as { at?: unknown }).at;
  return typeof at === "string" ? at : "";
}

/** One write waiting for its confirmation: where it goes, what it sends, and the words it shows. */
interface Pending {
  readonly path: string;
  readonly body: MembershipBody | LeadBody;
  readonly question: string;
  readonly consequence: string;
  readonly confirmLabel: string;
}

function Person({ member, department }: { readonly member: MemberRow; readonly department?: string | null }) {
  return (
    <>
      <Link to={personAddress(member.principal_id)}>{member.display_name}</Link> <code>{member.principal_id}</code>
      {department === undefined || department === null ? null : (
        <>
          {" "}
          <code>{department}</code>
        </>
      )}
      {member.disabled ? <span className="note"> {DISABLED}</span> : null}
    </>
  );
}

function Chooser({
  label,
  people,
  value,
  onChange,
}: {
  readonly label: string;
  readonly people: readonly MemberRow[];
  readonly value: string;
  readonly onChange: (value: string) => void;
}) {
  return (
    <label className="control-label">
      {label}{" "}
      <select
        className="form-control"
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      >
        <option value="">{CHOOSE_PERSON}</option>
        {people.map((one) => (
          <option key={one.principal_id} value={one.principal_id}>
            {one.display_name}
          </option>
        ))}
      </select>
    </label>
  );
}

function Organisation({ onChanged }: { readonly onChanged: (sentence: string) => void }) {
  const answer = useResource<unknown>(departmentsApiPath());
  const [search, setSearch] = useState("");
  const [chosen, setChosen] = useState<Readonly<Record<string, string>>>({});
  const [pending, setPending] = useState<Pending | null>(null);
  const [blank, setBlank] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const send = useCallback(
    (asked: Pending) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(asked.path, { method: "POST", body: asked.body });
        setBusy(false);
        setPending(null);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        onChanged(changedSentence(asked.question, readAt(result.data)));
      })();
    },
    [onChanged],
  );

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
  const choose = (key: string) => (value: string) => {
    setChosen({ ...chosen, [key]: value });
  };
  const nameOf = (people: readonly MemberRow[], id: string) =>
    people.find((one) => one.principal_id === id)?.display_name ?? id;

  const askJoin = (department: DepartmentRow, team: TeamRow, principalId: string) => {
    const question = membershipQuestion(team.name, nameOf(department.members, principalId), "join");
    setFailure(null);
    setPending({
      path: MEMBERSHIP_API_PATH,
      body: membershipBody(department.slug, team.slug, principalId, "join"),
      question,
      consequence: page.teams,
      confirmLabel: ADD_LABEL,
    });
  };
  const askLeave = (department: DepartmentRow, team: TeamRow, member: MemberRow) => {
    setFailure(null);
    setPending({
      path: MEMBERSHIP_API_PATH,
      body: membershipBody(department.slug, team.slug, member.principal_id, "leave"),
      question: membershipQuestion(team.name, member.display_name, "leave"),
      consequence: page.teams,
      confirmLabel: REMOVE_LABEL,
    });
  };
  const askAppoint = (department: DepartmentRow, principalId: string) => {
    setFailure(null);
    setPending({
      path: LEAD_API_PATH,
      body: appointBody(department.slug, principalId),
      question: leadQuestion(department.name, nameOf(department.members, principalId), "appoint"),
      consequence: page.leads,
      confirmLabel: APPOINT_LABEL,
    });
  };
  const askStandDown = (department: DepartmentRow, lead: MemberRow) => {
    setFailure(null);
    setPending({
      path: LEAD_API_PATH,
      body: standDownBody(department.slug),
      question: leadQuestion(department.name, lead.display_name, "stand_down"),
      consequence: page.leads,
      confirmLabel: STAND_DOWN_LABEL,
    });
  };

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

      {failure === null ? null : <Failure failure={failure} />}

      {pending === null ? null : (
        <ConfirmAction
          question={pending.question}
          consequence={pending.consequence}
          confirmLabel={pending.confirmLabel}
          cancelLabel={CANCEL_LABEL}
          busy={busy}
          onConfirm={() => {
            send(pending);
          }}
          onCancel={() => {
            setPending(null);
          }}
        />
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

            <h3>Lead</h3>
            {department.lead === null || department.lead === undefined ? (
              <p className="note">{NO_LEAD}</p>
            ) : (
              <p aria-label={`Lead of ${department.name}`}>
                <Person member={department.lead} />
                {page.mayOrganise ? (
                  <>
                    {" "}
                    <button
                      type="button"
                      className="button"
                      disabled={busy}
                      onClick={() => {
                        if (department.lead) {
                          askStandDown(department, department.lead);
                        }
                      }}
                    >
                      {STAND_DOWN_LABEL}
                    </button>
                  </>
                ) : null}
              </p>
            )}
            {page.mayOrganise && leadCandidates(department).length > 0 ? (
              <form
                className="form"
                aria-label={`Lead of ${department.name}`}
                onSubmit={(event) => {
                  event.preventDefault();
                  const principalId = chosen[`lead:${department.slug}`] ?? "";
                  if (principalId === "") {
                    setBlank(`lead:${department.slug}`);
                    return;
                  }
                  setBlank(null);
                  askAppoint(department, principalId);
                }}
              >
                <Chooser
                  label={`Lead of ${department.name}`}
                  people={leadCandidates(department)}
                  value={chosen[`lead:${department.slug}`] ?? ""}
                  onChange={choose(`lead:${department.slug}`)}
                />{" "}
                <button type="submit" className="button" disabled={busy}>
                  {APPOINT_LABEL}
                </button>
                {blank === `lead:${department.slug}` ? <p className="note">{CHOOSE_SOMEBODY_FIRST}</p> : null}
              </form>
            ) : null}

            <h3>Teams</h3>
            {department.teams.length === 0 ? (
              <p className="note">{NO_TEAMS}</p>
            ) : (
              <ul className="roster" aria-label={`Teams in ${department.name}`}>
                {department.teams.map((team) => {
                  const members = team.members ?? [];
                  const key = `team:${department.slug}.${team.slug}`;
                  const candidates = teamCandidates(department, team);
                  return (
                    <li key={team.slug}>
                      {team.name} <code>{`${department.slug}.${team.slug}`}</code>
                      {members.length === 0 ? (
                        <p className="note">{NOBODY_IN_TEAM}</p>
                      ) : (
                        <ul className="roster" aria-label={`Members of ${team.name}`}>
                          {members.map((member) => (
                            <li key={member.principal_id}>
                              <Person member={member} />
                              {page.mayOrganise ? (
                                <>
                                  {" "}
                                  <button
                                    type="button"
                                    className="button"
                                    disabled={busy}
                                    aria-label={`${REMOVE_LABEL}: ${membershipQuestion(team.name, member.display_name, "leave")}`}
                                    onClick={() => {
                                      askLeave(department, team, member);
                                    }}
                                  >
                                    {REMOVE_LABEL}
                                  </button>
                                </>
                              ) : null}
                            </li>
                          ))}
                        </ul>
                      )}
                      {page.mayOrganise && candidates.length > 0 ? (
                        <form
                          className="form"
                          aria-label={`Add to ${team.name}`}
                          onSubmit={(event) => {
                            event.preventDefault();
                            const principalId = chosen[key] ?? "";
                            if (principalId === "") {
                              setBlank(key);
                              return;
                            }
                            setBlank(null);
                            askJoin(department, team, principalId);
                          }}
                        >
                          <Chooser
                            label={`Add to ${team.name}`}
                            people={candidates}
                            value={chosen[key] ?? ""}
                            onChange={choose(key)}
                          />{" "}
                          <button type="submit" className="button" disabled={busy}>
                            {ADD_LABEL}
                          </button>
                          {blank === key ? <p className="note">{CHOOSE_SOMEBODY_FIRST}</p> : null}
                        </form>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            )}

            <h3>People</h3>
            {department.members.length === 0 ? (
              <p className="note">{NOBODY_LISTED}</p>
            ) : (
              <ul className="roster" aria-label={`People in ${department.name}`}>
                {department.members.map((member) => (
                  <li key={member.principal_id}>
                    <Person member={member} />
                  </li>
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
              <li key={member.principal_id}>
                <Person member={member} department={member.department} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {page.truncated ? <p className="note">{MORE_ROWS}</p> : null}
      {[page.teams, page.leads, page.counted, page.mayOrganise ? page.organising : ""]
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
  // A counter rather than a boolean, so two changes in a row remount twice. Never rendered.
  const [generation, setGeneration] = useState(0);
  const [changed, setChanged] = useState<string | null>(null);
  const onChanged = useCallback((sentence: string) => {
    setChanged(sentence);
    setGeneration((current) => current + 1);
  }, []);

  return (
    <article className="page">
      <p className="note">{DEPARTMENTS_CRUMB}</p>
      <h1>{DEPARTMENTS_HEADING}</h1>
      <p className="lede">{DEPARTMENTS_LEDE}</p>
      {changed === null ? null : (
        <p className="note" role="status">
          {changed}
        </p>
      )}
      <Organisation key={generation} onChanged={onChanged} />
    </article>
  );
}
